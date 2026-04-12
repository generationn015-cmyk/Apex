"""
APEX — Master Orchestrator
Runs all agents on a loop, fetches live data, routes signals through
risk manager, executes on paper or live Lighter.xyz.

Usage:
    python3 main.py              # Run continuously (paper mode)
    python3 main.py --live       # Live trading (requires Lighter API keys)
    python3 main.py --once       # Single cycle then exit
    python3 main.py --backtest   # Backtest mode (not yet implemented)
"""
import asyncio
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from configs.config import (
    AGENTS, RISK, SCAN_INTERVAL_SECONDS, HEARTBEAT_MINUTES,
    TRADING_MODE, TWELVE_DATA_KEY, SESSION_FILTER,
    STATE_FILE, LOGS_DIR,
)
from core.data_fetcher import MarketDataFetcher
from core.risk_manager import RiskManager
from core.paper_engine import PaperEngine
from exchanges.paper import PaperExecutor
from exchanges.lighter import LighterExecutor
from strategies.atlas    import analyze_ATLAS
from strategies.oracle   import analyze_ORACLE
from strategies.sniper   import analyze_SNIPER
from strategies.sentinel import analyze_SENTINEL

ANALYZERS = {
    "ATLAS":    analyze_ATLAS,
    "ORACLE":   analyze_ORACLE,
    "SNIPER":   analyze_SNIPER,
    "SENTINEL": analyze_SENTINEL,
}

# Optional: Anthropic AI signal review (from signal_engine_v2 concept)
try:
    import anthropic
    from configs.config import ANTHROPIC_API_KEY
    _claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except ImportError:
    _claude = None


def in_session() -> bool:
    """Check if we're in active trading hours."""
    if not SESSION_FILTER["enabled"]:
        return True
    h = datetime.now(timezone.utc).hour
    return SESSION_FILTER["open_utc"] <= h < SESSION_FILTER["close_utc"]


def claude_review(signal_data: dict) -> bool:
    """
    Optional Claude AI gate on signals. Returns True to approve, False to reject.
    Only called when ANTHROPIC_API_KEY is set and signal strength >= 0.70.
    Costs ~$0.003/call — runs only on real signals, not every cycle.
    """
    if _claude is None:
        return True   # No API key → pass through

    prompt = (
        f"You are a trading signal validator. A signal fired:\n"
        f"  Asset: {signal_data['asset']}\n"
        f"  Direction: {signal_data['signal']}\n"
        f"  Agent: {signal_data['agent']}\n"
        f"  Strength: {signal_data['strength']}\n"
        f"  Indicators: {json.dumps(signal_data.get('indicators', {}), indent=2)}\n\n"
        f"Reply with a JSON object only:\n"
        f'  {{"approve": true/false, "reason": "one sentence"}}\n'
        f"Reject if: overbought entry on BUY, oversold on SELL, weak trend, or contradictory indicators."
    )
    try:
        resp = _claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # Extract JSON even if wrapped in markdown
        if "```" in text:
            text = text.split("```")[1].strip().lstrip("json").strip()
        result = json.loads(text)
        approved = result.get("approve", True)
        reason   = result.get("reason", "")
        if not approved:
            print(f"    🤖 Claude REJECTED: {reason}")
        return approved
    except Exception as e:
        print(f"    [Claude] review failed ({e}) — passing signal through")
        return True


