"""
Binance public-archive downloader.

Source: https://data.binance.vision/?prefix=data/futures/um/monthly/

We pull *USDT-margined perpetual* (futures/um) monthly zips. Each zip contains
one CSV. We stream the zip in memory, parse the CSV, and append into a single
parquet file per (pair, timeframe).

Resumability: we check which months are already in the parquet file (by
month-start timestamp) and skip those. So you can re-run the downloader to
extend the dataset without re-fetching.

Usage:
    python -m data_loader --pairs BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h --years 2
"""
from __future__ import annotations

import io
import logging
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger("apex.data_loader")

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORICAL_DIR = REPO_ROOT / "data" / "historical"

BINANCE_BASE = "https://data.binance.vision/data/futures/um/monthly"

# Binance kline CSV columns (header is sometimes present, sometimes not — handle both)
KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]
FUNDING_COLS = ["calc_time", "funding_interval_hours", "last_funding_rate"]


def _months_between(start: date, end: date) -> list[tuple[int, int]]:
    """Yield (year, month) pairs from start..end inclusive."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _fetch_zip_csv(url: str, timeout: int = 60) -> pd.DataFrame | None:
    """Download a zip, extract its single CSV, return a DataFrame.

    Returns None on 404 (month not yet published) or transient HTTP error.
    Raises only on programming bugs.
    """
    try:
        r = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        log.warning("network error fetching %s: %s", url, e)
        return None

    if r.status_code == 404:
        log.debug("404 (not published yet): %s", url)
        return None
    if r.status_code != 200:
        log.warning("HTTP %d on %s", r.status_code, url)
        return None

    try:
        zf = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        log.warning("bad zip from %s", url)
        return None

    name = zf.namelist()[0]
    with zf.open(name) as fh:
        # Sniff first byte: if it's a digit, file has no header
        first = fh.read(1)
        fh.seek(0)
        has_header = not first.isdigit()
        return pd.read_csv(fh, header=0 if has_header else None)


def download_klines(
    pair: str,
    timeframe: str,
    years: float = 2.0,
    end: date | None = None,
) -> Path:
    """Download monthly kline zips for one pair/timeframe.

    Stores the result at data/historical/<pair>/<timeframe>.parquet with columns:
        timestamp (int ms, UTC), open, high, low, close, volume

    Resumable: re-running extends the file with any newer months.
    Returns the parquet path.
    """
    end = end or date.today().replace(day=1) - timedelta(days=1)  # last full month
    start = (end.replace(day=1) - timedelta(days=int(365 * years))).replace(day=1)

    out_dir = HISTORICAL_DIR / pair
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{timeframe}.parquet"

    existing = pd.DataFrame()
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        if not existing.empty:
            existing_months = set(
                pd.to_datetime(existing["timestamp"], unit="ms", utc=True)
                .dt.to_period("M").astype(str).unique()
            )
        else:
            existing_months = set()
    else:
        existing_months = set()

    chunks: list[pd.DataFrame] = []
    if not existing.empty:
        chunks.append(existing)

    months = _months_between(start, end)
    log.info(
        "klines %s %s: %d months requested (%s..%s), %d already cached",
        pair, timeframe, len(months), months[0], months[-1], len(existing_months),
    )

    for y, m in months:
        period = f"{y}-{m:02d}"
        if period in existing_months:
            continue
        url = f"{BINANCE_BASE}/klines/{pair}/{timeframe}/{pair}-{timeframe}-{period}.zip"
        df = _fetch_zip_csv(url)
        if df is None or df.empty:
            continue

        if len(df.columns) >= len(KLINE_COLS):
            df = df.iloc[:, : len(KLINE_COLS)]
            df.columns = KLINE_COLS
        else:
            log.warning("unexpected schema for %s: %s", url, list(df.columns))
            continue

        df = df[["open_time", "open", "high", "low", "close", "volume"]].rename(
            columns={"open_time": "timestamp"}
        )
        df["timestamp"] = df["timestamp"].astype("int64")
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["open", "close"])
        chunks.append(df)
        log.info("  %s %s: +%d bars", pair, period, len(df))
        time.sleep(0.05)  # be polite

    if not chunks:
        log.warning("no data fetched for %s %s", pair, timeframe)
        return out_path

    combined = (
        pd.concat(chunks, ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    combined.to_parquet(out_path, index=False)
    log.info("wrote %s: %d total bars (%s..%s)",
             out_path, len(combined),
             datetime.fromtimestamp(combined["timestamp"].iloc[0] / 1000),
             datetime.fromtimestamp(combined["timestamp"].iloc[-1] / 1000))
    return out_path


def download_funding(
    pair: str,
    years: float = 2.0,
    end: date | None = None,
) -> Path:
    """Download monthly funding-rate zips for one pair.

    Stores at data/historical/<pair>/funding.parquet with columns:
        timestamp (int ms), funding_rate (8h decimal)

    Resumable: re-running extends the file with any newer months.
    """
    end = end or date.today().replace(day=1) - timedelta(days=1)
    start = (end.replace(day=1) - timedelta(days=int(365 * years))).replace(day=1)

    out_dir = HISTORICAL_DIR / pair
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "funding.parquet"

    existing = pd.DataFrame()
    existing_months: set[str] = set()
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        if not existing.empty:
            existing_months = set(
                pd.to_datetime(existing["timestamp"], unit="ms", utc=True)
                .dt.to_period("M").astype(str).unique()
            )

    chunks: list[pd.DataFrame] = []
    if not existing.empty:
        chunks.append(existing)

    months = _months_between(start, end)
    log.info("funding %s: %d months", pair, len(months))

    for y, m in months:
        period = f"{y}-{m:02d}"
        if period in existing_months:
            continue
        url = f"{BINANCE_BASE}/fundingRate/{pair}/{pair}-fundingRate-{period}.zip"
        df = _fetch_zip_csv(url)
        if df is None or df.empty:
            continue

        if len(df.columns) >= 3:
            df = df.iloc[:, :3]
            df.columns = FUNDING_COLS
        else:
            continue

        df = df.rename(columns={"calc_time": "timestamp", "last_funding_rate": "funding_rate"})
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("Int64")
        df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
        df = df[["timestamp", "funding_rate"]].dropna()
        df["timestamp"] = df["timestamp"].astype("int64")
        chunks.append(df)
        log.info("  %s %s: +%d funding rows", pair, period, len(df))
        time.sleep(0.05)

    if not chunks:
        log.warning("no funding data for %s", pair)
        return out_path

    combined = (
        pd.concat(chunks, ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    combined.to_parquet(out_path, index=False)
    log.info("wrote %s: %d funding rows", out_path, len(combined))
    return out_path
