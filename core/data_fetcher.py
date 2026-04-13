"""
Market Data Fetcher — OHLCV for all APEX agents.
Primary:  Binance public REST API (free, full OHLCV with volume)
Fallback: TwelveData (for non-crypto symbols that Binance doesn't have)
"""
import asyncio
import aiohttp
import pandas as pd
import time

# Binance symbol map: internal symbol → BTCUSDT format
_BINANCE_SYM = {
    "BTC/USDT": "BTCUSDT",
    "ETH/USDT": "ETHUSDT",
    "SOL/USDT": "SOLUSDT",
    "BTC-PERP": "BTCUSDT",
    "ETH-PERP": "ETHUSDT",
    "SOL-PERP": "SOLUSDT",
}

# Interval map: apex notation → Binance notation
_BINANCE_INTERVAL = {
    "1min":  "1m",
    "5min":  "5m",
    "15min": "15m",
    "30min": "30m",
    "1h":    "1h",
    "4h":    "4h",
    "1d":    "1d",
}

# TwelveData fallback (non-crypto like forex)
_TD_SYMBOL = {
    "BTC/USDT": "BTC/USD",
    "ETH/USDT": "ETH/USD",
    "SOL/USDT": "SOL/USD",
}
_BINANCE_URLS = [
    "https://api.binance.us/api/v3/klines",      # US-accessible
    "https://api.binance.com/api/v3/klines",      # global (geo-blocked in US)
]


class MarketDataFetcher:
    """
    Fetches OHLCV candles.
    Crypto pairs → Binance public API (free, includes volume).
    Others → TwelveData with api_key.
    """

    def __init__(self, api_key: str = ""):
        self.api_key  = api_key
        self._td_base = "https://api.twelvedata.com"
        self._cache:  dict = {}   # cache_key → {"df": df, "time": float}
        self.requests_made = 0
        self._last_req     = 0.0

    # ── Binance (primary for all crypto) ─────────────────────────────────────

    async def _binance_ohlcv(self, symbol: str, interval: str,
                              limit: int, session: aiohttp.ClientSession) -> pd.DataFrame | None:
        bi_sym = _BINANCE_SYM.get(symbol)
        if not bi_sym:
            return None
        bi_int = _BINANCE_INTERVAL.get(interval, interval)

        # Retry up to 3 times with backoff
        for attempt in range(3):
            for base_url in _BINANCE_URLS:
                url = f"{base_url}?symbol={bi_sym}&interval={bi_int}&limit={limit}"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                        data = await r.json()
                        if not isinstance(data, list):
                            print(f"  [Binance] {bi_sym} non-list response from {base_url}: {str(data)[:100]}")
                            continue  # try next URL
                        self.requests_made += 1
                        df = pd.DataFrame([
                            {
                                "datetime": str(pd.to_datetime(k[0], unit="ms")),
                                "open":     float(k[1]),
                                "high":     float(k[2]),
                                "low":      float(k[3]),
                                "close":    float(k[4]),
                                "volume":   float(k[5]),
                            }
                            for k in data
                        ])
                        return df
                except Exception as e:
                    print(f"  [Binance] {bi_sym} fetch error ({base_url}): {e}")
                    continue  # try next URL
            # Backoff before retry
            if attempt < 2:
                await asyncio.sleep(2 * (attempt + 1))
        return None

    # ── TwelveData (fallback / non-crypto) ───────────────────────────────────

    async def _td_ohlcv(self, symbol: str, interval: str,
                        outputsize: int, session: aiohttp.ClientSession) -> pd.DataFrame | None:
        td_sym = _TD_SYMBOL.get(symbol, symbol)
        url    = (f"{self._td_base}/time_series?"
                  f"symbol={td_sym}&interval={interval}&outputsize={outputsize}&apikey={self.api_key}")
        now = time.time()
        if now - self._last_req < 0.5:
            await asyncio.sleep(0.5)
        self._last_req = time.time()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                if "values" not in data:
                    return None
                self.requests_made += 1
                df = pd.DataFrame(data["values"])
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                if "volume" not in df.columns:
                    df["volume"] = 1.0   # synthetic — TwelveData crypto omits volume
                df = df.sort_values("datetime").reset_index(drop=True)
                return df
        except Exception as e:
            print(f"  [Data] TwelveData fetch error ({symbol}): {e}")
            return None

    # ── Public interface ──────────────────────────────────────────────────────

    async def get_ohlcv(self, symbol: str, interval: str = "1h",
                        outputsize: int = 200) -> pd.DataFrame | None:
        cache_key = f"{symbol}_{interval}_{outputsize}"
        now       = time.time()
        ttl       = 60 if "1min" in interval else 300
        cached    = self._cache.get(cache_key)
        if cached and (now - cached["time"]) < ttl:
            return cached["df"]

        async with aiohttp.ClientSession() as session:
            # Prefer Binance for crypto (has volume)
            df = await self._binance_ohlcv(symbol, interval, outputsize, session)
            # Fallback to TwelveData
            if df is None or df.empty:
                df = await self._td_ohlcv(symbol, interval, outputsize, session)

        if df is None or df.empty:
            return None

        self._cache[cache_key] = {"df": df, "time": now}
        return df

    async def fetch_all_assets(self, assets: list, interval: str = "1h") -> dict:
        """Fetch data for all assets in parallel."""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for sym in assets:
                tasks.append(self._fetch_one(sym, interval, 200, session))
            results = await asyncio.gather(*tasks, return_exceptions=True)

        data = {}
        for sym, result in zip(assets, results):
            if isinstance(result, pd.DataFrame) and not result.empty:
                data[sym] = result
            elif isinstance(result, Exception):
                print(f"  [Data] {sym}: {result}")
        return data

    async def _fetch_one(self, symbol: str, interval: str, limit: int,
                         session: aiohttp.ClientSession) -> pd.DataFrame | None:
        cache_key = f"{symbol}_{interval}_{limit}"
        now       = time.time()
        ttl       = 60 if "1min" in interval else 300
        cached    = self._cache.get(cache_key)
        if cached and (now - cached["time"]) < ttl:
            return cached["df"]

        df = await self._binance_ohlcv(symbol, interval, limit, session)
        if df is None or df.empty:
            df = await self._td_ohlcv(symbol, interval, limit, session)
        if df is not None and not df.empty:
            self._cache[cache_key] = {"df": df, "time": now}
        return df

    async def get_current_price(self, symbol: str) -> float | None:
        async with aiohttp.ClientSession() as session:
            bi_sym = _BINANCE_SYM.get(symbol, symbol.replace("/", ""))
            url    = f"https://api.binance.com/api/v3/ticker/price?symbol={bi_sym}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    data = await r.json()
                    if "price" in data:
                        return float(data["price"])
            except Exception:
                pass
        return None

    def get_stats(self) -> dict:
        return {
            "requests_made":   self.requests_made,
            "symbols_cached":  len(self._cache),
        }