class ApexBot:
    def __init__(self, live_mode: bool = False):
        self.live_mode    = live_mode
        self.fetcher      = MarketDataFetcher(api_key=TWELVE_DATA_KEY)
        # Starting capital = sum of all agent capital allocations
        total_capital = sum(cfg["capital"] for cfg in AGENTS.values())
        self.risk_manager = RiskManager(starting_capital=total_capital)
        self.paper_engine = PaperEngine(
            log_path=str(LOGS_DIR / "paper_trades.jsonl")
        )
        self.executor = self._build_executor()
        self.cycle    = 0
        self.last_heartbeat = 0.0
        self._state: dict = {}

    def _build_executor(self):
        from configs.config import LIGHTER_API_KEY_ID, LIGHTER_API_KEY_SECRET
        if self.live_mode and LIGHTER_API_KEY_ID:
            print("⚡ LIVE MODE — connecting to Lighter.xyz")
            executor = LighterExecutor(
                api_key_id=LIGHTER_API_KEY_ID,
                api_key_secret=LIGHTER_API_KEY_SECRET,
                paper_mode=False,
            )
        else:
            print("📋 PAPER MODE — no real money at risk")
            executor = LighterExecutor(paper_mode=True)
        return executor

    # ── Data fetching ────────────────────────────────────────────────────────

    async def _get_all_data(self) -> dict:
        """Fetch 1h + 4h candles for all unique assets."""
        all_assets = set()
        for cfg in AGENTS.values():
            all_assets.update(cfg["assets"])

        # Toobit uses BTCUSDT format; TwelveData uses BTC/USDT
        data_1h = await self.fetcher.fetch_all_assets(list(all_assets), interval="1h")
        data_4h = await self.fetcher.fetch_all_assets(list(all_assets), interval="4h")
        return {"1h": data_1h, "4h": data_4h}

    # ── Main cycle ───────────────────────────────────────────────────────────

    async def run_cycle(self) -> dict:
        self.cycle += 1
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"\n{'='*58}")
        print(f"  APEX  |  Cycle {self.cycle}  |  {now_str}")
        print(f"  Mode: {'🔴 LIVE' if self.live_mode else '📋 PAPER'}")
        print(f"{'='*58}")

        if not in_session():
            print("  ⏸  Outside trading hours — skipping")
            return {}

        data = await self._get_all_data()
        data_1h = data["1h"]
        data_4h = data["4h"]

        if not data_1h:
            print("  ⚠️  No market data received — check API key / credits")
            return {}

        signals_fired  = 0
        cycle_results  = {}

        for agent_name, cfg in AGENTS.items():
            analyzer = ANALYZERS[agent_name]
            capital  = cfg["capital"]
            agent_signals = []

            for asset in cfg["assets"]:
                df    = data_1h.get(asset)
                df_4h = data_4h.get(asset)

                if df is None or df.empty:
                    print(f"  {agent_name}/{asset}: no data")
                    continue

                try:
                    result = analyzer(df, df_4h)
                except Exception as e:
                    print(f"  {agent_name}/{asset}: analyzer error — {e}")
                    continue

                if not result or result.get("signal") in ("NONE", None):
                    continue

                signal   = result["signal"]
                strength = result.get("strength", 0.0)

                # ── Strength gate ────────────────────────────────────────────
                if strength < RISK["min_signal_strength"]:
                    print(f"  {agent_name}/{asset}: signal too weak ({strength:.2f} < {RISK['min_signal_strength']})")
                    continue

                # ── Risk gate ────────────────────────────────────────────────
                adx_score = result.get("indicators", {}).get("adx", 50)
                can_trade, reason = self.risk_manager.can_trade(agent_name, float(adx_score))
                if not can_trade:
                    print(f"  {agent_name}/{asset}: BLOCKED — {reason}")
                    continue

                # ── Reward:Risk gate ─────────────────────────────────────────
                entry_price    = float(df["close"].iloc[-1])
                stop_pct       = result.get("stop_loss_pct", 5.0) / 100
                stop_price     = (entry_price * (1 - stop_pct)
                                  if signal == "BUY"
                                  else entry_price * (1 + stop_pct))
                take_profit    = (entry_price * (1 + stop_pct * RISK["min_rr_ratio"])
                                  if signal == "BUY"
                                  else entry_price * (1 - stop_pct * RISK["min_rr_ratio"]))
                rr_ratio       = RISK["min_rr_ratio"]

                # ── Claude AI review (optional) ──────────────────────────────
                review_data = {
                    "agent": agent_name, "asset": asset,
                    "signal": signal, "strength": strength,
                    "indicators": result.get("indicators", {}),
                }
                if strength >= 0.70 and not claude_review(review_data):
                    continue

                # ── Execute ──────────────────────────────────────────────────
                amount = capital * (RISK["max_risk_pct"] / 100)
                trade  = self.paper_engine.open_trade(
                    agent=agent_name, asset=asset,
                    direction=signal, entry_price=entry_price,
                    amount=amount, strategy=cfg["type"],
                    stop_loss=round(stop_price, 6),
                    notes=(f"strength={strength}, "
                           f"stop={stop_price:.4f}, tp={take_profit:.4f}"),
                )

                signals_fired += 1
                agent_signals.append({
                    "agent": agent_name, "asset": asset,
                    "signal": signal, "strength": strength,
                    "entry_price": entry_price,
                    "stop_loss": round(stop_price, 6),
                    "take_profit": round(take_profit, 6),
                    "trade_id": trade.trade_id,
                    "indicators": result.get("indicators", {}),
                })

                ind = result.get("indicators", {})
                ind_str = ", ".join(
                    f"{k}={v}" for k, v in ind.items()
                    if isinstance(v, (int, float, str)) and k != "reason"
                )
                print(f"  ✅ {agent_name} | {asset} | {signal} | "
                      f"strength={strength:.2f} | entry={entry_price:.4f}")
                print(f"     stop={stop_price:.4f}  tp={take_profit:.4f}")
                if ind_str:
                    print(f"     {ind_str}")

            cycle_results[agent_name] = agent_signals

        # ── Check stop losses ─────────────────────────────────────────────────
        current_prices = {
            sym: float(df["close"].iloc[-1])
            for sym, df in data_1h.items()
            if not df.empty
        }
        stopped = self.paper_engine.check_stop_losses(current_prices) or []
        for stop in stopped:
            pnl_sign = "+" if stop.get("pnl", 0) >= 0 else ""
            print(f"  ⛔ STOP: {stop['agent']} {stop['asset']} "
                  f"@ {stop['exit_price']:.4f}  "
                  f"pnl={pnl_sign}{stop.get('pnl', 0):.2f}")
            pnl = stop.get("pnl", 0.0) or 0.0
            if stop.get("status") == "LOSS":
                self.risk_manager.record_loss(stop["agent"], pnl_usd=pnl)
            else:
                self.risk_manager.record_win(stop["agent"],  pnl_usd=pnl)

        # ── Summary ───────────────────────────────────────────────────────────
        stats = self.paper_engine.get_agent_stats()
        print(f"\n  Signals: {signals_fired}  |  "
              f"Trades: {stats['total_trades']} total / {stats['open']} open  |  "
              f"WR: {stats['win_rate']}%  |  PnL: ${stats['total_pnl']:.2f}")

        # ── Persist state ─────────────────────────────────────────────────────
        self._save_state(stats, cycle_results)

        return cycle_results

    def _save_state(self, stats: dict, last_cycle: dict):
        state = {
            "updated_at":  datetime.now(timezone.utc).isoformat(),
            "mode":        "live" if self.live_mode else "paper",
            "cycle":       self.cycle,
            "stats":       stats,
            "last_signals": last_cycle,
        }
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def get_report(self) -> dict:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode":         "live" if self.live_mode else "paper",
            "cycle":        self.cycle,
            "global":       self.paper_engine.get_agent_stats(),
            "agents": {
                name: self.paper_engine.get_agent_stats(name)
                for name in AGENTS
            },
        }


