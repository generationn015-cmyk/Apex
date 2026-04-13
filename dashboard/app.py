"""
APEX Trading HQ — Unified Dashboard v2
═══════════════════════════════════════════════════════════════════
5 tabs: Overview | BTC 5-Min Sniper | Crypto Agents | Polymarket Scanner | Copy Trader

Run:
  uv run streamlit run dashboard/app.py   (from apex/ root)

Data sources (all local JSON):
  logs/state.json             — crypto agent stats
  logs/watchdog_status.json   — process status
  logs/paper_trades.jsonl     — crypto agent trades
  polymarket/data/btc_5m_state.json   — BTC 5-min sniper
  polymarket/data/sniper_state.json   — general Polymarket sniper
  polymarket/data/scan_results.json   — latest scanner results
"""
import json
import html as html_lib
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="APEX Trading HQ",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
* { font-family:'Inter',sans-serif !important; }
.block-container { padding:14px 22px !important; }

/* ── Stats bar ── */
.stats-bar {
    display:flex; gap:10px; padding:14px; margin-bottom:12px;
    background:#161b22; border-radius:14px; border:1px solid #30363d; flex-wrap:wrap;
}
.stat-item {
    display:flex; flex-direction:column; align-items:center;
    padding:10px 14px; border-radius:10px; background:#0d1117;
    border:1px solid #21262d; min-width:85px; text-align:center; flex:1;
}
.stat-value { font-size:22px; font-weight:700; }
.stat-label { font-size:10px; color:#8b949e; margin-top:3px; text-transform:uppercase; letter-spacing:.5px; }

/* ── Card grid ── */
.floor-grid {
    display:grid; grid-template-columns:repeat(auto-fill,minmax(290px,1fr));
    gap:14px; margin:14px 0;
}
.station-card {
    background:#161b22; border:1px solid #30363d; border-radius:12px;
    padding:18px; transition:all .2s; overflow:hidden;
}
.station-card:hover { border-color:#58a6ff; transform:translateY(-2px); box-shadow:0 8px 24px rgba(0,0,0,.3); }
.station-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.station-name { font-size:15px; font-weight:700; color:#e6edf3; }
.station-sub  { font-size:11px; color:#8b949e; }

/* ── Status dots ── */
.status-wrap  { display:flex; align-items:center; gap:6px; font-size:12px; }
.status-dot   { width:8px; height:8px; border-radius:50%; display:inline-block; }
.status-active   { background:#3fb950; box-shadow:0 0 8px #3fb950; animation:pulse 1.5s infinite; }
.status-inactive { background:#484f58; }
.status-live     { background:#f85149; box-shadow:0 0 10px #f85149; animation:pulse .8s infinite; }
@keyframes pulse { 0%,100%{opacity:1}50%{opacity:.4} }

/* ── XP tracks ── */
.xp-track { width:100%; height:5px; background:#21262d; border-radius:3px; margin:8px 0; overflow:hidden; }
.xp-fill  { height:100%; border-radius:3px; background:linear-gradient(90deg,#58a6ff,#bc8cff); }
.xp-label { display:flex; justify-content:space-between; font-size:10px; color:#8b949e; margin-bottom:6px; }

/* ── Card stats ── */
.card-stats { display:grid; grid-template-columns:1fr 1fr; gap:7px; margin-top:10px; }
.card-stat  { background:#0d1117; padding:9px 7px; border-radius:7px; text-align:center; border:1px solid #21262d; }
.card-stat-val { font-size:15px; font-weight:700; }
.card-stat-lbl { font-size:9px; color:#8b949e; margin-top:2px; text-transform:uppercase; letter-spacing:.3px; }
.pos { color:#3fb950; }
.neg { color:#f85149; }
.neu { color:#8b949e; }

/* ── Achievement badges ── */
.ach-row { margin-top:10px; display:flex; flex-wrap:wrap; gap:5px; }
.ach-badge {
    background:linear-gradient(135deg,#1a3a4a,#161b22);
    border:1px solid #30363d; border-radius:8px; padding:3px 9px;
    font-size:10px; color:#e6edf3; display:inline-flex; align-items:center; gap:3px;
}

/* ── Section headers ── */
.section-hdr {
    font-size:16px; font-weight:700; color:#e6edf3; margin:20px 0 10px;
    display:flex; align-items:center; gap:7px;
}

/* ── Process badges ── */
.proc-row {
    display:flex; align-items:center; justify-content:space-between;
    padding:10px 0; border-bottom:1px solid #21262d;
}
.proc-row:last-child { border-bottom:none; }
.proc-name  { font-size:13px; font-weight:600; color:#e6edf3; }
.proc-sub   { font-size:10px; color:#8b949e; }
.proc-badge {
    padding:3px 12px; border-radius:10px; font-size:11px; font-weight:700;
}
.proc-badge.running { background:#0d2b0d; color:#3fb950; border:1px solid #238636; }
.proc-badge.dead    { background:#2d1a0a; color:#d29922; border:1px solid #9e6a03; }
.proc-badge.stopped { background:#1a1a1a; color:#484f58; border:1px solid #30363d; }

/* ── Big number cards ── */
.big-card {
    background:#161b22; border:1px solid #30363d; border-radius:12px;
    padding:20px; text-align:center;
}
.big-card-val { font-size:28px; font-weight:700; }
.big-card-lbl { font-size:11px; color:#8b949e; margin-top:4px; text-transform:uppercase; letter-spacing:.5px; }

/* ── Indicator grid ── */
.ind-grid {
    display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr));
    gap:8px; margin:10px 0;
}
.ind-chip {
    background:#0d1117; border:1px solid #21262d; border-radius:8px;
    padding:8px 10px; text-align:center; font-size:12px;
}
.ind-chip-name { font-size:10px; color:#8b949e; margin-bottom:2px; text-transform:uppercase; }
.ind-chip-val  { font-size:14px; font-weight:700; }

/* ── Coming soon ── */
.coming-soon {
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    min-height:300px; color:#484f58;
}
.coming-soon-icon { font-size:64px; margin-bottom:16px; }
.coming-soon-text { font-size:24px; font-weight:700; }
.coming-soon-sub  { font-size:13px; margin-top:8px; }

/* ── No data state ── */
.no-data {
    background:#161b22; border:1px solid #21262d; border-radius:12px;
    padding:40px; text-align:center; color:#484f58; font-size:14px;
    margin:10px 0;
}

/* ── Sniper table overrides ── */
div[data-testid="stDataFrame"] { border-radius:10px; overflow:hidden; }
</style>
""", unsafe_allow_html=True)

# ── Paths ────────────────────────────────────────────────────────────────────
_APEX_ROOT = Path(__file__).parent.parent
LOGS_DIR = _APEX_ROOT / "logs"
POLY_DIR = _APEX_ROOT / "polymarket" / "data"

STATE_FILE = LOGS_DIR / "state.json"
STATUS_FILE = LOGS_DIR / "watchdog_status.json"
PAPER_LOG = LOGS_DIR / "paper_trades.jsonl"
BTC_5M_STATE = POLY_DIR / "btc_5m_state.json"
SNIPER_STATE = POLY_DIR / "sniper_state.json"
SCAN_RESULTS = POLY_DIR / "scan_results.json"

LOGS_DIR.mkdir(exist_ok=True)
REFRESH_S = 30


# ── Data loaders (local files first, GitHub fallback for Replit) ─────────────
_GITHUB_RAW = "https://raw.githubusercontent.com/generationn015-cmyk/Apex/master"
_USE_GITHUB = not (LOGS_DIR / "state.json").exists() and not (BTC_5M_STATE).exists()

def _fetch_url(url: str) -> str | None:
    """Fetch URL content for GitHub fallback."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "APEX-Dashboard"})
        with urllib.request.urlopen(req, timeout=10) as f:
            return f.read().decode()
    except Exception:
        return None


def load_json(p: Path) -> dict | list | None:
    try:
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    # GitHub fallback for Replit deployment
    if _USE_GITHUB:
        rel = str(p).replace(str(_APEX_ROOT) + "/", "")
        raw = _fetch_url(f"{_GITHUB_RAW}/{rel}")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
    return None


def load_jsonl(p: Path) -> list[dict]:
    rows = []
    text = None
    try:
        if p.exists():
            text = p.read_text()
    except Exception:
        pass
    # GitHub fallback
    if text is None and _USE_GITHUB:
        rel = str(p).replace(str(_APEX_ROOT) + "/", "")
        text = _fetch_url(f"{_GITHUB_RAW}/{rel}")
    if text:
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def fmt_pnl(v: float) -> str:
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"


def pnl_cls(v: float) -> str:
    return "pos" if v >= 0 else "neg"


def sbar(icon: str, val, lbl: str, cls: str = "") -> str:
    return (f'<div class="stat-item">'
            f'<div class="stat-value {cls}">{icon} {html_lib.escape(str(val))}</div>'
            f'<div class="stat-label">{lbl}</div></div>')


def proc_badge_html(status: str) -> str:
    if status == "running":
        return '<span class="proc-badge running">RUNNING</span>'
    elif status == "dead":
        return '<span class="proc-badge dead">CRASHED</span>'
    elif status == "not_started":
        return '<span class="proc-badge stopped">STOPPED</span>'
    return '<span class="proc-badge stopped">OFFLINE</span>'


def status_dot_html(status: str) -> str:
    if status == "running":
        return '<span class="status-dot status-active"></span>'
    return '<span class="status-dot status-inactive"></span>'


def time_ago(ts_str: str) -> str:
    """Human-readable time-ago string from an ISO timestamp."""
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        elif secs < 3600:
            return f"{secs // 60}m ago"
        elif secs < 86400:
            return f"{secs // 3600}h ago"
        else:
            return f"{secs // 86400}d ago"
    except Exception:
        return "—"


# ── Load all data once ───────────────────────────────────────────────────────
apex_state = load_json(STATE_FILE) or {}
wdog_status = load_json(STATUS_FILE) or {}
procs = wdog_status.get("processes", {})
btc_5m = load_json(BTC_5M_STATE) or {}
sniper_state = load_json(SNIPER_STATE) or {}
scan_results = load_json(SCAN_RESULTS)
trades_rows = load_jsonl(PAPER_LOG)
trades_df = pd.DataFrame(trades_rows) if trades_rows else pd.DataFrame()

# BTC 5-min trades
btc_trades = btc_5m.get("trades", [])
btc_df = pd.DataFrame(btc_trades) if btc_trades else pd.DataFrame()

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_overview, tab_btc5m, tab_crypto, tab_scanner, tab_copy = st.tabs([
    "  Overview  ",
    "  BTC 5-Min Sniper  ",
    "  Crypto Agents  ",
    "  Polymarket Scanner  ",
    "  Copy Trader  ",
])


# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════
with tab_overview:
    st.markdown('<div class="section-hdr">System Status</div>', unsafe_allow_html=True)

    # ── Process status cards ─────────────────────────────────────────────
    PROC_META = {
        "apex_bot":           ("APEX Bot",              "Lighter.xyz crypto perps — 4 agents"),
        "telegram_bot":       ("Telegram Bot",          "Command interface"),
        "btc_5m_sniper":      ("BTC 5-Min Sniper",      "Polymarket BTC Up/Down 5-min windows"),
        "polymarket_sniper":  ("Polymarket Scanner",     "Kelly-edge scanner across all markets"),
        "copy_trader":        ("Copy Trader",            "Whale flow mirroring — Kelly-sized"),
    }

    proc_html = '<div class="floor-grid">'
    for proc_key, (label, sub) in PROC_META.items():
        info = procs.get(proc_key, {})
        pstatus = info.get("status", "unknown")
        pid = info.get("pid")
        mode = info.get("mode", "")

        dot = status_dot_html(pstatus)
        badge = proc_badge_html(pstatus)
        mode_tag = f' ({mode})' if mode else ''
        pid_tag = f'pid {pid}' if pid else '—'

        proc_html += f"""
        <div class="station-card">
            <div class="station-header">
                <div>
                    <div class="station-name">{dot} {html_lib.escape(label)}</div>
                    <div class="station-sub">{html_lib.escape(sub)}</div>
                </div>
                {badge}
            </div>
            <div class="card-stats">
                <div class="card-stat"><div class="card-stat-val" style="font-size:12px;">{pid_tag}</div><div class="card-stat-lbl">PID</div></div>
                <div class="card-stat"><div class="card-stat-val" style="font-size:12px;">{html_lib.escape(mode_tag) if mode_tag else '—'}</div><div class="card-stat-lbl">Mode</div></div>
            </div>
        </div>"""
    proc_html += '</div>'
    st.markdown(proc_html, unsafe_allow_html=True)

    # ── Aggregate PnL & bankroll ─────────────────────────────────────────
    st.markdown('<div class="section-hdr">Performance Summary</div>', unsafe_allow_html=True)

    # Crypto agent PnL
    crypto_stats = apex_state.get("stats", {})
    crypto_pnl = crypto_stats.get("total_pnl", 0)
    crypto_trades_count = crypto_stats.get("total_trades", 0)

    # BTC 5-min PnL
    btc_pnl = 0.0
    btc_trade_count = len(btc_trades)
    btc_resolved = [t for t in btc_trades if t.get("resolved")]
    btc_wins = [t for t in btc_resolved if t.get("won")]
    for t in btc_resolved:
        btc_pnl += t.get("pnl", 0)
    btc_bankroll = btc_5m.get("bankroll", 0)
    btc_win_rate = (len(btc_wins) / len(btc_resolved) * 100) if btc_resolved else 0

    # Polymarket sniper PnL
    sniper_pnl = 0.0
    sniper_bankroll = 0.0
    sniper_trades_list = []
    if isinstance(sniper_state, dict):
        sniper_bankroll = sniper_state.get("bankroll", 0)
        sniper_trades_list = sniper_state.get("trades", [])
        if not sniper_trades_list:
            # Fallback: build from positions + history
            for cid, pos in sniper_state.get("positions", {}).items():
                sniper_trades_list.append({**pos, "condition_id": cid, "resolved": False})
            sniper_trades_list.extend(sniper_state.get("history", []))
        for t in sniper_trades_list:
            if t.get("resolved"):
                sniper_pnl += t.get("pnl", 0)

    total_pnl = crypto_pnl + btc_pnl + sniper_pnl

    st.markdown(f"""<div class="stats-bar">
        {sbar("", fmt_pnl(total_pnl), "Total PnL", pnl_cls(total_pnl))}
        {sbar("", fmt_pnl(btc_pnl), "BTC Sniper PnL", pnl_cls(btc_pnl))}
        {sbar("", fmt_pnl(crypto_pnl), "Crypto Agents PnL", pnl_cls(crypto_pnl))}
        {sbar("", f"${btc_bankroll:,.2f}", "BTC Sniper Bankroll", "pos" if btc_bankroll > 0 else "neu")}
        {sbar("", f"{btc_win_rate:.0f}%", "BTC Win Rate", "pos" if btc_win_rate >= 50 else ("neg" if btc_resolved else "neu"))}
        {sbar("", btc_trade_count + crypto_trades_count, "Total Trades", "")}
    </div>""", unsafe_allow_html=True)

    # ── Uptime info ──────────────────────────────────────────────────────
    wdog_updated = wdog_status.get("updated_at", "")
    apex_updated = apex_state.get("updated_at", "")
    btc_updated = btc_5m.get("updated", "")

    st.markdown('<div class="section-hdr">Last Updated</div>', unsafe_allow_html=True)
    uptime_html = '<div class="stats-bar">'
    if wdog_updated:
        uptime_html += sbar("", time_ago(wdog_updated), "Watchdog", "")
    if apex_updated:
        uptime_html += sbar("", time_ago(apex_updated), "Crypto Agents", "")
    if btc_updated:
        uptime_html += sbar("", time_ago(btc_updated), "BTC 5-Min Sniper", "")
    if not wdog_updated and not apex_updated and not btc_updated:
        uptime_html += sbar("", "—", "No data", "neu")
    uptime_html += '</div>'
    st.markdown(uptime_html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — BTC 5-MIN SNIPER (THE MAIN EVENT)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_btc5m:
    if not btc_trades:
        st.markdown('<div class="no-data">No BTC 5-min sniper data yet. Waiting for first trade...</div>',
                    unsafe_allow_html=True)
    else:
        # ── Top stats bar ────────────────────────────────────────────────
        resolved = [t for t in btc_trades if t.get("resolved")]
        wins = [t for t in resolved if t.get("won")]
        losses = [t for t in resolved if not t.get("won")]
        total_btc_pnl = sum(t.get("pnl", 0) for t in resolved)
        wr = (len(wins) / len(resolved) * 100) if resolved else 0
        windows_scanned = btc_5m.get("windows_scanned", 0)
        windows_traded = btc_5m.get("windows_traded", 0)
        avg_edge = np.mean([t.get("edge", 0) for t in btc_trades]) if btc_trades else 0
        avg_bet = np.mean([t.get("bet_size", 0) for t in btc_trades]) if btc_trades else 0

        st.markdown(f"""<div class="stats-bar">
            {sbar("", f"${btc_5m.get('bankroll', 0):,.2f}", "Bankroll", "pos")}
            {sbar("", fmt_pnl(total_btc_pnl), "Total PnL", pnl_cls(total_btc_pnl))}
            {sbar("", f"{wr:.0f}%", "Win Rate", "pos" if wr >= 50 else "neg")}
            {sbar("", f"{len(wins)}W / {len(losses)}L", "Record", "")}
            {sbar("", len(btc_trades), "Total Trades", "")}
            {sbar("", f"{avg_edge*100:.1f}%", "Avg Edge", "pos")}
            {sbar("", f"${avg_bet:.2f}", "Avg Bet", "")}
            {sbar("", f"{windows_scanned}", "Scanned", "")}
        </div>""", unsafe_allow_html=True)

        # ── PnL curve ────────────────────────────────────────────────────
        if resolved:
            st.markdown('<div class="section-hdr">PnL Curve</div>', unsafe_allow_html=True)
            pnl_data = []
            cum = 0
            for t in sorted(resolved, key=lambda x: x.get("timestamp", "")):
                cum += t.get("pnl", 0)
                pnl_data.append({
                    "timestamp": t.get("timestamp", ""),
                    "pnl": t.get("pnl", 0),
                    "cumulative": cum,
                    "direction": t.get("direction", ""),
                    "won": t.get("won", False),
                })
            pnl_df = pd.DataFrame(pnl_data)
            pnl_df["timestamp"] = pd.to_datetime(pnl_df["timestamp"], utc=True, errors="coerce")

            fig = go.Figure()
            # Area fill
            fig.add_trace(go.Scatter(
                x=pnl_df["timestamp"], y=pnl_df["cumulative"],
                mode="lines+markers",
                line=dict(color="#58a6ff", width=2.5),
                marker=dict(
                    size=8,
                    color=["#3fb950" if w else "#f85149" for w in pnl_df["won"]],
                    line=dict(color="#0d1117", width=1),
                ),
                fill="tozeroy",
                fillcolor="rgba(88,166,255,0.1)",
                name="Cumulative PnL",
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "PnL: $%{customdata[1]:.2f}<br>"
                    "Cumulative: $%{y:.2f}<br>"
                    "<extra></extra>"
                ),
                customdata=list(zip(pnl_df["direction"], pnl_df["pnl"])),
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#484f58")
            fig.update_layout(
                height=320, template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor="#21262d", showgrid=True),
                yaxis=dict(gridcolor="#21262d", showgrid=True, title="Cumulative PnL ($)"),
                hovermode="x unified",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

        # ── Win/Loss distribution ────────────────────────────────────────
        if resolved:
            col_wl1, col_wl2 = st.columns(2)
            with col_wl1:
                st.markdown('<div class="section-hdr">Win/Loss Distribution</div>', unsafe_allow_html=True)
                pnls = [t.get("pnl", 0) for t in resolved]
                colors = ["#3fb950" if p >= 0 else "#f85149" for p in pnls]
                fig_dist = go.Figure(go.Bar(
                    x=list(range(1, len(pnls) + 1)),
                    y=pnls,
                    marker_color=colors,
                    hovertemplate="Trade #%{x}<br>PnL: $%{y:.2f}<extra></extra>",
                ))
                fig_dist.add_hline(y=0, line_dash="dash", line_color="#484f58")
                fig_dist.update_layout(
                    height=250, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(gridcolor="#21262d", title="Trade #"),
                    yaxis=dict(gridcolor="#21262d", title="PnL ($)"),
                    showlegend=False,
                )
                st.plotly_chart(fig_dist, use_container_width=True)

            with col_wl2:
                st.markdown('<div class="section-hdr">Direction Breakdown</div>', unsafe_allow_html=True)
                up_trades = [t for t in resolved if t.get("direction") == "UP"]
                down_trades = [t for t in resolved if t.get("direction") == "DOWN"]
                up_wins = len([t for t in up_trades if t.get("won")])
                down_wins = len([t for t in down_trades if t.get("won")])

                dir_data = pd.DataFrame({
                    "Direction": ["UP", "DOWN"],
                    "Wins": [up_wins, down_wins],
                    "Losses": [len(up_trades) - up_wins, len(down_trades) - down_wins],
                })
                fig_dir = go.Figure()
                fig_dir.add_trace(go.Bar(
                    x=dir_data["Direction"], y=dir_data["Wins"],
                    name="Wins", marker_color="#3fb950",
                ))
                fig_dir.add_trace(go.Bar(
                    x=dir_data["Direction"], y=dir_data["Losses"],
                    name="Losses", marker_color="#f85149",
                ))
                fig_dir.update_layout(
                    barmode="group",
                    height=250, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(gridcolor="#21262d"),
                    yaxis=dict(gridcolor="#21262d", title="Count"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig_dir, use_container_width=True)

        # ── Indicator breakdown (from latest trades with indicator data) ──
        trades_with_indicators = [t for t in btc_trades if t.get("indicators")]
        if trades_with_indicators:
            latest = trades_with_indicators[-1]
            ind = latest.get("indicators", {})
            scores = ind.get("scores", {})

            st.markdown('<div class="section-hdr">Indicator Breakdown (Latest Trade)</div>',
                        unsafe_allow_html=True)

            INDICATOR_NAMES = {
                "window_delta": "Window Delta",
                "macd_histogram": "MACD Histogram",
                "macd_acceleration": "MACD Accel",
                "macd_cross": "MACD Cross",
                "macd_zero_regime": "MACD Zero",
                "fast_macd_confirm": "Fast MACD",
                "macd_volume_flow": "MACD Vol Flow",
                "tick_trend": "Tick Trend",
            }

            if scores:
                ind_html = '<div class="ind-grid">'
                for key, display_name in INDICATOR_NAMES.items():
                    val = scores.get(key, 0)
                    color = "#3fb950" if val > 0 else ("#f85149" if val < 0 else "#484f58")
                    ind_html += f"""
                    <div class="ind-chip">
                        <div class="ind-chip-name">{display_name}</div>
                        <div class="ind-chip-val" style="color:{color};">{val:+.1f}</div>
                    </div>"""
                ind_html += '</div>'
                st.markdown(ind_html, unsafe_allow_html=True)

                # Score bar chart
                fig_ind = go.Figure(go.Bar(
                    x=[INDICATOR_NAMES.get(k, k) for k in scores.keys()],
                    y=list(scores.values()),
                    marker_color=["#3fb950" if v > 0 else "#f85149" if v < 0 else "#484f58"
                                  for v in scores.values()],
                    hovertemplate="%{x}: %{y:+.2f}<extra></extra>",
                ))
                fig_ind.add_hline(y=0, line_dash="dash", line_color="#484f58")
                fig_ind.update_layout(
                    height=220, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(gridcolor="#21262d"),
                    yaxis=dict(gridcolor="#21262d", title="Score"),
                    showlegend=False,
                )
                st.plotly_chart(fig_ind, use_container_width=True)
            else:
                # Show raw indicator details if no scores dict
                details = {k: v for k, v in ind.items() if k != "scores"}
                if details:
                    ind_html = '<div class="ind-grid">'
                    for k, v in details.items():
                        display = f"{v:.3f}" if isinstance(v, float) else str(v)
                        ind_html += f"""
                        <div class="ind-chip">
                            <div class="ind-chip-name">{k.replace('_', ' ').title()}</div>
                            <div class="ind-chip-val">{display}</div>
                        </div>"""
                    ind_html += '</div>'
                    st.markdown(ind_html, unsafe_allow_html=True)

        # ── Trade history table ──────────────────────────────────────────
        st.markdown('<div class="section-hdr">Trade History</div>', unsafe_allow_html=True)
        display_trades = []
        for t in reversed(btc_trades):
            row = {
                "Time": t.get("timestamp", "")[:19].replace("T", " "),
                "Direction": t.get("direction", "—"),
                "Bet Size": f"${t.get('bet_size', 0):.2f}",
                "Edge": f"{t.get('edge', 0) * 100:.1f}%",
                "Market Price": f"{t.get('market_price', 0):.3f}",
                "BTC Price": f"${t.get('btc_price', 0):,.2f}",
            }
            # Include confidence/score if present
            if "confidence" in t:
                row["Confidence"] = f"{t['confidence']:.0%}"
            if "score" in t:
                row["Score"] = f"{t['score']:+.1f}"
            # Result
            if t.get("resolved"):
                row["Result"] = "WIN" if t.get("won") else "LOSS"
                row["PnL"] = fmt_pnl(t.get("pnl", 0))
            else:
                row["Result"] = "PENDING"
                row["PnL"] = "—"
            display_trades.append(row)

        if display_trades:
            st.dataframe(
                pd.DataFrame(display_trades),
                use_container_width=True,
                hide_index=True,
                height=min(400, 35 * len(display_trades) + 38),
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — CRYPTO AGENTS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_crypto:
    stats = apex_state.get("stats", {})
    last_signals = apex_state.get("last_signals", {})
    cycle = apex_state.get("cycle", 0)
    mode = apex_state.get("mode", "paper")

    # ── Global stats ─────────────────────────────────────────────────────
    total_crypto_pnl = stats.get("total_pnl", 0)
    win_rate = stats.get("win_rate", 0)

    st.markdown(f"""<div class="stats-bar">
        {sbar("", mode.upper(), "Mode")}
        {sbar("", cycle, "Cycle")}
        {sbar("", stats.get("total_trades", 0), "Trades")}
        {sbar("", stats.get("open", 0), "Open")}
        {sbar("", stats.get("closed", 0), "Closed")}
        {sbar("", f"{win_rate}%", "Win Rate", "pos" if win_rate >= 50 else ("neg" if stats.get("closed", 0) > 0 else "neu"))}
        {sbar("", fmt_pnl(total_crypto_pnl), "Net PnL", pnl_cls(total_crypto_pnl))}
    </div>""", unsafe_allow_html=True)

    # ── Agent cards ──────────────────────────────────────────────────────
    AGENT_META = {
        "ATLAS":    {"sprite": "&#9875;", "color": "#58a6ff",  "desc": "SMA + ADX + Volume"},
        "ORACLE":   {"sprite": "&#128302;", "color": "#3fb950",  "desc": "MACD + RSI + HTF"},
        "SNIPER":   {"sprite": "&#127919;", "color": "#d29922",  "desc": "Regime-switching"},
        "SENTINEL": {"sprite": "&#128752;", "color": "#bc8cff",  "desc": "EMA + Keltner Squeeze"},
    }

    ACH = {
        "First Blood": "&#128169;", "Sharp Shooter": "&#127919;", "Profit Hunter": "&#128176;",
        "Diamond Hands": "&#128142;", "Sniper": "&#128299;", "Unstoppable": "&#128640;",
    }

    def check_ach(r: dict) -> list[str]:
        u = []
        if r.get("total_pnl", 0) > 0:
            u.append("First Blood")
        if r.get("win_rate", 0) >= 50:
            u.append("Sharp Shooter")
        if r.get("total_pnl", 0) >= 50:
            u.append("Profit Hunter")
        if r.get("total_trades", 0) >= 100:
            u.append("Diamond Hands")
        if r.get("total_trades", 0) >= 10 and r.get("win_rate", 0) >= 60:
            u.append("Sniper")
        if r.get("total_pnl", 0) >= 100:
            u.append("Unstoppable")
        return u

    def xp_from(r: dict) -> int:
        v = max(0, int(r.get("total_pnl", 0) * 2))
        v += max(0, int(r.get("win_rate", 0)))
        v += min(r.get("total_trades", 0) * 2, 200)
        return max(v, 0)

    st.markdown('<div class="section-hdr">Agent Status</div>', unsafe_allow_html=True)
    st.markdown('<div class="floor-grid">', unsafe_allow_html=True)

    agent_pnl_data = {}
    for agent_name, meta in AGENT_META.items():
        sigs = last_signals.get(agent_name, [])
        is_sig = len(sigs) > 0
        sd = "status-active" if is_sig else "status-inactive"
        sl = "SIGNAL" if is_sig else "WATCHING"

        # Per-agent stats from trade log
        ar = {"total_trades": 0, "win_rate": 0, "total_pnl": 0, "wins": 0, "losses": 0, "open": 0}
        if not trades_df.empty and "agent" in trades_df.columns:
            ag = trades_df[trades_df["agent"] == agent_name]
            cl = ag[ag["status"].isin(["WIN", "LOSS"])]
            w = cl[cl["status"] == "WIN"]
            op = ag[ag["status"] == "OPEN"]
            ar["total_trades"] = len(ag)
            ar["open"] = len(op)
            ar["wins"] = len(w)
            ar["losses"] = len(cl) - len(w)
            ar["win_rate"] = round(len(w) / len(cl) * 100, 1) if len(cl) > 0 else 0
            ar["total_pnl"] = round(cl["pnl"].sum(), 2) if "pnl" in cl.columns else 0

        agent_pnl_data[agent_name] = ar

        x = xp_from(ar)
        lv = x // 100
        prog = min(x % 100, 100)
        sc = pnl_cls(ar["total_pnl"])
        achs = check_ach(ar)
        ach_html = "".join(
            f'<span class="ach-badge">{ACH.get(a, "&#11088;")} {a}</span>'
            for a in achs
        ) or '<span style="color:#484f58;font-size:10px;">No achievements yet</span>'

        sig_html = ""
        for s in sigs[:2]:
            dc = "pos" if s.get("signal") == "BUY" else "neg"
            sig_html += (
                f'<div style="margin-top:6px;font-size:11px;color:#8b949e;">'
                f'<span style="color:{meta["color"]}">{html_lib.escape(str(s.get("asset", "")))}</span> '
                f'<span class="{dc}">{html_lib.escape(str(s.get("signal", "")))}</span> '
                f'@ {s.get("entry_price", 0):.4f}  str={s.get("strength", 0):.2f}</div>'
            )

        st.markdown(f"""
        <div class="station-card" style="border-top:3px solid {meta['color']};">
            <div class="station-header">
                <div>
                    <div class="station-name">{meta['sprite']} {agent_name}</div>
                    <div class="station-sub">{meta['desc']}</div>
                </div>
                <div class="status-wrap">
                    <span class="status-dot {sd}"></span>
                    <span style="color:#8b949e;font-size:11px;">{sl}</span>
                </div>
            </div>
            <div class="xp-label"><span>Level {lv}</span><span>{x} XP</span></div>
            <div class="xp-track"><div class="xp-fill" style="width:{prog}%;"></div></div>
            <div class="card-stats">
                <div class="card-stat"><div class="card-stat-val {sc}">${ar['total_pnl']:+.2f}</div><div class="card-stat-lbl">PnL</div></div>
                <div class="card-stat"><div class="card-stat-val">{ar['win_rate']}%</div><div class="card-stat-lbl">Win Rate</div></div>
                <div class="card-stat"><div class="card-stat-val">{ar['total_trades']}</div><div class="card-stat-lbl">Trades</div></div>
                <div class="card-stat"><div class="card-stat-val pos">{ar['open']}</div><div class="card-stat-lbl">Open</div></div>
            </div>
            {sig_html}
            <div class="ach-row">{ach_html}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── PnL by agent chart ───────────────────────────────────────────────
    if agent_pnl_data and any(v["total_trades"] > 0 for v in agent_pnl_data.values()):
        st.markdown('<div class="section-hdr">PnL by Agent</div>', unsafe_allow_html=True)

        agent_names = list(agent_pnl_data.keys())
        agent_pnls = [agent_pnl_data[a]["total_pnl"] for a in agent_names]
        agent_colors_map = {
            "ATLAS": "#58a6ff", "ORACLE": "#3fb950",
            "SNIPER": "#d29922", "SENTINEL": "#bc8cff",
        }

        fig_agent = go.Figure(go.Bar(
            x=agent_names,
            y=agent_pnls,
            marker_color=[agent_colors_map.get(a, "#58a6ff") for a in agent_names],
            hovertemplate="%{x}: $%{y:+.2f}<extra></extra>",
        ))
        fig_agent.add_hline(y=0, line_dash="dash", line_color="#484f58")
        fig_agent.update_layout(
            height=280, template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(gridcolor="#21262d"),
            yaxis=dict(gridcolor="#21262d", title="PnL ($)"),
            showlegend=False,
        )
        st.plotly_chart(fig_agent, use_container_width=True)

    # ── Equity curve by agent ────────────────────────────────────────────
    if not trades_df.empty and "pnl" in trades_df.columns:
        cl_df = trades_df[trades_df["status"].isin(["WIN", "LOSS"])].copy()
        if not cl_df.empty and "closed_at" in cl_df.columns:
            st.markdown('<div class="section-hdr">Equity Curve</div>', unsafe_allow_html=True)
            cl_df["closed_at"] = pd.to_datetime(cl_df["closed_at"], utc=True, errors="coerce")
            cl_df = cl_df.sort_values("closed_at").dropna(subset=["closed_at"])
            cl_df["cum_pnl"] = cl_df["pnl"].cumsum()
            fig_eq = go.Figure()
            for ag in cl_df["agent"].unique():
                adf = cl_df[cl_df["agent"] == ag]
                fig_eq.add_trace(go.Scatter(
                    x=adf["closed_at"], y=adf["cum_pnl"].values,
                    name=ag, mode="lines+markers", line=dict(width=2), marker=dict(size=4),
                ))
            fig_eq.add_hline(y=0, line_dash="dash", line_color="#484f58")
            fig_eq.update_layout(
                height=300, template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor="#21262d"),
                yaxis=dict(gridcolor="#21262d", title="Cumulative PnL ($)"),
                hovermode="x unified",
            )
            st.plotly_chart(fig_eq, use_container_width=True)

    # ── Open positions table ─────────────────────────────────────────────
    if not trades_df.empty and "status" in trades_df.columns:
        open_df = trades_df[trades_df["status"] == "OPEN"].copy()
        if not open_df.empty:
            st.markdown('<div class="section-hdr">Open Positions</div>', unsafe_allow_html=True)
            cols = [c for c in ["opened_at", "agent", "asset", "direction", "entry_price",
                                "stop_loss", "take_profit", "amount"]
                    if c in open_df.columns]
            disp = open_df.sort_values("opened_at", ascending=False)[cols]
            st.dataframe(disp, use_container_width=True, hide_index=True)

    # ── Recent signals ───────────────────────────────────────────────────
    if last_signals:
        all_sigs = []
        for agent_name, sigs in last_signals.items():
            for s in sigs:
                all_sigs.append({
                    "Agent": agent_name,
                    "Asset": s.get("asset", ""),
                    "Signal": s.get("signal", ""),
                    "Strength": f"{s.get('strength', 0):.2f}",
                    "Entry": f"${s.get('entry_price', 0):,.2f}",
                    "Stop Loss": f"${s.get('stop_loss', 0):,.2f}",
                    "Take Profit": f"${s.get('take_profit', 0):,.2f}",
                })
        if all_sigs:
            st.markdown('<div class="section-hdr">Recent Signals</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(all_sigs), use_container_width=True, hide_index=True)

    if trades_df.empty and not last_signals:
        st.markdown('<div class="no-data">No crypto agent data yet. Waiting for first cycle...</div>',
                    unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 4 — POLYMARKET SCANNER
# ═══════════════════════════════════════════════════════════════════════════════
with tab_scanner:
    # ── Sniper positions ─────────────────────────────────────────────────
    if isinstance(sniper_state, dict):
        sniper_trades = sniper_state.get("trades", [])
        if not sniper_trades:
            for cid, pos in sniper_state.get("positions", {}).items():
                sniper_trades.append({**pos, "condition_id": cid, "resolved": False})
            sniper_trades.extend(sniper_state.get("history", []))
        sniper_bankroll_val = sniper_state.get("bankroll", 0)
    else:
        sniper_trades = []
        sniper_bankroll_val = 0

    if not sniper_trades and not scan_results:
        st.markdown(
            '<div class="no-data">No Polymarket scanner data yet. '
            'Waiting for first scan...</div>',
            unsafe_allow_html=True,
        )
    else:
        # ── Stats bar ────────────────────────────────────────────────
        if sniper_trades:
            s_resolved = [t for t in sniper_trades if t.get("resolved")]
            s_wins = [t for t in s_resolved if t.get("won")]
            s_pnl = sum(t.get("pnl", 0) for t in s_resolved)
            s_wr = (len(s_wins) / len(s_resolved) * 100) if s_resolved else 0

            st.markdown(f"""<div class="stats-bar">
                {sbar("", f"${sniper_bankroll_val:,.2f}", "Bankroll", "pos" if sniper_bankroll_val > 0 else "neu")}
                {sbar("", fmt_pnl(s_pnl), "Total PnL", pnl_cls(s_pnl))}
                {sbar("", f"{s_wr:.0f}%", "Win Rate", "pos" if s_wr >= 50 else "neg")}
                {sbar("", len(sniper_trades), "Trades", "")}
                {sbar("", len(s_resolved), "Resolved", "")}
            </div>""", unsafe_allow_html=True)

        # ── Current positions ────────────────────────────────────────
        open_sniper = [t for t in sniper_trades if not t.get("resolved")]
        if open_sniper:
            st.markdown('<div class="section-hdr">Open Positions</div>', unsafe_allow_html=True)
            pos_display = []
            for t in open_sniper:
                pos_display.append({
                    "Market": t.get("question", t.get("market", "—"))[:60],
                    "Side": t.get("side", t.get("direction", "—")),
                    "Bet": f"${t.get('bet_size', 0):.2f}",
                    "Edge": f"{t.get('edge', 0) * 100:.1f}%",
                    "Price": f"{t.get('market_price', t.get('price', 0)):.3f}",
                    "Time": str(t.get("timestamp", ""))[:19],
                })
            st.dataframe(pd.DataFrame(pos_display), use_container_width=True, hide_index=True)

        # ── Scan results ─────────────────────────────────────────────
        if scan_results:
            st.markdown('<div class="section-hdr">Latest Scan Results</div>', unsafe_allow_html=True)

            if isinstance(scan_results, list):
                scan_list = scan_results
            elif isinstance(scan_results, dict):
                scan_list = scan_results.get("results", scan_results.get("markets", []))
                if not scan_list and "question" in scan_results:
                    scan_list = [scan_results]
            else:
                scan_list = []

            if scan_list:
                scan_display = []
                edges = []
                for r in scan_list[:50]:
                    edge = r.get("edge", r.get("kelly_edge", 0))
                    edges.append(edge)
                    scan_display.append({
                        "Market": str(r.get("question", r.get("market", "—")))[:60],
                        "Edge": f"{edge * 100:.1f}%" if isinstance(edge, (int, float)) else str(edge),
                        "Confidence": f"{r.get('confidence', r.get('true_prob', 0)):.1%}",
                        "Price": f"{r.get('price', r.get('market_price', 0)):.3f}",
                    })
                st.dataframe(pd.DataFrame(scan_display), use_container_width=True, hide_index=True)

                # Edge distribution chart
                edges_pct = [e * 100 for e in edges if isinstance(e, (int, float)) and e != 0]
                if edges_pct:
                    st.markdown('<div class="section-hdr">Edge Distribution</div>',
                                unsafe_allow_html=True)
                    fig_edge = go.Figure(go.Histogram(
                        x=edges_pct,
                        nbinsx=20,
                        marker_color="#58a6ff",
                        hovertemplate="Edge: %{x:.1f}%<br>Count: %{y}<extra></extra>",
                    ))
                    fig_edge.update_layout(
                        height=250, template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0, r=0, t=10, b=0),
                        xaxis=dict(gridcolor="#21262d", title="Edge (%)"),
                        yaxis=dict(gridcolor="#21262d", title="Count"),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_edge, use_container_width=True)
            else:
                st.markdown('<div class="no-data">Scan results file exists but no markets found.</div>',
                            unsafe_allow_html=True)

        # ── Trade history ────────────────────────────────────────────
        resolved_sniper = [t for t in sniper_trades if t.get("resolved")]
        if resolved_sniper:
            st.markdown('<div class="section-hdr">Resolved Trades</div>', unsafe_allow_html=True)
            res_display = []
            for t in reversed(resolved_sniper):
                res_display.append({
                    "Market": str(t.get("question", t.get("market", "—")))[:60],
                    "Side": t.get("side", t.get("direction", "—")),
                    "Bet": f"${t.get('bet_size', 0):.2f}",
                    "Edge": f"{t.get('edge', 0) * 100:.1f}%",
                    "Result": "WIN" if t.get("won") else "LOSS",
                    "PnL": fmt_pnl(t.get("pnl", 0)),
                })
            st.dataframe(pd.DataFrame(res_display), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 5 — COPY TRADER (COMING SOON)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_copy:
    copy_status = load_json(POLY_DIR / "copy_trader_status.json")

    if not copy_status:
        st.markdown(
            '<div class="no-data">Copy Trader not started yet. '
            'Run: <code>uv run python3 polymarket/copy_trader.py</code></div>',
            unsafe_allow_html=True,
        )
    else:
        # -- Stats bar
        c_bankroll = copy_status.get("bankroll", 0)
        c_history = copy_status.get("history", [])
        c_positions = copy_status.get("positions", {})
        c_resolved = [h for h in c_history if h.get("resolved")]
        c_wins = sum(1 for h in c_resolved if h.get("won"))
        c_total = len(c_resolved)
        c_pnl = sum(h.get("pnl", 0) for h in c_resolved)
        c_wr = round(c_wins / c_total * 100) if c_total else 0
        c_wallets = copy_status.get("total_wallets_tracked", 0)
        c_cooldown = copy_status.get("cooldown_until")

        st.markdown(f"""<div class="stats-bar">
            {sbar("", f"${c_bankroll:,.2f}", "Bankroll", "pos" if c_bankroll > 0 else "neu")}
            {sbar("", fmt_pnl(c_pnl), "Total PnL", pnl_cls(c_pnl))}
            {sbar("", f"{c_wr}%", "Win Rate", "pos" if c_wr >= 50 else ("neg" if c_total else "neu"))}
            {sbar("", len(c_positions), "Open", "")}
            {sbar("", c_total, "Closed", "")}
            {sbar("", c_wallets, "Wallets Tracked", "")}
        </div>""", unsafe_allow_html=True)

        if c_cooldown:
            st.markdown(
                f'<div class="no-data" style="padding:12px;color:#d29922;">'
                f'Cooling down until {c_cooldown[:19]}</div>',
                unsafe_allow_html=True,
            )

        # -- Top Traders Leaderboard
        top_traders = copy_status.get("top_traders", [])
        if top_traders:
            st.markdown('<div class="section-hdr">Top Whale Leaderboard</div>',
                        unsafe_allow_html=True)
            leader_rows = []
            for i, t in enumerate(top_traders[:10], 1):
                addr = t.get("address", "")
                leader_rows.append({
                    "#": i,
                    "Wallet": f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr,
                    "Win Rate": f"{t.get('win_rate', 0)}%",
                    "Resolved": t.get("resolved", 0),
                    "PnL": fmt_pnl(t.get("net_pnl", 0)),
                    "Volume": f"${t.get('volume', 0):,.0f}",
                })
            st.dataframe(pd.DataFrame(leader_rows), use_container_width=True, hide_index=True)

        # -- Open Positions
        if c_positions:
            st.markdown('<div class="section-hdr">Open Copy Positions</div>',
                        unsafe_allow_html=True)
            pos_rows = []
            for cid, pos in c_positions.items():
                addr = pos.get("whale_address", "")
                pos_rows.append({
                    "Direction": pos.get("direction", "?"),
                    "Bet": f"${pos.get('bet_size', 0):.2f}",
                    "Whale Size": f"${pos.get('whale_size', 0):,.0f}",
                    "Whale": f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr,
                    "Top Trader": "Y" if pos.get("is_top_trader") else "N",
                    "Time": str(pos.get("timestamp", ""))[:19],
                })
            st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)

        # -- Trade History
        if c_resolved:
            st.markdown('<div class="section-hdr">Copy Trade History</div>',
                        unsafe_allow_html=True)
            hist_rows = []
            for h in reversed(c_resolved[-20:]):
                addr = h.get("whale_address", "")
                hist_rows.append({
                    "Direction": h.get("direction", "?"),
                    "Bet": f"${h.get('bet_size', 0):.2f}",
                    "Whale": f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr,
                    "Result": "WIN" if h.get("won") else "LOSS",
                    "PnL": fmt_pnl(h.get("pnl", 0)),
                    "Time": str(h.get("timestamp", ""))[:19],
                })
            st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)

            # PnL chart
            if len(c_resolved) >= 2:
                cum = 0
                pnl_data = []
                for h in c_resolved:
                    cum += h.get("pnl", 0)
                    pnl_data.append({"trade": len(pnl_data) + 1, "pnl": cum,
                                     "won": h.get("won", False)})
                pnl_df = pd.DataFrame(pnl_data)
                fig_copy = go.Figure(go.Scatter(
                    x=pnl_df["trade"], y=pnl_df["pnl"],
                    mode="lines+markers",
                    line=dict(color="#58a6ff", width=2),
                    marker=dict(
                        size=6,
                        color=["#3fb950" if w else "#f85149" for w in pnl_df["won"]],
                    ),
                    fill="tozeroy", fillcolor="rgba(88,166,255,0.1)",
                ))
                fig_copy.add_hline(y=0, line_dash="dash", line_color="#484f58")
                fig_copy.update_layout(
                    height=250, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(gridcolor="#21262d", title="Trade #"),
                    yaxis=dict(gridcolor="#21262d", title="Cumulative PnL ($)"),
                    showlegend=False,
                )
                st.plotly_chart(fig_copy, use_container_width=True)


# ── Auto-refresh ─────────────────────────────────────────────────────────────
# Streamlit reruns on interaction; add a timed auto-refresh via session state
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

elapsed = time.time() - st.session_state.last_refresh
if elapsed >= REFRESH_S:
    st.session_state.last_refresh = time.time()
    st.rerun()

# Footer with refresh countdown
remaining = max(0, int(REFRESH_S - elapsed))
st.markdown(
    f'<div style="text-align:center; color:#484f58; font-size:11px; margin-top:20px; padding-bottom:10px;">'
    f'APEX Trading HQ &mdash; Auto-refresh in {remaining}s'
    f'</div>',
    unsafe_allow_html=True,
)
