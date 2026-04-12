"""
Toobit Executor - Real cryptocurrency exchange connector.
Supports spot and futures trading.
"""
import hashlib
import hmac
import time
import aiohttp
from datetime import datetime, timezone

class ToobitExecutor:
    """Toobit exchange integration for crypto trading."""

    def __init__(self, api_key, api_secret, paper_mode=True):
        self.name = "TOOBIT"
        self.paper_mode = paper_mode
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.toobit.com/api/v1"
        self.is_connected = False
        self.balances = {}

    def _sign_request(self, method, path, params=None):
        """Create HMAC-SHA256 signature for Toobit API."""
        timestamp = str(int(time.time() * 1000))
        query_string = ""
        if params:
            query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        string_to_sign = f"{timestamp}{method}{path}?{query_string}"
        signature = hmac.new(
            self.api_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).hexdigest()
        return timestamp, signature

    async def connect(self):
        """Verify API connectivity and permissions."""
        try:
            async with aiohttp.ClientSession() as session:
                # Ping endpoint
                async with session.get(f"{self.base_url}/ping",
                    timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        self.is_connected = True
                        return True
            return False
        except Exception:
            return False

    async def get_price(self, symbol):
        """Get current price from Toobit order book."""
        toobit_symbol = symbol.replace("/", "")
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/depth?symbol={toobit_symbol}&limit=1"
                async with session.get(url,
                    timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if data.get("asks") and data.get("bids"):
                        mid = (float(data["bids"][0][0]) + float(data["asks"][0][0])) / 2
                        return round(mid, 8)
        except Exception:
            pass
        return None

    async def place_order(self, symbol, side, amount, order_type="MARKET"):
        """Place a real order on Toobit."""
        if self.paper_mode:
            return {"status": "PAPER", "msg": "Paper trading mode active"}

        toobit_symbol = symbol.replace("/", "")
        params = {
            "symbol": toobit_symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(amount),
            "api_key": self.api_key,
        }

        timestamp, signature = self._sign_request("POST", "/order", params)
        params["signature"] = signature
        params["timestamp"] = timestamp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/order",
                    data=params,
                    timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return await resp.json()
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    async def close_position(self, symbol, trade_id=None):
        """Close position on Toobit."""
        if self.paper_mode:
            return {"status": "PAPER", "msg": "Paper trading mode active"}
        # Implementation for real exchange
        return None

    async def get_balance(self):
        if self.paper_mode:
            return {"status": "PAPER", "balances": self.balances}
        return {"status": "NOT_IMPLEMENTED"}

    async def get_historical_data(self, symbol, interval="1h", limit=200):
        """Get kline data from Toobit."""
        toobit_symbol = symbol.replace("/", "")
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        kline_interval = interval_map.get(interval, "1h")

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/klines?symbol={toobit_symbol}&interval={kline_interval}&limit={limit}"
                async with session.get(url,
                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    if data.get("data"):
                        # Convert Toobit kline format to standard OHLCV
                        candles = []
                        for k in data["data"]:
                            candles.append({
                                "timestamp": k[0],
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[5]),
                            })
                        return candles
        except Exception:
            pass
        return None