# ── Entry point ───────────────────────────────────────────────────────────────

async def _run(args):
    bot = ApexBot(live_mode=args.live)

    if args.once:
        await bot.run_cycle()
        return

    print(f"APEX starting — scan every {SCAN_INTERVAL_SECONDS}s")
    print("Press Ctrl+C to stop\n")

    while True:
        try:
            await bot.run_cycle()
        except Exception as e:
            print(f"  ⚠️  Cycle error: {e}")

        # Heartbeat every hour
        if time.time() - bot.last_heartbeat > HEARTBEAT_MINUTES * 60:
            bot.last_heartbeat = time.time()
            try:
                from telegram.bot import send_heartbeat
                await send_heartbeat(bot.get_report())
            except Exception:
                pass

        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


def main():
    parser = argparse.ArgumentParser(description="APEX Trading Bot")
    parser.add_argument("--live",     action="store_true",
                        help="Enable live trading on Toobit (default: paper)")
    parser.add_argument("--once",     action="store_true",
                        help="Run one cycle then exit")
    parser.add_argument("--backtest", action="store_true",
                        help="Backtest mode (coming soon)")
    args = parser.parse_args()

    if args.live and not os.getenv("LIGHTER_API_KEY_ID"):
        print("ERROR: --live requires LIGHTER_API_KEY_ID environment variable")
        sys.exit(1)

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
