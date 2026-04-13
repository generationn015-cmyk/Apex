"""
Paper Trading Engine - Simulates all agent trades with real market data.
Tracks entry/exit, PnL, win rate, and strategy performance metrics.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

class PaperTrade:
    """Represents a single paper trade position."""
    
    def __init__(self, agent_name, asset, direction, entry_price,
                 amount, strategy_type, broker="paper"):
        self.trade_id = f"{agent_name}_{int(time.time()*1000)}"
        self.agent = agent_name
        self.asset = asset
        self.direction = direction  # BUY or SELL
        self.entry_price = float(entry_price)
        self.exit_price = None
        self.amount = float(amount)
        self.strategy = strategy_type
        self.broker = broker
        self.opened_at = datetime.now(timezone.utc).isoformat()
        self.closed_at = None
        self.stop_loss = None
        self.take_profit = None
        self.pnl = 0.0
        self.status = "OPEN"  # OPEN, WIN, LOSS, STOPPED, TIMEOUT
        self.notes = ""

    def to_dict(self):
        return {
            "trade_id": self.trade_id,
            "agent": self.agent,
            "asset": self.asset,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "amount": self.amount,
            "strategy": self.strategy,
            "broker": self.broker,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "pnl": self.pnl,
            "status": self.status,
            "notes": self.notes,
        }

    def close(self, exit_price, reason="", notes=""):
        self.exit_price = float(exit_price)
        self.closed_at = datetime.now(timezone.utc).isoformat()
        self.notes = notes
        
        if self.direction == "BUY":
            self.pnl = (self.exit_price - self.entry_price) / self.entry_price * self.amount
            self.status = "WIN" if self.pnl >= 0 else "LOSS"
        else:  # SELL
            self.pnl = (self.entry_price - self.exit_price) / self.entry_price * self.amount
            self.status = "WIN" if self.pnl >= 0 else "LOSS"
        return self.to_dict()


class PaperEngine:
    """Manages all paper trades, tracks performance, logs results."""
    
    def __init__(self, log_path="paper/paper_trades.jsonl"):
        self.trades: dict[str, PaperTrade] = {}
        self.log_path = Path(log_path)
        self._load_existing()

    def _load_existing(self):
        if self.log_path.exists():
            for line in self.log_path.read_text().strip().split("\n"):
                if line.strip():
                    try:
                        data = json.loads(line)
                        t = PaperTrade.__new__(PaperTrade)
                        t.__dict__.update(data)
                        self.trades[t.trade_id] = t
                    except:
                        pass

    def open_trade(self, agent, asset, direction, entry_price,
                    amount, strategy, broker="paper", notes="",
                    stop_loss=None, take_profit=None):
        trade = PaperTrade(agent, asset, direction, entry_price, amount, strategy, broker)
        trade.notes = notes
        trade.stop_loss = stop_loss
        trade.take_profit = take_profit
        self.trades[trade.trade_id] = trade
        self._append_trade(trade)
        return trade

    def close_trade(self, trade_id, exit_price, reason=""):
        if trade_id not in self.trades:
            return None
        trade = self.trades[trade_id]
        if trade.status != "OPEN":
            return None
        result = trade.close(exit_price, reason=reason)
        self._append_trade(trade)
        return result

    def check_exits(self, current_prices: dict, max_age_hours: float = 48.0):
        """Check all open trades for SL, TP, and timeout exits."""
        HARD_STOP_LOSS_PCT = 0.05  # 5% default stop loss
        now = datetime.now(timezone.utc)

        closed = []
        # snapshot keys to avoid dict-size-change during iteration
        for tid in list(self.trades.keys()):
            trade = self.trades[tid]
            if trade.status != "OPEN":
                continue
            price = current_prices.get(trade.asset)
            if price is None:
                continue

            # Ensure stop loss is set
            if trade.stop_loss is None:
                if trade.direction == "BUY":
                    trade.stop_loss = trade.entry_price * (1 - HARD_STOP_LOSS_PCT)
                else:
                    trade.stop_loss = trade.entry_price * (1 + HARD_STOP_LOSS_PCT)

            # Take profit hit
            if trade.take_profit is not None:
                tp_hit = (
                    (trade.direction == "BUY"  and price >= trade.take_profit) or
                    (trade.direction == "SELL" and price <= trade.take_profit)
                )
                if tp_hit:
                    result = self.close_trade(tid, price, reason="TAKE_PROFIT")
                    if result:
                        closed.append(result)
                    continue

            # Stop loss hit
            sl_hit = (
                (trade.direction == "BUY"  and price <= trade.stop_loss) or
                (trade.direction == "SELL" and price >= trade.stop_loss)
            )
            if sl_hit:
                result = self.close_trade(tid, price, reason="STOP_LOSS")
                if result:
                    closed.append(result)
                continue

            # Timeout — close stale positions older than max_age_hours
            try:
                opened_at = datetime.fromisoformat(trade.opened_at)
                age_hours = (now - opened_at).total_seconds() / 3600.0
                if age_hours > max_age_hours:
                    result = self.close_trade(tid, price, reason="TIMEOUT")
                    if result:
                        closed.append(result)
            except Exception:
                pass

        return closed

    # backwards-compat alias
    def check_stop_losses(self, current_prices: dict):
        return self.check_exits(current_prices)

    def _append_trade(self, trade):
        with open(self.log_path, "a") as f:
            f.write(json.dumps(trade.to_dict()) + "\n")

    def get_agent_stats(self, agent_name=None, current_prices=None):
        trades = list(self.trades.values())
        if agent_name:
            trades = [t for t in trades if t.agent == agent_name]

        closed = [t for t in trades if t.status != "OPEN"]
        wins = [t for t in closed if t.pnl >= 0]
        losses = [t for t in closed if t.pnl < 0]

        total_pnl = sum(t.pnl for t in closed)
        win_rate = (len(wins) / len(closed) * 100) if closed else 0

        # Unrealized PnL for open positions
        unrealized = 0.0
        if current_prices:
            for t in trades:
                if t.status == "OPEN":
                    price = current_prices.get(t.asset)
                    if price:
                        if t.direction == "BUY":
                            unrealized += (price - t.entry_price) / t.entry_price * t.amount
                        else:
                            unrealized += (t.entry_price - price) / t.entry_price * t.amount

        # By asset
        by_asset = {}
        for t in closed:
            a = t.asset
            if a not in by_asset:
                by_asset[a] = {"wins": 0, "losses": 0, "pnl": 0}
            if t.pnl >= 0:
                by_asset[a]["wins"] += 1
            else:
                by_asset[a]["losses"] += 1
            by_asset[a]["pnl"] += t.pnl

        return {
            "total_trades": len(trades),
            "closed": len(closed),
            "open": len(trades) - len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "net_pnl": round(total_pnl + unrealized, 2),
            "by_asset": by_asset,
        }

    def has_open_position(self, agent: str, asset: str) -> bool:
        """Check if an agent already has an open position on an asset."""
        for t in self.trades.values():
            if t.status == "OPEN" and t.agent == agent and t.asset == asset:
                return True
        return False

    def get_open_trades(self, agent_name=None):
        trades = []
        for t in self.trades.values():
            if t.status == "OPEN":
                if agent_name and t.agent != agent_name:
                    continue
                trades.append(t.to_dict())
        return trades
