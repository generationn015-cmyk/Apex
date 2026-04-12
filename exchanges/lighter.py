"""
APEX — Lighter.xyz Executor
Perpetual futures: BTC-PERP, ETH-PERP, SOL-PERP

Why Lighter over Toobit:
  - Zero fees (vs 0.1%+ on CEX)
  - On-chain — you hold your private key
  - Python SDK: lighter-sdk
  - Same markets we already trade (BTC/ETH/SOL)

Credentials (set in .env):
  LIGHTER_API_KEY_ID     — from app.lighter.xyz → API Keys
  LIGHTER_API_KEY_SECRET — from app.lighter.xyz → API Keys

Paper mode is the default. Set TRADING_MODE=live to execute real orders.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("apex.lighter")

# Symbol map: apex internal → Lighter market name
SYMBOL_MAP = {
    "BTC/USDT":  "BTC-PERP",
    "ETH/USDT":  "ETH-PERP",
    "SOL/USDT":  "SOL-PERP",
    "BTC-PERP":  "BTC-PERP",
    "ETH-PERP":  "ETH-PERP",
    "SOL-PERP":  "SOL-PERP",
}


class LighterExecutor:
    """
    Live executor for Lighter.xyz perpetual futures.
    Wraps lighter-sdk with paper fallback and price fetching.
    """

    def __init__(self, api_key_id: str = "", api_key_secret: str = "",
                 paper_mode: bool = True):
        self.api_key_id     = api_key_id or os.getenv("LIGHTER_API_KEY_ID", "")
        self.api_key_secret = api_key_secret or os.getenv("LIGHTER_API_KEY_SECRET", "")
        self.paper_mode     = paper_mode
        self.name           = "LIGHTER"
        self.is_connected   = False
        self._client        = None   # lighter-sdk client
        self._trades: list  = []

    async def connect(self) -> bool:
        """Initialise lighter-sdk client and verify connectivity."""
        if self.paper_mode:
            self.is_connected = True
            logger.info("Lighter: paper mode — no real connection needed")
            return True

        if not self.api_key_id or not self.api_key_secret:
            logger.error("Lighter: missing API credentials (LIGHTER_API_KEY_ID / LIGHTER_API_KEY_SECRET)")
            return False

        try:
            from lighter import Client                     # lighter-sdk
            self._client = Client(
                api_key_id=self.api_key_id,
                api_key_secret=self.api_key_secret,
            )
            # Ping — fetch account info to verify keys
            account = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_account
            )
            self.is_connected = True
            logger.info(f"Lighter connected — account: {account}")
            return True
        except ImportError:
            logger.error("lighter-sdk not installed. Run: pip install lighter-sdk")
            return False
        except Exception as e:
            logger.error(f"Lighter connection failed: {e}")
            return False

    def _lighter_symbol(self, symbol: str) -> str:
        return SYMBOL_MAP.get(symbol, symbol)

    async def get_price(self, symbol: str) -> Optional[float]:
        """
        Fetch mid-price from Lighter order book.
        Falls back to Binance public API if lighter unavailable.
        """
        lighter_sym = self._lighter_symbol(symbol)

        # Try Lighter REST
        if self._client and not self.paper_mode:
            try:
                book = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._client.get_orderbook(lighter_sym)
                )
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                if bids and asks:
                    return round((float(bids[0][0]) + float(asks[0][0])) / 2, 6)
            except Exception as e:
                logger.warning(f"Lighter price fetch failed ({e}), using Binance fallback")

        # Binance public fallback (no auth needed)
        return await self._binance_price(symbol)

    async def _binance_price(self, symbol: str) -> Optional[float]:
        """Public Binance ticker — no API key required."""
        import aiohttp
        binance_sym = symbol.replace("/", "").replace("-PERP", "USDT")
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={binance_sym}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    data = await r.json()
                    if "price" in data:
                        return float(data["price"])
        except Exception:
            pass
        return None

    async def place_order(self, symbol: str, side: str, amount: float,
                          order_type: str = "MARKET",
                          leverage: int = 1) -> dict:
        """
        Place a perpetual futures order on Lighter.
        side: "BUY" (long) or "SELL" (short)
        amount: position size in USD
        leverage: 1–5 (default 1 = no leverage — safe for first live run)
        """
        lighter_sym = self._lighter_symbol(symbol)
        price = await self.get_price(symbol)

        if price is None:
            return {"status": "ERROR", "error": "Could not fetch price"}

        # Size in contracts (1 BTC-PERP contract = $1 notional on Lighter)
        notional = amount * leverage
        contracts = notional / price

        trade = {
            "id":          f"lighter_{int(time.time()*1000)}",
            "exchange":    "LIGHTER",
            "symbol":      lighter_sym,
            "side":        side.upper(),
            "amount_usd":  amount,
            "leverage":    leverage,
            "notional":    round(notional, 2),
            "contracts":   round(contracts, 6),
            "entry_price": price,
            "entry_time":  datetime.now(timezone.utc).isoformat(),
            "status":      "OPEN",
            "exit_price":  None,
            "pnl":         0.0,
            "fees":        0.0,   # Lighter = zero fees
        }

        if self.paper_mode:
            self._trades.append(trade)
            logger.info(f"PAPER {side} {contracts:.6f} {lighter_sym} @ {price:.4f} (${notional:.2f} notional)")
            return {"status": "FILLED", "trade": trade}

        # Live execution via lighter-sdk
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.place_order(
                    market=lighter_sym,
                    side=side.upper(),
                    size=contracts,
                    order_type=order_type.lower(),
                    leverage=leverage,
                )
            )
            trade["id"] = result.get("order_id", trade["id"])
            trade["status"] = "FILLED" if result.get("status") == "filled" else "PENDING"
            self._trades.append(trade)
            logger.info(f"LIVE {side} {contracts:.6f} {lighter_sym} @ {price:.4f} — id={trade['id']}")
            return {"status": "FILLED", "trade": trade}
        except Exception as e:
            logger.error(f"Lighter order failed: {e}")
            return {"status": "ERROR", "error": str(e)}

    async def close_position(self, symbol: str, trade_id: str = None) -> Optional[dict]:
        """Close an open position at current market price."""
        price = await self.get_price(symbol)
        if price is None:
            return None

        lighter_sym = self._lighter_symbol(symbol)
        for trade in self._trades:
            if trade["symbol"] == lighter_sym and trade["status"] == "OPEN":
                if trade_id and trade["id"] != trade_id:
                    continue

                trade["exit_price"] = price
                trade["exit_time"]  = datetime.now(timezone.utc).isoformat()
                trade["status"]     = "CLOSED"
                trade["fees"]       = 0.0   # Zero fees — competitive advantage

                if trade["side"] == "BUY":
                    trade["pnl"] = (price - trade["entry_price"]) / trade["entry_price"] \
                                   * trade["notional"]
                else:
                    trade["pnl"] = (trade["entry_price"] - price) / trade["entry_price"] \
                                   * trade["notional"]

                logger.info(f"Closed {lighter_sym} pnl={trade['pnl']:+.4f}")
                return trade
        return None

    async def get_balance(self) -> dict:
        if self.paper_mode or not self._client:
            pnl = sum(t["pnl"] for t in self._trades if t["status"] == "CLOSED")
            return {"status": "OK", "mode": "paper", "realized_pnl": round(pnl, 4)}

        try:
            acct = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_account
            )
            return {"status": "OK", "mode": "live", "account": acct}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    async def get_open_positions(self) -> list:
        return [t for t in self._trades if t["status"] == "OPEN"]

    async def get_historical_data(self, symbol: str, interval: str = "1h",
                                  limit: int = 200) -> Optional[list]:
        """Fetch candles via Lighter or Binance fallback."""
        lighter_sym = self._lighter_symbol(symbol)

        if self._client and not self.paper_mode:
            try:
                candles = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._client.get_candles(lighter_sym, interval, limit)
                )
                if candles:
                    return candles
            except Exception:
                pass

        return await self._binance_candles(symbol, interval, limit)

    async def _binance_candles(self, symbol: str, interval: str,
                               limit: int) -> Optional[list]:
        import aiohttp
        binance_sym = symbol.replace("/", "").replace("-PERP", "USDT")
        interval_map = {"1h": "1h", "4h": "4h", "15min": "15m",
                        "5min": "5m", "1d": "1d"}
        bi = interval_map.get(interval, "1h")
        url = (f"https://api.binance.com/api/v3/klines"
               f"?symbol={binance_sym}&interval={bi}&limit={limit}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json()
                    return [
                        {"timestamp": k[0], "open": float(k[1]), "high": float(k[2]),
                         "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
                        for k in data
                    ]
        except Exception:
            return None

    def get_stats(self) -> dict:
        closed = [t for t in self._trades if t["status"] == "CLOSED"]
        wins   = [t for t in closed if t["pnl"] > 0]
        return {
            "total_trades": len(self._trades),
            "open":         len([t for t in self._trades if t["status"] == "OPEN"]),
            "closed":       len(closed),
            "wins":         len(wins),
            "losses":       len(closed) - len(wins),
            "win_rate":     round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "total_pnl":    round(sum(t["pnl"] for t in closed), 4),
            "total_fees":   0.0,   # Always zero — Lighter advantage
        }
