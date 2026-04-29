"""FRED data source — Federal Reserve Economic Data, free, no auth.

Used for macro overlays: yield curve slope, VIX, unemployment, CPI, etc.
Public CSV endpoint requires no API key but a key is recommended for higher
rate limits (set FRED_API_KEY in env).

Common series IDs:
  T10Y2Y    — 10-Year minus 2-Year Treasury yield (yield curve)
  T10Y3M    — 10-Year minus 3-Month
  DGS10     — 10-Year Treasury constant maturity
  DGS2      — 2-Year Treasury
  VIXCLS    — CBOE Volatility Index daily close
  UNRATE    — Unemployment rate
  CPIAUCSL  — Consumer Price Index
  DFF       — Federal Funds effective rate
"""
from __future__ import annotations

import logging
import os
from datetime import date
from io import StringIO

import pandas as pd

log = logging.getLogger("apex2.data.fred")

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def get_series(series_id: str, start: date | None = None, end: date | None = None) -> pd.Series:
    """Fetch a FRED series by ID. Returns float-valued Series indexed by date.

    Uses the public CSV endpoint (no auth required) for simplicity.
    """
    import httpx

    params = {"id": series_id}
    if start:
        params["cosd"] = start.isoformat()
    if end:
        params["coed"] = end.isoformat()
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(FRED_CSV_BASE, params=params)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text))
    except Exception as e:
        log.warning("FRED fetch %s failed: %s", series_id, e)
        return pd.Series(dtype=float, name=series_id)

    date_col = next((c for c in df.columns if c.lower().startswith("date") or c.upper() == "DATE"), df.columns[0])
    val_col = next((c for c in df.columns if c != date_col), df.columns[1] if len(df.columns) > 1 else None)
    if val_col is None:
        return pd.Series(dtype=float, name=series_id)
    df = df.rename(columns={date_col: "date", val_col: "value"})
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    s = df.set_index("date")["value"].dropna()
    s.name = series_id
    return s


def yield_curve_slope(start: date | None = None, end: date | None = None) -> pd.Series:
    """10y-2y treasury spread. Negative = inverted curve = recession signal."""
    return get_series("T10Y2Y", start=start, end=end)


def vix_history(start: date | None = None, end: date | None = None) -> pd.Series:
    return get_series("VIXCLS", start=start, end=end)
