"""
APEX Trading Bot — Main Entry Point
=====================================
The brain. Orchestrates everything:
  - Loads config
  - Connects to all enabled exchanges
  - Runs strategy analysis in parallel every cycle
  - Scores and ranks signals (best edge wins)
  - Routes winning signals through risk manager → execution engine
  - Monitors open trades
  - Handles daily resets, kill switches, graceful shutdown

Usage:
  python main.py                         # Uses config.yaml
  python main.py --config config.local.yaml
  python main.py --paper                 # Force paper mode
  python main.py --live                  # Force live mode (careful!)
  python main.py --pair BTCUSDT --venue toobit  # Single pair mode
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from data.store import TradeStore
from exchanges.toobit import ToobitExchange
from exchanges.hyperliquid import HyperliquidExchange
from exchanges.lighter import LighterExchange
from exchanges.polymarket import PolymarketExchange
from exchanges.mock import MockExchange
from exchanges.base import BaseExchange
from execution.engine import ExecutionEngine
from monitoring.alerts import TelegramAlerter
from monitoring.dashboard import Dashboard
from monitoring.web_dashboard import WebDashboard
from risk.manager import RiskManager
from signals.confluence import ConfluenceEngine
from strategies.base import Signal
from strategies.breakout import BreakoutStrategy
from strategies.claude_advisor import ClaudeAdvisor
from strategies.delta_neutral import DeltaNeutralStrategy
from strategies.funding_arb import FundingArbStrategy
from strategies.liquidation_cascade import LiquidationCascadeStrategy
from strategies.momentum import MomentumStrategy
from strategies.polymarket_arb import PolymarketArbStrategy

log = logging.getLogger("apex.main")


def load_config(path: str) -> dict:
    with open(path) as f:
        config = yaml.safe_load(f)
    # Load secrets from .env (overrides config file values)
    load_dotenv()
    _inject_env(config)
    return config


def _inject_env(config: dict) -> None:
    """Pull secrets from environment variables into config."""
    venues = config.get("venues", {})
    env_map = {
        "TOOBIT_API_KEY": ("toobit", "api_key"),
        "TOOBIT_API_SECRET": ("toobit", "api_secret"),
        "HYPERLIQUID_WALLET": ("hyperliquid", "wallet_address"),
        "HYPERLIQUID_PRIVATE_KEY": ("hyperliquid", "private_key"),
        "LIGHTER_WALLET": ("lighter", "wallet_address"),
        "LIGHTER_PRIVATE_KEY": ("lighter", "private_key"),
        "POLYMARKET_API_KEY": ("polymarket", "api_key"),
        "POLYMARKET_API_SECRET": ("polymarket", "api_secret"),
        "POLYMARKET_PASSPHRASE": ("polymarket", "passphrase"),
        "POLYMARKET_PRIVATE_KEY": ("polymarket", "wallet_private_key"),
        "TELEGRAM_BOT_TOKEN": (None, None),  # handled separately
        "TELEGRAM_CHAT_ID": (None, None),
    }
    for env_var, (venue, key) in env_map.items():
        val = os.getenv(env_var)
        if val and venue and key:
            if venue in venues:
                venues[venue][key] = val

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    if tg_token:
        config.setdefault("monitoring", {}).setdefault("telegram", {})["bot_token"] = tg_token
        if tg_token:
            config["monitoring"]["telegram"]["enabled"] = True
    if tg_chat:
        config.setdefault("monitoring", {}).setdefault("telegram", {})["chat_id"] = tg_chat


def setup_logging(config: dict) -> None:
    level = getattr(logging, config.get("bot", {}).get("log_level", "INFO"))
    log_file = config.get("monitoring", {}).get("log_file", "logs/apex.log")
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file),
        ]
    )


class OpportunityScore:
    """Ranks competing signals to pick the best edge available."""

    def __init__(self, config: dict):
        weights = config.get("scoring", {})
        self.weights = {
            "delta_neutral": weights.get("delta_neutral_weight", 0.35),   # Primary: highest weight
            "momentum": weights.get("momentum_weight", 0.25),
            "breakout": weights.get("breakout_weight", 0.20),
            "funding_arb": weights.get("funding_weight", 0.10),
            "liquidation_cascade": weights.get("liquidation_weight", 0.05),
            "polymarket_arb": weights.get("polymarket_arb_weight", 0.05),
        }
        self.min_score = weights.get("min_score_to_trade", 0.55)

    def score(self, signal: Signal) -> float:
        """
        Composite score: strategy weight × signal confidence.
        A signal must exceed min_score to be tradeable.
        """
        weight = self.weights.get(signal.strategy, 0.1)
        base_score = weight * signal.confidence

        # Bonus for high R:R
        rr_bonus = min((signal.risk_reward - 1.5) * 0.05, 0.10)

        return round(base_score + rr_bonus, 4)

    def rank_signals(self, signals: list[Signal]) -> list[tuple[float, Signal]]:
        """Returns signals sorted by score, descending. Filters below threshold."""
        scored = [(self.score(sig), sig) for sig in signals]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(s, sig) for s, sig in scored if s >= self.min_score]


class ApexBot:
    def __init__(self, config: dict, paper_override: bool | None = None, demo: bool = False):
        self.config = config
        if paper_override is not None:
            self.config["bot"]["mode"] = "paper" if paper_override else "live"

        self.paper_mode = config["bot"]["mode"] == "paper"
        self.demo_mode  = demo
        self._running = False
        self._shutdown_event = asyncio.Event()

        # ── Core components ───────────────────────────────────────────
        self.exchanges: dict[str, BaseExchange] = {}
        self.risk = RiskManager(config)
        self.store = TradeStore(config.get("monitoring", {}).get("db_file", "data/apex.db"))
        self.execution = ExecutionEngine(self.exchanges, self.risk, self.paper_mode)
        self.scorer = OpportunityScore(config)
        self.confluence = ConfluenceEngine()
        self.alerter = TelegramAlerter(config)
        self.dashboard = Dashboard(config)

        # Claude AI advisor — reviews Tier 2+ signals before execution
        claude_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.claude: ClaudeAdvisor | None = None
        if claude_key:
            try:
                self.claude = ClaudeAdvisor(claude_key)
                log.info("Claude AI advisor enabled — Tier 2+ signals will be reviewed")
            except Exception as e:
                log.warning("Claude advisor init failed: %s — running without AI review", e)
        else:
            log.info("No ANTHROPIC_API_KEY set — bot runs rule-based only (no Claude review)")
        self.webdash = WebDashboard(
            port=config.get("monitoring", {}).get("web_port", 8080),
            starting_balance=config["capital"]["starting_balance_usd"],
            monthly_target=config.get("monitoring", {}).get("monthly_target", 2500.0),
        )

        # ── Strategies ────────────────────────────────────────────────
        self.strategies = []
        strat_configs = config.get("strategies", {})
        # Delta-neutral is priority 0 — always loaded first (primary yield strategy)
        if strat_configs.get("delta_neutral", {}).get("enabled", False):
            self.strategies.append(DeltaNeutralStrategy(strat_configs["delta_neutral"]))
        if strat_configs.get("momentum", {}).get("enabled", False):
            self.strategies.append(MomentumStrategy(strat_configs["momentum"]))
        if strat_configs.get("breakout", {}).get("enabled", False):
            self.strategies.append(BreakoutStrategy(strat_configs["breakout"]))
        if strat_configs.get("funding_arb", {}).get("enabled", False):
            self.strategies.append(FundingArbStrategy(strat_configs["funding_arb"]))
        if strat_configs.get("liquidation_cascade", {}).get("enabled", False):
            self.strategies.append(LiquidationCascadeStrategy(strat_configs["liquidation_cascade"]))
        if strat_configs.get("polymarket_arb", {}).get("enabled", False):
            self.strategies.append(PolymarketArbStrategy(strat_configs["polymarket_arb"]))

        # Sort by priority
        self.strategies.sort(key=lambda s: s.priority)

        self._cycle_count = 0
        self._last_daily_reset = 0.0
        self._last_balance_log = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        log.info("=" * 60)
        log.info("APEX BOT STARTING | mode=%s", "PAPER" if self.paper_mode else "LIVE")
        log.info("Strategies: %s", [s.name for s in self.strategies])
        log.info("=" * 60)

        # Connect infrastructure
        await self.store.connect()
        self.execution.attach_store(self.store)
        await self.alerter.connect()
        self.dashboard.attach(self.execution, self.risk)

        # Connect exchanges
        await self._connect_exchanges()

        # Auto-fallback: if nothing connected, spin up mock exchange for demo
        if not self.exchanges:
            if self.demo_mode or self.paper_mode:
                log.warning("No real exchanges reachable — starting DEMO mode with synthetic prices")
                mock = MockExchange()
                await mock.connect()
                # Register mock under every pair/venue referenced in strategy configs
                for strat_cfg in self.config.get("strategies", {}).values():
                    for venue in strat_cfg.get("venues", []):
                        if venue not in self.exchanges:
                            self.exchanges[venue] = mock
                if not self.exchanges:
                    self.exchanges["hyperliquid"] = mock
            else:
                log.error("No exchanges connected! Check your config and API keys.")
                return

        # Initialize daily stats
        initial_balance = await self._get_total_balance()
        self.risk.reset_daily(initial_balance)

        log.info("Connected to: %s | Balance: $%.2f", list(self.exchanges.keys()), initial_balance)
        await self.alerter.send_custom(
            f"*APEX Bot Started*\n"
            f"Mode: {'PAPER' if self.paper_mode else 'LIVE'}\n"
            f"Balance: ${initial_balance:.2f}\n"
            f"Strategies: {', '.join(s.name for s in self.strategies)}"
        )

        # Attach and start dashboards
        self.webdash.attach(self.execution, self.risk)
        self.webdash.start()
        self.dashboard.start()

        # Register shutdown handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        self._running = True
        await self._main_loop()

    async def shutdown(self) -> None:
        log.info("Shutting down APEX bot...")
        self._running = False
        self._shutdown_event.set()

        # Cancel all pending orders
        for venue, exchange in self.exchanges.items():
            try:
                count = await exchange.cancel_all_orders()
                if count:
                    log.info("Cancelled %d orders on %s", count, venue)
            except Exception as e:
                log.warning("cancel_all on %s: %s", venue, e)

        # Disconnect
        for exchange in self.exchanges.values():
            try:
                await exchange.disconnect()
            except Exception:
                pass

        self.dashboard.stop()
        await self.alerter.disconnect()
        await self.store.disconnect()
        log.info("APEX bot stopped cleanly.")

    # ── Main Loop ─────────────────────────────────────────────────────

    async def _main_loop(self) -> None:
        """The heartbeat. Runs forever until shutdown."""
        while self._running and not self._shutdown_event.is_set():
            self._cycle_count += 1
            cycle_start = time.time()

            try:
                await self._cycle()
            except Exception as e:
                log.error("Main loop error (cycle %d): %s", self._cycle_count, e, exc_info=True)

            # Dashboard refresh
            self.dashboard.refresh()

            # Sleep remainder of 30-second cycle
            elapsed = time.time() - cycle_start
            sleep_time = max(0, 30.0 - elapsed)
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._shutdown_event.wait()),
                    timeout=sleep_time
                )
                break   # Shutdown event fired
            except asyncio.TimeoutError:
                pass    # Normal — continue next cycle

    async def _cycle(self) -> None:
        """Single bot cycle: monitor → analyze → execute."""
        # ── 1. Check daily reset ──────────────────────────────────────
        await self._check_daily_reset()

        # ── 2. Update balances ────────────────────────────────────────
        balance = await self._get_total_balance()
        self.risk.update_balance(balance)

        # ── 3. Monitor open trades ────────────────────────────────────
        closed_ids = await self.execution.monitor_trades()
        for trade_id in closed_ids:
            all_trades = {t.trade_id: t for t in self.execution.get_all_trades()}
            if trade_id in all_trades:
                closed_trade = all_trades[trade_id]
                self.dashboard.print_trade_closed(closed_trade)
                await self.alerter.trade_closed(closed_trade)

        # Update risk manager with current positions
        all_positions = []
        for exchange in self.exchanges.values():
            try:
                positions = await exchange.get_positions()
                all_positions.extend(positions)
            except Exception as e:
                log.debug("get_positions: %s", e)
        self.risk.update_open_positions(all_positions)

        # ── 4. Skip new signals if risk halted ────────────────────────
        if self.risk.is_halted:
            log.debug("Trading halted — skipping signal scan")
            return

        # ── 5. Gather signals from all strategies in parallel ─────────
        signal_tasks = [
            strategy.analyze_all(self.exchanges)
            for strategy in self.strategies
        ]
        results = await asyncio.gather(*signal_tasks, return_exceptions=True)

        all_signals: list[Signal] = []
        for result in results:
            if isinstance(result, list):
                all_signals.extend(result)
            elif isinstance(result, Exception):
                log.debug("Strategy error: %s", result)

        if not all_signals:
            return

        # ── 6. Confluence analysis ────────────────────────────────────
        # Get order book imbalance and funding bias to feed into confluence
        ob_imbalance = await self._get_orderbook_imbalance(all_signals)
        funding_bias = self._extract_funding_bias(all_signals)

        confluence_results = self.confluence.analyze(
            all_signals, ob_imbalance, funding_bias
        )

        best_confluence = self.confluence.get_best(confluence_results)
        if best_confluence and best_confluence[1].tier >= 2:
            log.info("TOP CONFLUENCE: %s", best_confluence[1])

        # ── 7. Score and rank signals ─────────────────────────────────
        ranked = self.scorer.rank_signals(all_signals)

        if ranked:
            log.debug(
                "Cycle %d: %d signals, %d above threshold",
                self._cycle_count, len(all_signals), len(ranked)
            )

        # ── 8. Execute best signal (if any) ──────────────────────────
        for score, signal in ranked:
            current_price = signal.entry_price

            # Look up confluence result for this signal's pair + direction
            direction = "long" if "long" in signal.direction.value else "short"
            conf_key = f"{signal.pair}:{direction}"
            confluence = confluence_results.get(conf_key)

            # ── Claude AI review (Tier 2+ only) ──────────────────────
            # Claude evaluates the full setup before risk approval.
            # A veto here skips execution without touching risk limits.
            if self.claude and confluence and confluence.tier >= 2:
                try:
                    ai_go, ai_reason, ai_adj = await self.claude.evaluate(
                        signal, confluence, self.risk.get_stats()
                    )
                    if not ai_go:
                        log.info(
                            "CLAUDE VETO: %s %s — %s",
                            signal.pair, signal.direction.value, ai_reason,
                        )
                        self.dashboard.print_signal(signal, False, f"CLAUDE_VETO: {ai_reason}")
                        await self.store.log_signal(signal, False, f"CLAUDE_VETO: {ai_reason}")
                        self.webdash.log_signal(
                            pair=signal.pair,
                            direction=signal.direction.value,
                            confidence=signal.confidence,
                            rr=signal.risk_reward,
                            score=score,
                            executed=False,
                            confluence_tier=confluence.tier if confluence else 1,
                        )
                        continue
                    # Claude approved — apply any confidence adjustment
                    if ai_adj != 0:
                        signal.confidence = max(0.0, min(1.0, signal.confidence + ai_adj))
                        log.info("Claude adjusted confidence by %+.2f → %.0%%", ai_adj, signal.confidence * 100)
                except Exception as e:
                    log.warning("Claude review error: %s — proceeding without AI review", e)

            approval = self.risk.approve_trade(signal, balance, current_price, confluence)

            self.dashboard.print_signal(signal, approval.approved, approval.reason)
            await self.store.log_signal(signal, approval.approved, approval.reason)

            # Log signal to web dashboard feed
            self.webdash.log_signal(
                pair=signal.pair,
                direction=signal.direction.value,
                confidence=signal.confidence,
                rr=signal.risk_reward,
                score=score,
                executed=False,  # updated below if executed
                confluence_tier=confluence.tier if confluence else 1,
            )

            if not approval.approved:
                continue

            # Execute the trade
            trade = await self.execution.execute_signal(signal, approval)
            if trade:
                # Update the last signal entry to mark it executed
                if self.webdash._signal_buffer:
                    self.webdash._signal_buffer[-1]["executed"] = True
                self.dashboard.print_trade_open(trade)
                await self.alerter.trade_opened(trade)
                # Only execute ONE signal per cycle (avoid over-trading)
                break

        # ── 8. Push state to web dashboard ───────────────────────────
        await self.webdash.push_state()

        # ── 9. Periodic balance logging ───────────────────────────────
        if time.time() - self._last_balance_log > 300:  # every 5 min
            await self.store.log_balance("total", balance)
            self._last_balance_log = time.time()

    # ── Helpers ───────────────────────────────────────────────────────

    async def _connect_exchanges(self) -> None:
        venues = self.config.get("venues", {})
        exchange_classes = {
            "toobit": ToobitExchange,
            "hyperliquid": HyperliquidExchange,
            "lighter": LighterExchange,
            "polymarket": PolymarketExchange,
        }

        for name, cls in exchange_classes.items():
            cfg = venues.get(name, {})
            if not cfg.get("enabled", False):
                continue
            try:
                exchange = cls(cfg)
                await exchange.connect()
                self.exchanges[name] = exchange
                log.info("Connected: %s", name)
            except Exception as e:
                log.warning("Failed to connect %s: %s", name, e)

    async def _get_total_balance(self) -> float:
        """Sum balances across unique connected exchanges (dedup by identity)."""
        total = 0.0
        seen: set[int] = set()
        for exchange in self.exchanges.values():
            if id(exchange) in seen:
                continue
            seen.add(id(exchange))
            try:
                bal = await exchange.get_balance()
                total += bal.available_usd
            except Exception as e:
                log.debug("get_balance %s: %s", exchange.name, e)
        return total if total > 0 else self.config["capital"]["starting_balance_usd"]

    async def _get_orderbook_imbalance(self, signals: list[Signal]) -> float:
        """
        Fetch order book imbalance for the most active pair/venue in signals.
        Used to feed into confluence engine for additional scoring.
        Returns imbalance in range [-1.0, +1.0].
        """
        if not signals:
            return 0.0
        # Use the first signal's venue/pair as a representative sample
        sig = signals[0]
        exchange = self.exchanges.get(sig.venue)
        if not exchange:
            return 0.0
        try:
            ob = await exchange.get_orderbook(sig.pair)
            return ob.imbalance()
        except Exception:
            return 0.0

    def _extract_funding_bias(self, signals: list[Signal]) -> float:
        """
        Pull funding bias from any funding_arb signals in this cycle.
        The funding bias is a [-1.0, +1.0] value indicating whether the
        market is short-heavy (negative) or long-heavy (positive).
        """
        for sig in signals:
            if sig.strategy == "funding_arb":
                return sig.metadata.get("funding_bias", 0.0)
        return 0.0

    async def _check_daily_reset(self) -> None:
        """Reset daily stats at midnight UTC."""
        import datetime
        now = datetime.datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")
        if today_str != getattr(self, "_current_day", ""):
            balance = await self._get_total_balance()
            self.risk.reset_daily(balance)
            self._current_day = today_str

            # Send daily summary for the previous day
            stats = self.risk.get_stats()
            await self.alerter.daily_summary(stats)
            log.info("Daily reset complete. New balance: $%.2f", balance)


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="APEX Trading Bot")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--paper", action="store_true", help="Force paper trading mode")
    parser.add_argument("--live", action="store_true", help="Force live trading mode")
    parser.add_argument("--demo", action="store_true", help="Demo mode: synthetic prices, no API keys needed")
    parser.add_argument("--pair", help="Restrict to single pair (e.g. BTCUSDT)")
    parser.add_argument("--venue", help="Restrict to single venue")
    args = parser.parse_args()

    # Try local config first
    config_path = args.config
    if config_path == "config.yaml" and Path("config.local.yaml").exists():
        config_path = "config.local.yaml"

    config = load_config(config_path)
    setup_logging(config)

    # Override paper/live mode
    paper_override = None
    if args.paper:
        paper_override = True
    elif args.live:
        paper_override = False

    # Restrict pairs/venues if specified
    if args.pair or args.venue:
        for strat_name, strat_cfg in config.get("strategies", {}).items():
            if args.pair:
                strat_cfg["pairs"] = [args.pair]
            if args.venue:
                strat_cfg["venues"] = [args.venue]

    demo = args.demo or (args.paper and not args.live)
    bot = ApexBot(config, paper_override, demo=demo)

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received")


if __name__ == "__main__":
    main()
