"""
config.py — Bot 2 Polymarket Configuration
Merged: User uploaded version + live system fixes
Claude NLP replaced with free keyword-based sentiment + RSS feeds
"""
import os
from pathlib import Path

# ── Bullpen CLI (Primary copy-trading data source) ────────────────────────────
BULLPEN_PATH = "/home/jefe/.bullpen/bin/bullpen"

# ── Polymarket Wallet Auth (NOT needed for paper trading / copy mode) ─────────
POLY_PRIVATE_KEY  = "0x19c63922c5a7ad781907cda3566e6219889709024b9b2b96dca7a8add2740816"
POLY_PROXY_WALLET = ""

# ── Alchemy (Polygon RPC — optional, bot works without it) ────────────────────
ALCHEMY_API_KEY = ""

# ── Claude / Anthropic REPLACED with free alternatives ────────────────────────
# USE_KEYWORD_SENTIMENT replaces Claude NLP cost-free
ANTHROPIC_API_KEY = ""
CLAUDE_MODEL      = ""  # Not used — replaced with keyword sentiment
USE_KEYWORD_SENTIMENT = True

# ── Dune Analytics (optional — whale wallet discovery) ────────────────────────
DUNE_API_KEY = ""

# ── Twitter / X (optional — news feed) ───────────────────────────────────────
TWITTER_BEARER_TOKEN = ""

# ── Telegram Alerts ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8723118008:AAFv1tIx4vn60jWJZ_IVQ04mSgqZ8zm5Z_M"
TELEGRAM_CHAT_ID   = "6768348686"

# ── Kalshi (optional — cross-platform arb) ────────────────────────────────────
KALSHI_API_KEY    = ""
KALSHI_API_SECRET = ""

# ── Bot Capital & Risk Settings ───────────────────────────────────────────────
STARTING_BANKROLL      = 250.0
MAX_POSITION_PCT       = 0.05    # 5% max per trade
KELLY_FRACTION         = 0.25    # Quarter-Kelly
MIN_EDGE               = 0.01    # 1% minimum edge to trade (quarter-Kelly keeps sizing safe)
DAILY_LOSS_CAP_PCT     = 0.03    # Halt if -3% in a day
MIN_LIQUIDITY          = 1000.0  # Skip markets below this
MIN_VOLUME             = 500.0

# ── Copy Trading Settings ─────────────────────────────────────────────────────
MIRROR_RATIO           = 0.15    # Mirror whale at 15% of their size
MAX_COPY_SIZE          = 10.0    # Hard cap per copy trade
MIN_WHALE_TRADE_SIZE   = 200.0   # Ignore whale micro-bets below this
MAX_CONSECUTIVE_LOSSES = 5       # Cooldown after this many consecutive losses
COOLDOWN_HOURS         = 6
TOP_N_TRADERS          = 15      # Increased from 10 to track more

# ── Data Paths ────────────────────────────────────────────────────────────────
DATA_DIR            = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PAPER_RESULTS_PATH  = DATA_DIR / "paper_results.json"
COPY_TRADES_PATH    = DATA_DIR / "copy_trades.json"
WHALE_STATS_PATH    = DATA_DIR / "whale_stats.json"
SCAN_RESULTS_PATH   = DATA_DIR / "scan_results.json"
DAILY_PNL_PATH      = DATA_DIR / "daily_pnl.json"

# ── Scan Schedule ─────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECS     = 60     # Scan every 60s for 5-min BTC market timing
COPY_SCAN_INTERVAL     = 300    # Copy layer refresh every 5 min

# ── BTC Short-Duration Sniper ─────────────────────────────────────────────────
# Targets Polymarket's fast-resolving BTC price markets (e.g. "Will BTC be above X in 5min?")
BTC_SNIPER_ENABLED     = True
BTC_SNIPER_MAX_MINUTES = 30     # Only enter markets resolving within this window
BTC_SNIPER_MIN_MINUTES = 1      # Avoid markets resolving in < 1 min (too late to enter)
BTC_SNIPER_MIN_EDGE    = 0.02   # 2% edge — slightly lower bar for fast-resolving trades
BTC_SNIPER_MAX_BET_PCT = 0.03   # 3% of bankroll cap per BTC micro-trade

# ── Polymarket API Bases ──────────────────────────────────────────────────────
GAMMA_API   = "https://gamma-api.polymarket.com"
CLOB_API    = "https://clob.polymarket.com"
DATA_API    = "https://data-api.polymarket.com"
DERIBIT_API = "https://www.deribit.com/api/v2/public"
KALSHI_API_BASE = "https://trading-api.kalshi.com/trade-api/v2"

# ── Feature Flags ─────────────────────────────────────────────────────────────
ENABLE_SHORT_POSITIONS = True
ENABLE_COPY_TRADING    = True
ENABLE_BOND_STRATEGY   = True
ENABLE_AMM             = True
ENABLE_KALSHI_ARB      = False
ENABLE_NEWS_ENGINE     = True   # Now uses free RSS + keyword sentinel
# ── Platform Config ─────────────────────────────────────────────────────
EXECUTION_TARGET = "polymarket"  # "polymarket" or "bullpen" (both use CLOB)
PAPER_TRADE_ONLY = True           # False for live trading

# ── RSS News Sources (free, no API key needed) ────────────────────────────────
RSS_FEEDS = [
    "https://www.reuters.com/markets/rss",
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://feeds.bbci.co.uk/news/rss.xml",
]

KEYWORDS_BULLISH = ["yes", "happens", "wins", "approved", "passes", "confirms"]
KEYWORDS_BEARISH = ["no", "fails", "rejected", "denied", "loses", "cancels"]

def check_config() -> dict:
    """Return a dict of which integrations are active."""
    return {
        "bullpen":        Path(BULLPEN_PATH).exists(),
        "alchemy_rpc":    bool(ALCHEMY_API_KEY),
        "keyword_sentiment": USE_KEYWORD_SENTIMENT,
        "claude_nlp":     bool(ANTHROPIC_API_KEY),
        "dune":           bool(DUNE_API_KEY),
        "twitter":        bool(TWITTER_BEARER_TOKEN),
        "telegram":       bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "kalshi_arb":     bool(KALSHI_API_KEY),
        "live_trading":   bool(POLY_PRIVATE_KEY) and not PAPER_TRADE_ONLY,
        "paper_mode":     PAPER_TRADE_ONLY,
    }
