"""Historical data ingestion. Alpaca primary, yfinance fallback. Parquet cache."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from ..config.models import AlpacaConfig, DataConfig

log = logging.getLogger("apex2.data")


class DataSource:
    """Unified bar fetcher with disk cache.

    Cached files: <cache_dir>/<source>/<symbol>_<timeframe>.parquet
    Cache strategy: load existing, fetch only the gap, append, dedupe, write back.
    """

    def __init__(self, cfg: DataConfig, alpaca: AlpacaConfig | None = None):
        self.cfg = cfg
        self.alpaca = alpaca
        self.cache_root = Path(cfg.cache_dir)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, source: str, symbol: str, timeframe: str) -> Path:
        d = self.cache_root / source
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{symbol}_{timeframe}.parquet"

    def get_bars(
        self,
        symbol: str,
        start: date | datetime,
        end: date | datetime,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        """Return OHLCV DataFrame indexed by tz-naive timestamp.

        Columns: open, high, low, close, volume.
        """
        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()

        sources = [self.cfg.primary_source]
        if self.cfg.fallback_source != "none" and self.cfg.fallback_source != self.cfg.primary_source:
            sources.append(self.cfg.fallback_source)

        last_err: Exception | None = None
        for source in sources:
            try:
                df = self._get_with_cache(source, symbol, start, end, timeframe)
                if not df.empty:
                    return df
            except Exception as e:
                log.warning("Source %s failed for %s: %s", source, symbol, e)
                last_err = e
        if last_err:
            raise last_err
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _get_with_cache(
        self, source: str, symbol: str, start: date, end: date, timeframe: str
    ) -> pd.DataFrame:
        cache_path = self._cache_path(source, symbol, timeframe)
        cached = pd.DataFrame()
        if cache_path.exists():
            cached = pd.read_parquet(cache_path)

        need_start = start
        if not cached.empty:
            cached_max = cached.index.max().date()
            if cached_max >= end:
                return cached.loc[
                    (cached.index >= pd.Timestamp(start)) & (cached.index <= pd.Timestamp(end))
                ]
            need_start = cached_max + timedelta(days=1)

        fresh = self._fetch(source, symbol, need_start, end, timeframe)

        combined = pd.concat([cached, fresh]) if not cached.empty else fresh
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()

        if not combined.empty:
            combined.to_parquet(cache_path, compression=self.cfg.parquet_compression)

        if combined.empty:
            return combined
        return combined.loc[
            (combined.index >= pd.Timestamp(start)) & (combined.index <= pd.Timestamp(end))
        ]

    def _fetch(self, source: str, symbol: str, start: date, end: date, timeframe: str) -> pd.DataFrame:
        if source == "alpaca":
            return self._fetch_alpaca(symbol, start, end, timeframe)
        if source == "yfinance":
            return self._fetch_yfinance(symbol, start, end, timeframe)
        raise ValueError(f"unknown source: {source}")

    def _fetch_alpaca(self, symbol: str, start: date, end: date, timeframe: str) -> pd.DataFrame:
        if not self.alpaca or not self.alpaca.api_key:
            raise RuntimeError("alpaca credentials not configured")
        from alpaca.data.historical.stock import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf_map = {
            "1m": TimeFrame(1, TimeFrameUnit.Minute),
            "5m": TimeFrame(5, TimeFrameUnit.Minute),
            "15m": TimeFrame(15, TimeFrameUnit.Minute),
            "1h": TimeFrame(1, TimeFrameUnit.Hour),
            "1d": TimeFrame(1, TimeFrameUnit.Day),
        }
        tf = tf_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Day))
        client = StockHistoricalDataClient(
            api_key=self.alpaca.api_key, secret_key=self.alpaca.api_secret
        )
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start, end=end)
        bars = client.get_stock_bars(req).df
        if bars.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if "symbol" in bars.index.names:
            bars = bars.xs(symbol, level="symbol")
        bars.index = bars.index.tz_convert(None) if bars.index.tz is not None else bars.index
        return bars[["open", "high", "low", "close", "volume"]].astype(float)

    def _fetch_yfinance(self, symbol: str, start: date, end: date, timeframe: str) -> pd.DataFrame:
        import yfinance as yf

        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1d"}
        interval = interval_map.get(timeframe, "1d")
        df = yf.download(
            symbol,
            start=start,
            end=end + timedelta(days=1),
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)
        df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
        return df[["open", "high", "low", "close", "volume"]].astype(float)
