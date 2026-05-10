"""
Historical data loader.

Downloads OHLCV candles and funding rates from Binance's free public archive
(data.binance.vision) and stores them as parquet under data/historical/.

The archive covers BTCUSDT, ETHUSDT, SOLUSDT and ~100 other USDT-margined
perpetuals back to 2019, on every standard timeframe (1m, 5m, 15m, 1h, 4h, 1d).

We treat Binance as a *proxy* for Hyperliquid — funding and price are >99%
correlated on the majors, and Hyperliquid does not publish a candle archive.
"""
from data_loader.binance_downloader import (
    download_klines,
    download_funding,
    HISTORICAL_DIR,
)

__all__ = ["download_klines", "download_funding", "HISTORICAL_DIR"]
