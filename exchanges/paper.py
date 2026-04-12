"""
Paper Execution Engine - Simulates broker trades with live market data.
Uses TwelveData API for real prices.
"""
import time
import aiohttp
import asyncio
from datetime import datetime, timezone

class PaperExecutor:
    """Paper trading mock broker with real market data."""

    def __init__(self, api_keys=None):
        self.name = "PAPER"
        self.paper_mode = True
        self.is_connected = True
        self.balances = {}
        self.api_keys = api_keys or {}
        self.trades = []

    async def connect(self):
        self.is_connected = True
        return True

    async def get_price(self, symbol):
        """Get current market price via TwelveData."""
        api_key = self.api_keys.get("twelvedata", "")
        if not api_key:
            return None

        url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if "price" in data:
                    return float(data["price"])
        return None

    async def place_order(self, symbol, side, amount, order_type="MARKET"):
        """Simulated order with current market price."""
        price = await self.get_price(symbol)
        if price is None:
            return {"status": "ERROR", "error": "Could not fetch price"}

        trade = {
            "id": f"paper_{int(time.time()*1000)}",
            "broker": "PAPER",
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "entry_price": price,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "status": "OPEN",
            "exit_price": None,
            "pnl": 0.0,
        }
        self.trades.append(trade)
        return {"status": "FILLED", "trade": trade}

    async def get_balance(self):
        return {"status": "OK", "balances": self.balances}

    async def get_open_positions(self):
        return [t for t in self.trades if t["status"] == "OPEN"]

    async def close_position(self, symbol, trade_id=None):
        price = await self.get_price(symbol)
        if price is None:
            return None

        for trade in self.trades:
            if trade["symbol"] == symbol and trade["status"] == "OPEN":
                if trade_id and trade["id"] != trade_id:
                    continue

                trade["exit_price"] = price
                trade["exit_time"] = datetime.now(timezone.utc).isoformat()

                if trade["side"] == "BUY":
                    trade["pnl"] = (price - trade["entry_price"]) / trade["entry_price"] * trade["amount"]
                else:
                    trade["pnl"] = (trade["entry_price"] - price) / trade["entry_price"] * trade["amount"]

                trade["status"] = "CLOSED"
                trade["closed_at"] = datetime.now(timezone.utc).isoformat()
                return trade

        return None

    async def get_historical_data(self, symbol, interval="1h", limit=200):
        """Get historical data for backtesting."""
        api_key = self.api_keys.get("twelvedata", "")
        if not api_key:
            return None

        url = (f"https://api.twelvedata.com/time_series?"
               f"symbol={symbol}&interval={interval}&outputsize={limit}&apikey={api_key}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if "values" in data:
                    return data["values"]
        return None
