"""TradingAgents-light: lightweight Claude advisor overlay for rule-based strategies.

The full TauricResearch/TradingAgents framework runs 5 LLM agents (Analyst,
Researcher, Trader, Risk, Portfolio Manager) in a debate. For a daily-bar
rule-based bot that's overkill — 8+ API calls per signal, $1+ per trade in
inference cost, plus seconds of latency.

This module provides three TARGETED LLM augmentations:

  1. daily_briefing()     — Once/day macro+regime read. Output cached for 8h.
  2. pre_trade_veto()     — One-shot sanity check before order submission.
                            Returns (allow, reason). Designed to catch obvious
                            news-driven bad ideas (earnings tomorrow, halt, etc).
  3. trade_journal()      — Append every executed decision + outcome for later
                            reflection. Powers a weekly review prompt.

All three are OPT-IN. If ANTHROPIC_API_KEY is missing, every call returns
the permissive default (allow=True, briefing=None). The bot keeps running.

Cost control:
  - daily_briefing uses prompt caching for the system prompt (~90% savings)
  - pre_trade_veto has a hard daily call budget (default 50)
  - All calls use claude-haiku-4-5 by default for fast/cheap reads;
    set MODEL=claude-sonnet-4-6 if you want the upgrade.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("apex2.agents.advisor")

DEFAULT_MODEL = os.environ.get("APEX_ADVISOR_MODEL", "claude-haiku-4-5")
JOURNAL_PATH = Path(os.environ.get("APEX_JOURNAL", "data/trade_journal.jsonl"))

_DAILY_CACHE: dict = {}     # {date_iso: briefing_dict}
_VETO_BUDGET_DATE: str | None = None
_VETO_CALLS_TODAY: int = 0
_VETO_DAILY_LIMIT: int = int(os.environ.get("APEX_VETO_DAILY_LIMIT", "50"))


@dataclass
class Briefing:
    regime: str                           # "risk_on" | "neutral" | "risk_off"
    summary: str
    confidence: float                     # 0.0 - 1.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class VetoResult:
    allow: bool
    reason: str = ""
    confidence: float = 0.0


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        from anthropic import Anthropic
        return Anthropic()
    except ImportError:
        log.warning("anthropic SDK not installed — advisor inert")
        return None


def daily_briefing(force: bool = False) -> Briefing | None:
    """Once-per-day macro briefing. Returns None if no API key.

    Cached for the calendar day. Called by the runner at session start
    or when the date changes.
    """
    today = date.today().isoformat()
    if not force and today in _DAILY_CACHE:
        return _DAILY_CACHE[today]

    client = _client()
    if client is None:
        return None

    system = (
        "You are a quantitative trading regime classifier. "
        "Output valid JSON with three fields: "
        "regime (one of: 'risk_on', 'neutral', 'risk_off'), "
        "summary (one sentence), "
        "confidence (0.0 to 1.0). "
        "Base your call on what is verifiable about the current market: "
        "VIX level, yield curve, recent SPY trend, Fed policy stance, "
        "and notable upcoming events. Be terse, no hedging."
    )
    user = f"Today is {today}. Classify the current US equity regime."

    try:
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=300,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text.strip()
        # Strip optional markdown fences.
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        b = Briefing(
            regime=str(data.get("regime", "neutral")),
            summary=str(data.get("summary", "")),
            confidence=float(data.get("confidence", 0.5)),
        )
        _DAILY_CACHE.clear()
        _DAILY_CACHE[today] = b
        log.info("daily briefing: regime=%s confidence=%.2f", b.regime, b.confidence)
        return b
    except Exception as e:
        log.warning("daily_briefing failed: %s", e)
        return None


def _check_budget() -> bool:
    global _VETO_BUDGET_DATE, _VETO_CALLS_TODAY
    today = date.today().isoformat()
    if _VETO_BUDGET_DATE != today:
        _VETO_BUDGET_DATE = today
        _VETO_CALLS_TODAY = 0
    if _VETO_CALLS_TODAY >= _VETO_DAILY_LIMIT:
        return False
    _VETO_CALLS_TODAY += 1
    return True


def pre_trade_veto(symbol: str, side: str, strategy: str, reason: str = "") -> VetoResult:
    """Veto check before submitting an order.

    Returns allow=True when no API key, on error, or budget exceeded.
    Returns allow=False ONLY when the LLM identifies a clear obstacle
    (earnings, halt, M&A, dividend ex-date causing stop blowout, etc.).
    """
    client = _client()
    if client is None:
        return VetoResult(allow=True, reason="no_advisor")
    if not _check_budget():
        return VetoResult(allow=True, reason="budget_exhausted")

    system = (
        "You are a pre-trade safety gate for a US-equity algorithmic bot. "
        "You receive a proposed order and check for OBVIOUS reasons to block. "
        "Block ONLY for: earnings within 24h, trading halt, M&A action, "
        "stock split or major dividend ex-date in the next session, "
        "or a known liquidity event. Do NOT block for opinion-level concerns "
        "(valuation, sentiment, etc). When in doubt, allow. "
        "Output JSON: {allow: bool, reason: string, confidence: 0-1}."
    )
    user = (
        f"Order: {side.upper()} {symbol}\n"
        f"Strategy: {strategy}\n"
        f"Signal reason: {reason}\n"
        f"Date: {date.today().isoformat()}\n"
        "Anything to block this for the next session?"
    )

    try:
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=200,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        return VetoResult(
            allow=bool(data.get("allow", True)),
            reason=str(data.get("reason", "")),
            confidence=float(data.get("confidence", 0.5)),
        )
    except Exception as e:
        log.warning("pre_trade_veto failed for %s: %s", symbol, e)
        return VetoResult(allow=True, reason=f"error:{e!r}"[:120])


def trade_journal(entry: dict) -> None:
    """Append a structured trade entry to JSONL journal.

    Keys we care about:
      ts, strategy, symbol, side, qty, price, reason,
      pre_trade_veto, regime_at_entry, exit_reason, realized_pnl_pct
    """
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {**entry, "ts": entry.get("ts", datetime.utcnow().isoformat())}
    with JOURNAL_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
