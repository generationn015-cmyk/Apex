"""
APEX — Unified Configuration
All secrets come from environment variables. Never hardcode keys.
Copy .env.example to .env and fill in your values.
"""
import os

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN",   "8723118008:AAFv1tIx4vn60jWJZ_IVQ04mSgqZ8zm5Z_M")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6768348686")

# ── Twelve Data ───────────────────────────────────────────────────────────────
TWELVE_DATA_KEYS = [
    os.getenv("TWELVE_DATA_KEY_1", "f78bd5d5350e4c6fa6af4ddaa63a347b"),
    os.getenv("TWELVE_DATA_KEY_2", "28fa4c9f04ca410396bea5132161307f"),
]
TWELVE_DATA_KEY = TWELVE_DATA_KEYS[0]

# ── Lighter.xyz Exchange (zero-fee perpetuals) ────────────────────────────────
# Get keys at: app.lighter.xyz → API Keys
LIGHTER_API_KEY_ID     = os.getenv("LIGHTER_API_KEY_ID",     "")
LIGHTER_API_KEY_SECRET = os.getenv("LIGHTER_API_KEY_SECRET", "")

# ── Anthropic (Claude AI signal review) ──────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── GitHub (hourly data sync to Streamlit Cloud) ──────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# ── Polymarket ────────────────────────────────────────────────────────────────
POLY_PRIVATE_KEY  = os.getenv("POLY_PRIVATE_KEY", "")

# ── Trading mode ──────────────────────────────────────────────────────────────
# "paper" = simulate only (safe default)
# "live"  = real money on Lighter.xyz (requires LIGHTER_API_KEY_ID + LIGHTER_API_KEY_SECRET)
TRADING_MODE = os.getenv("TRADING_MODE", "paper")

# ── Agents & Assets ───────────────────────────────────────────────────────────
# BTC/ETH/SOL perps — available on Lighter.xyz with zero fees
AGENTS = {
    "ATLAS": {
        "type":     "sma_trend",
        "assets":   ["BTC/USDT", "ETH/USDT"],
        "capital":  100.0,
        "interval": "1h",       # 1h candles (less noise vs 5min)
        "description": "SMA Trend + ADX + Volume",
    },
    "ORACLE": {
        "type":     "macd_momentum",
        "assets":   ["ETH/USDT", "SOL/USDT"],
        "capital":  100.0,
        "interval": "1h",
        "description": "MACD Zero-Line + RSI + HTF",
    },
    "SNIPER": {
        "type":     "hybrid_regime",
        "assets":   ["BTC/USDT", "SOL/USDT"],
        "capital":  100.0,
        "interval": "1h",
        "description": "Regime-switching: BB Breakout (trending) / RSI Mean-Rev (ranging)",
    },
    "SENTINEL": {
        "type":     "ema_squeeze",
        "assets":   ["BTC/USDT"],
        "capital":  100.0,
        "interval": "1h",
        "description": "EMA Alignment + Keltner Squeeze Release",
    },
}

# ── Risk parameters ───────────────────────────────────────────────────────────
RISK = {
    "max_risk_pct":            2.0,    # Max 2% of capital per trade
    "max_position_pct":       20.0,    # Max 20% of total bankroll in one trade
    "consecutive_loss_limit":   2,     # Cooldown after N losses in a row
    "cooldown_hours":          12,     # Shorter than original 24h
    "volatility_kill_pct":     90,     # 90th percentile VIX equivalent
    "min_signal_strength":      0.65,  # Only trade signals ≥ 65% strength
    "min_rr_ratio":             1.5,   # Minimum reward:risk ratio required
}

# ── Session filter (UTC) ─────────────────────────────────────────────────────
# Crypto trades 24/7 but volume peaks during NY + London overlap
SESSION_FILTER = {
    "enabled":   True,
    "open_utc":  7,    # 7am UTC = London open
    "close_utc": 21,   # 9pm UTC = NY close
}

# ── Loop timing ───────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS = 300   # Scan every 5 minutes
HEARTBEAT_MINUTES     = 60    # Send Telegram heartbeat every hour

# ── Polymarket ────────────────────────────────────────────────────────────────
POLY = {
    "starting_bankroll": 50.0,
    "kelly_fraction":    0.25,
    "min_edge":          0.05,
    "max_position_pct":  0.15,
    "min_liquidity":    1000,
    "min_volume":        500,
    "max_hours_to_resolve": 48,
}

# ── Paths ─────────────────────────────────────────────────────────────────────
import pathlib
ROOT = pathlib.Path(__file__).parent.parent
LOGS_DIR    = ROOT / "logs"
PAPER_DIR   = ROOT / "paper"
STATE_FILE  = ROOT / "logs" / "state.json"

LOGS_DIR.mkdir(exist_ok=True)
PAPER_DIR.mkdir(exist_ok=True)
