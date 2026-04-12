"""
APEX Trading HQ — Unified Dashboard
Tab 1 — APEX       : crypto perps (Lighter.xyz), 4 agents, live PnL, Go Live toggle
Tab 2 — Pocket Option : Signal Engine forex signals (XAU/USD, USD/JPY, GBP/USD…)

Run:
  uv run streamlit run dashboard/app.py   (from apex/ root)

Control files (logs/):
  .go_live  — created by Go Live button → watchdog restarts apex_bot --live
  .paused   — created by Telegram /pause command
"""
import json
import os
import time
import html as html_lib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="APEX Trading HQ",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
* { font-family:'Inter',sans-serif !important; }
.block-container { padding:14px 22px !important; }

.stats-bar {
    display:flex; gap:10px; padding:14px; margin-bottom:12px;
    background:#161b22; border-radius:14px; border:1px solid #30363d; flex-wrap:wrap;
}
.stat-item {
    display:flex; flex-direction:column; align-items:center;
    padding:10px 14px; border-radius:10px; background:#0d1117;
    border:1px solid #21262d; min-width:85px; text-align:center;
}
.stat-value { font-size:22px; font-weight:700; }
.stat-label { font-size:10px; color:#8b949e; margin-top:3px; text-transform:uppercase; letter-spacing:.5px; }

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
.status-wrap  { display:flex; align-items:center; gap:6px; font-size:12px; }
.status-dot   { width:8px; height:8px; border-radius:50%; display:inline-block; }
.status-active   { background:#3fb950; box-shadow:0 0 8px #3fb950; animation:pulse 1.5s infinite; }
.status-inactive { background:#484f58; }
.status-live     { background:#f85149; box-shadow:0 0 10px #f85149; animation:pulse .8s infinite; }
@keyframes pulse { 0%,100%{opacity:1}50%{opacity:.4} }

.xp-track { width:100%; height:5px; background:#21262d; border-radius:3px; margin:8px 0; overflow:hidden; }
.xp-fill  { height:100%; border-radius:3px; background:linear-gradient(90deg,#58a6ff,#bc8cff); }
.xp-label { display:flex; justify-content:space-between; font-size:10px; color:#8b949e; margin-bottom:6px; }

.card-stats { display:grid; grid-template-columns:1fr 1fr; gap:7px; margin-top:10px; }
.card-stat  { background:#0d1117; padding:9px 7px; border-radius:7px; text-align:center; border:1px solid #21262d; }
.card-stat-val { font-size:15px; font-weight:700; }
.card-stat-lbl { font-size:9px; color:#8b949e; margin-top:2px; text-transform:uppercase; letter-spacing:.3px; }
.pos { color:#3fb950; }
.neg { color:#f85149; }
.neu { color:#8b949e; }

.ach-row { margin-top:10px; display:flex; flex-wrap:wrap; gap:5px; }
.ach-badge {
    background:linear-gradient(135deg,#1a3a4a,#161b22);
    border:1px solid #30363d; border-radius:8px; padding:3px 9px;
    font-size:10px; color:#e6edf3; display:inline-flex; align-items:center; gap:3px;
}

.section-hdr {
    font-size:16px; font-weight:700; color:#e6edf3; margin:20px 0 10px;
    display:flex; align-items:center; gap:7px;
}

/* Live Control Panel */
.live-panel {
    border-radius:14px; padding:22px; margin:16px 0;
    border:2px solid #30363d; background:#0d1117;
}
.live-panel.is-live  { border-color:#f85149; background:#1a0a0a; }
.live-panel.is-paper { border-color:#30363d; background:#0d1117; }
.live-status-badge {
    display:inline-flex; align-items:center; gap:8px;
    padding:6px 18px; border-radius:20px; font-size:13px; font-weight:700;
}
.live-status-badge.live  { background:#2d0a0a; color:#f85149; border:1px solid #f85149; }
.live-status-badge.paper { background:#0d1a0d; color:#3fb950; border:1px solid #3fb950; }
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
.proc-badge.live    { background:#2d0a0a; color:#f85149; border:1px solid #da3633; }
.proc-badge.dead    { background:#2d1a0a; color:#d29922; border:1px solid #9e6a03; }
.proc-badge.stopped { background:#1a1a1a; color:#484f58; border:1px solid #30363d; }
.proc-badge.always-live { background:#1a0d2b; color:#bc8cff; border:1px solid #8957e5; }

/* Trophy */
.trophy-room { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:8px; margin:12px 0; }
.trophy { background:#161b22; border:1px solid #30363d; border-radius:9px; padding:10px; text-align:center; }
.trophy:hover { border-color:#d29922; }
.trophy-locked { opacity:.2; }

/* Pocket Option */
.po-hdr { color:#58a6ff; font-size:13px; letter-spacing:3px; margin:18px 0 6px; font-family:'Share Tech Mono',monospace; font-weight:700; }
.session-badge { display:inline-block; padding:3px 12px; border-radius:10px; font-size:11px; font-weight:600;
    background:#1a3a4a; color:#58a6ff; border:1px solid #1f4a6a; }
</style>
""", unsafe_allow_html=True)

# ── Paths ─────────────────────────────────────────────────────────────────────
_APEX_ROOT   = Path(__file__).parent.parent
_SE_ROOT     = Path.home() / "signal_engine"
LOGS_DIR     = _APEX_ROOT / "logs"
STATE_FILE   = Path(os.getenv("STATE_FILE",  str(LOGS_DIR / "state.json")))
STATUS_FILE  = Path(os.getenv("STATUS_FILE", str(LOGS_DIR / "watchdog_status.json")))
SIGNALS_LOG  = Path(os.getenv("SIGNALS_LOG", str(_SE_ROOT / "signals_log.jsonl")))
SE_CFG_FILE  = Path(os.getenv("SE_CONFIG",   str(_SE_ROOT / "engine_config.json")))
PAPER_LOG    = LOGS_DIR / "paper_trades.jsonl"
LIVE_FILE    = LOGS_DIR / ".go_live"      # controls apex_bot live mode
PAUSE_FILE   = LOGS_DIR / ".paused"

LOGS_DIR.mkdir(exist_ok=True)
REFRESH_S = 30


def load_json(p):
    try:
        if Path(p).exists():
            with open(p) as f:
                return json.load(f)
    except Exception:
        pass
    return None


# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_apex, tab_po = st.tabs(["⚡  APEX — Crypto Perps", "🎯  Pocket Option — Signal Engine"])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — APEX
# ══════════════════════════════════════════════════════════════════════════════
with tab_apex:

    apex_state  = load_json(STATE_FILE)
    wdog_status = load_json(STATUS_FILE)
    procs       = (wdog_status or {}).get("processes", {})

    # ── Current mode (from control file, not state.json) ──────────────────
    is_live   = LIVE_FILE.exists()
    is_paused = PAUSE_FILE.exists()
    mode_str  = "LIVE" if is_live else "PAPER"
    stats     = (apex_state or {}).get("stats", {})
    cycle     = (apex_state or {}).get("cycle", 0)
    updated   = (apex_state or {}).get("updated_at", "")[:19].replace("T", " ")

    # ── Global stats bar ──────────────────────────────────────────────────
    total_pnl  = stats.get("total_pnl", 0)
    win_rate   = stats.get("win_rate", 0)
    pnl_cls    = "pos" if total_pnl >= 0 else "neg"

    def sbar(icon, val, lbl, cls=""):
        return (f'<div class="stat-item">'
                f'<div class="stat-value {cls}">{icon} {html_lib.escape(str(val))}</div>'
                f'<div class="stat-label">{lbl}</div></div>')

    pause_tag = " ⏸" if is_paused else ""
    st.markdown(f"""<div class="stats-bar">
        {sbar("🔴" if is_live else "📋", mode_str + pause_tag, "Mode")}
        {sbar("🔁", cycle, "Cycle")}
        {sbar("🧾", stats.get("total_trades", 0), "Trades")}
        {sbar("📂", stats.get("open", 0), "Open")}
        {sbar("✅", stats.get("closed", 0), "Closed")}
        {sbar("🎯", f"{win_rate}%", "Win Rate", "pos" if win_rate >= 50 else ("neg" if stats.get("closed",0) > 0 else "neu"))}
        {sbar("💰", f"${total_pnl:+.2f}", "Net PnL", pnl_cls)}
        <div class="stat-item"><div class="stat-value" style="font-size:11px;color:#484f58;">{updated or "—"}</div>
        <div class="stat-label">Last Update UTC</div></div>
    </div>""", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    #  LIVE CONTROL PANEL
    # ══════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-hdr">🎛️ Live Control</div>', unsafe_allow_html=True)

    panel_cls  = "is-live" if is_live else "is-paper"
    badge_cls  = "live"    if is_live else "paper"
    badge_txt  = "🔴 LIVE TRADING" if is_live else "📋 PAPER MODE"
    st.markdown(f'<div class="live-panel {panel_cls}">', unsafe_allow_html=True)

    ctrl_l, ctrl_r = st.columns([2, 1])
    with ctrl_l:
        st.markdown(
            f'<div style="margin-bottom:14px;">'
            f'<span class="live-status-badge {badge_cls}">{badge_txt}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Process status rows
        PROC_LABELS = {
            "apex_bot":          ("⚡ APEX Bot",          "Lighter.xyz crypto perps"),
            "telegram_bot":      ("📱 Telegram Bot",       "Command interface"),
            "polymarket_sniper": ("🎯 Polymarket Sniper",  "Binary prediction markets"),
            "signal_engine":     ("📡 Signal Engine",      "Pocket Option forex — ALWAYS LIVE"),
            "wolf_bot":          ("🐺 Wolf Bot",           "Polymarket / Kalshi"),
        }
        for proc_key, (label, sub) in PROC_LABELS.items():
            info = procs.get(proc_key, {})
            pstatus = info.get("status", "unknown")
            pmode   = info.get("mode", "")
            always  = info.get("always_live", False)

            if always:
                badge = '<span class="proc-badge always-live">⭐ ALWAYS LIVE</span>'
            elif pstatus == "running" and pmode == "live":
                badge = '<span class="proc-badge live">🔴 LIVE</span>'
            elif pstatus == "running":
                badge = '<span class="proc-badge running">🟢 RUNNING</span>'
            elif pstatus == "dead":
                badge = '<span class="proc-badge dead">⚠️ CRASHED</span>'
            elif pstatus == "not_started":
                badge = '<span class="proc-badge stopped">⏹ STOPPED</span>'
            else:
                badge = '<span class="proc-badge stopped">— OFFLINE</span>'

            pid_txt = f" · pid {info['pid']}" if info.get("pid") else ""
            st.markdown(
                f'<div class="proc-row">'
                f'<div><div class="proc-name">{label}</div>'
                f'<div class="proc-sub">{sub}{pid_txt}</div></div>'
                f'{badge}</div>',
                unsafe_allow_html=True,
            )

    with ctrl_r:
        st.markdown("**Switch Trading Mode**")
        st.markdown(
            '<div style="font-size:12px;color:#8b949e;margin-bottom:12px;">'
            'Signal Engine is <b>not affected</b> by this toggle.<br>'
            'It always runs live during market hours.</div>',
            unsafe_allow_html=True,
        )

        if is_live:
            # Currently LIVE — offer Go Paper
            if st.button("📋 Switch to PAPER", type="secondary", use_container_width=True):
                LIVE_FILE.unlink(missing_ok=True)
                st.success("Switched to PAPER. Watchdog will restart apex_bot.")
                time.sleep(1)
                st.rerun()
        else:
            # Currently PAPER — offer Go Live
            st.warning("Going live uses real money on Lighter.xyz.")
            confirm = st.checkbox("I understand — use real funds")
            if confirm:
                from configs.config import LIGHTER_API_KEY_ID
                if not LIGHTER_API_KEY_ID:
                    st.error("LIGHTER_API_KEY_ID not set. Add to .env first.")
                else:
                    if st.button("🔴 GO LIVE", type="primary", use_container_width=True):
                        LIVE_FILE.touch()
                        st.success("LIVE file created. Watchdog will restart apex_bot --live.")
                        time.sleep(1)
                        st.rerun()
            else:
                st.button("🔴 GO LIVE", type="primary", use_container_width=True, disabled=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    #  AGENT CARDS
    # ══════════════════════════════════════════════════════════════════════
    AGENT_META = {
        "ATLAS":    {"sprite": "⚓", "color": "#58a6ff",  "desc": "SMA + ADX + Volume"},
        "ORACLE":   {"sprite": "🔮", "color": "#3fb950",  "desc": "MACD + RSI + HTF"},
        "SNIPER":   {"sprite": "🎯", "color": "#d29922",  "desc": "Regime-switching"},
        "SENTINEL": {"sprite": "🛰️", "color": "#bc8cff",  "desc": "EMA + Keltner Squeeze"},
    }
    ACH = {
        "First Blood": "🩸", "Sharp Shooter": "🎯", "Profit Hunter": "💰",
        "Diamond Hands": "💎", "Sniper": "🔫", "Unstoppable": "🚀",
        "Risk Master": "🛡️", "Veteran": "⭐", "Comeback King": "♻️",
    }

    def check_ach(r):
        u = []
        if r.get("total_pnl", 0) > 0:        u.append("First Blood")
        if r.get("win_rate", 0) >= 50:        u.append("Sharp Shooter")
        if r.get("total_pnl", 0) >= 50:       u.append("Profit Hunter")
        if r.get("total_trades", 0) >= 100:   u.append("Diamond Hands")
        if r.get("total_trades",0)>=10 and r.get("win_rate",0)>=60: u.append("Sniper")
        if r.get("total_pnl", 0) >= 100:      u.append("Unstoppable")
        if r.get("total_trades", 0) > 0:      u.append("Risk Master")
        if r.get("total_trades", 0) >= 500:   u.append("Veteran")
        return u

    def xp_from(r):
        v  = max(0, int(r.get("total_pnl",    0) * 2))
        v += max(0, int(r.get("win_rate",      0)))
        v += min(r.get("total_trades", 0) * 2, 200)
        return max(v, 0)

    # Load paper trades
    trades_df = pd.DataFrame()
    if PAPER_LOG.exists():
        rows = []
        for line in PAPER_LOG.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        if rows:
            trades_df = pd.DataFrame(rows)

    last_signals = (apex_state or {}).get("last_signals", {})

    st.markdown('<div class="section-hdr">🛰️ Mission Control</div>', unsafe_allow_html=True)
    st.markdown('<div class="floor-grid">', unsafe_allow_html=True)

    for agent_name, meta in AGENT_META.items():
        sigs    = last_signals.get(agent_name, [])
        is_sig  = len(sigs) > 0
        sd      = "status-live" if (is_sig and is_live) else ("status-active" if is_sig else "status-inactive")
        sl      = ("🔴 LIVE SIGNAL" if is_live else "📋 SIGNAL") if is_sig else "WATCHING"

        # Per-agent stats
        ar = {"total_trades": 0, "win_rate": 0, "total_pnl": 0, "wins": 0, "losses": 0, "open": 0}
        if not trades_df.empty and "agent" in trades_df.columns:
            ag   = trades_df[trades_df["agent"] == agent_name]
            cl   = ag[ag["status"].isin(["WIN", "LOSS"])]
            w    = cl[cl["status"] == "WIN"]
            op   = ag[ag["status"] == "OPEN"]
            ar["total_trades"] = len(ag)
            ar["open"]         = len(op)
            ar["wins"]         = len(w)
            ar["losses"]       = len(cl) - len(w)
            ar["win_rate"]     = round(len(w)/len(cl)*100,1) if len(cl)>0 else 0
            ar["total_pnl"]    = round(cl["pnl"].sum(),2) if "pnl" in cl.columns else 0

        x    = xp_from(ar)
        lv   = x // 100
        prog = min(x % 100, 100)
        sc   = "pos" if ar["total_pnl"] >= 0 else "neg"
        achs = check_ach(ar)
        ach_html = "".join(
            f'<span class="ach-badge">{ACH.get(a,"⭐")} {a}</span>'
            for a in achs
        ) or '<span style="color:#484f58;font-size:10px;">No achievements yet</span>'

        sig_html = ""
        for s in sigs[:2]:
            dc = "pos" if s.get("signal") == "BUY" else "neg"
            sig_html += (
                f'<div style="margin-top:6px;font-size:11px;color:#8b949e;">'
                f'<span style="color:{meta["color"]}">{s.get("asset","")}</span> '
                f'<span class="{dc}">{s.get("signal","")}</span> '
                f'@ {s.get("entry_price",0):.4f}  str={s.get("strength",0):.2f}</div>'
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

    # ── Equity curve ──────────────────────────────────────────────────────
    if not trades_df.empty and "pnl" in trades_df.columns:
        st.markdown('<div class="section-hdr">📈 Equity Curve</div>', unsafe_allow_html=True)
        cl_df = trades_df[trades_df["status"].isin(["WIN","LOSS"])].copy()
        if not cl_df.empty and "closed_at" in cl_df.columns:
            cl_df["closed_at"] = pd.to_datetime(cl_df["closed_at"], utc=True, errors="coerce")
            cl_df = cl_df.sort_values("closed_at").dropna(subset=["closed_at"])
            cl_df["cum_pnl"] = cl_df["pnl"].cumsum()
            fig = go.Figure()
            for ag in cl_df["agent"].unique():
                adf = cl_df[cl_df["agent"] == ag]
                fig.add_trace(go.Scatter(
                    x=adf["closed_at"], y=adf["cum_pnl"].values,
                    name=ag, mode="lines+markers", line=dict(width=2), marker=dict(size=4),
                ))
            fig.add_hline(y=0, line_dash="dash", line_color="#484f58")
            fig.update_layout(
                height=300, template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0,r=0,t=0,b=0),
                xaxis=dict(gridcolor="#21262d"),
                yaxis=dict(gridcolor="#21262d", title="Cumulative PnL ($)"),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Recent trades ─────────────────────────────────────────────────────
    if not trades_df.empty:
        st.markdown('<div class="section-hdr">📋 Recent Trades</div>', unsafe_allow_html=True)
        cols = [c for c in ["opened_at","agent","asset","direction","entry_price","stop_loss","status","pnl"]
                if c in trades_df.columns]
        disp = trades_df.sort_values("opened_at", ascending=False).head(30)[cols].copy()
        if "pnl" in disp.columns:
            disp["pnl"] = disp["pnl"].apply(
                lambda x: f"+${x:.2f}" if x > 0 else (f"-${abs(x):.2f}" if x < 0 else "$0.00")
            )
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.markdown('<div class="section-hdr">📋 Recent Trades</div>', unsafe_allow_html=True)
        st.info("No trades yet. Bot will start logging trades once it fires signals during trading hours (7am–9pm UTC).")

    # ── Trophy room ───────────────────────────────────────────────────────
    st.markdown('<div class="section-hdr">🏆 Trophy Room</div>', unsafe_allow_html=True)
    all_achs: dict[str, list] = {}
    for ag_name, meta in AGENT_META.items():
        if not trades_df.empty and "agent" in trades_df.columns:
            ag = trades_df[trades_df["agent"] == ag_name]
            cl = ag[ag["status"].isin(["WIN","LOSS"])]
            w  = cl[cl["status"] == "WIN"]
            r  = {
                "total_trades": len(ag),
                "win_rate":     round(len(w)/len(cl)*100,1) if len(cl)>0 else 0,
                "total_pnl":    cl["pnl"].sum() if "pnl" in cl.columns else 0,
            }
            for a in check_ach(r):
                all_achs.setdefault(a, []).append(ag_name)

    st.markdown('<div class="trophy-room">', unsafe_allow_html=True)
    for aname, aicon in ACH.items():
        holders = all_achs.get(aname, [])
        locked  = not holders
        st.markdown(f"""
        <div class="trophy{' trophy-locked' if locked else ''}">
            <div style="font-size:20px;">{aicon}</div>
            <div style="font-size:11px;font-weight:600;color:#e6edf3;margin-top:3px;">{aname}</div>
            <div style="font-size:9px;color:#8b949e;">{", ".join(holders) if not locked else "Locked"}</div>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — POCKET OPTION / SIGNAL ENGINE
# ══════════════════════════════════════════════════════════════════════════════
with tab_po:

    @st.cache_data(ttl=REFRESH_S)
    def load_signals() -> pd.DataFrame:
        rows = []
        if not SIGNALS_LOG.exists():
            return pd.DataFrame()
        for line in SIGNALS_LOG.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        if "session" in df.columns:
            df["session"] = df["session"].str.replace(r"[^\x00-\x7F]+", "", regex=True).str.strip()
        return df

    se_cfg = load_json(SE_CFG_FILE) or {}
    df     = load_signals()

    # ── Header + session status ───────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    now_h   = now_utc.hour
    SESSIONS = {"NY Morning": (13,15), "NY Peak": (15,18), "NY Close": (18,20)}
    active_session = next((n for n,(s,e) in SESSIONS.items() if s<=now_h<e), None)

    session_html = (
        f'<span class="session-badge">🟢 {active_session}</span>'
        if active_session else
        '<span class="session-badge" style="background:#1a1a1a;color:#484f58;border-color:#30363d;">⏸ Dead Zone</span>'
    )

    # Signal engine is always live — show that prominently
    se_proc = (wdog_status or {}).get("processes", {}).get("signal_engine", {})
    se_running = se_proc.get("status") == "running"
    se_badge = (
        '<span style="background:#1a0d2b;color:#bc8cff;border:1px solid #8957e5;'
        'padding:4px 14px;border-radius:10px;font-size:12px;font-weight:700;">⭐ ALWAYS LIVE</span>'
    )

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:4px;">'
        f'<span style="font-size:20px;color:#58a6ff;letter-spacing:3px;font-weight:700;'
        f'font-family:Share Tech Mono,monospace;">// POCKET OPTION — SIGNAL ENGINE //</span>'
        f'{se_badge}&nbsp;{session_html}'
        f'<small style="color:#484f58;">{now_utc.strftime("%H:%M UTC")}</small></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="font-size:11px;color:#484f58;margin-bottom:12px;">'
        'Signal Engine runs independently — the APEX Go Live button has no effect on it.</div>',
        unsafe_allow_html=True,
    )

    # ── Session schedule ──────────────────────────────────────────────────
    s_cols = st.columns(4)
    for col, (name, (sh, eh)) in zip(s_cols[:3], SESSIONS.items()):
        active = name == active_session
        col.markdown(
            f'<div style="background:{"#0d2b1a" if active else "#0d1117"};'
            f'border:1px solid {"#3fb950" if active else "#21262d"};'
            f'border-radius:8px;padding:10px;text-align:center;'
            f'font-family:Share Tech Mono,monospace;">'
            f'<div style="font-size:10px;color:{"#3fb950" if active else "#8b949e"};">{name}</div>'
            f'<div style="font-size:13px;color:#e6edf3;margin-top:2px;">{sh}:00–{eh}:00 UTC</div>'
            f'<div style="font-size:10px;color:#484f58;">{"▶ ACTIVE" if active else "STANDBY"}</div></div>',
            unsafe_allow_html=True,
        )
    s_cols[3].markdown(
        '<div style="background:#1a0d0d;border:1px solid #3a1a1a;'
        'border-radius:8px;padding:10px;text-align:center;font-family:Share Tech Mono,monospace;">'
        '<div style="font-size:10px;color:#484f58;">Dead Zone</div>'
        '<div style="font-size:13px;color:#e6edf3;margin-top:2px;">20:00–13:00 UTC</div>'
        '<div style="font-size:10px;color:#484f58;">NO SIGNALS</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("<hr style='border-color:#21262d;margin:14px 0;'>", unsafe_allow_html=True)

    # ── Asset cards ───────────────────────────────────────────────────────
    st.markdown('<div class="po-hdr">ASSET CONFIGURATION</div>', unsafe_allow_html=True)
    asset_cfg = se_cfg.get("asset_config", {})
    ASSET_META = {
        "XAU/USD": ("🥇", "Gold"),
        "USD/JPY": ("🇯🇵", "Dollar-Yen"),
        "GBP/USD": ("🇬🇧", "Cable"),
        "EUR/USD": ("🇪🇺", "Fiber"),
        "BTC/USD": ("₿",  "Bitcoin"),
    }
    premium_assets = se_cfg.get("premium_assets", [])
    a_cols = st.columns(len(ASSET_META))
    for col, (asset, (flag, name)) in zip(a_cols, ASSET_META.items()):
        cfg_a   = asset_cfg.get(asset, {})
        wr_a    = cfg_a.get("backtest_wr", 0)
        expiry  = cfg_a.get("expiry", "—")
        min_sc  = cfg_a.get("min_score", se_cfg.get("min_score_default", 0.70))
        premium = asset in premium_assets
        wr_col  = "#3fb950" if wr_a >= 55 else ("#d29922" if wr_a >= 45 else "#f85149")
        col.markdown(
            f'<div style="background:#0d1117;border:1px solid {"#d29922" if premium else "#21262d"};'
            f'border-radius:8px;padding:10px;text-align:center;font-family:Share Tech Mono,monospace;">'
            f'{"<div style=\'font-size:9px;color:#d29922;margin-bottom:2px;\'>⭐ PREMIUM</div>" if premium else ""}'
            f'<div style="font-size:20px;">{flag}</div>'
            f'<div style="font-size:12px;font-weight:700;color:#e6edf3;margin-top:3px;">{asset}</div>'
            f'<div style="font-size:9px;color:#8b949e;">{name}</div>'
            f'<div style="font-size:14px;color:{wr_col};font-weight:700;margin-top:5px;">{wr_a:.0f}%</div>'
            f'<div style="font-size:9px;color:#8b949e;">backtest WR</div>'
            f'<div style="font-size:9px;color:#484f58;margin-top:3px;">exp={expiry}m  min={min_sc:.0%}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:#21262d;margin:14px 0;'>", unsafe_allow_html=True)

    if df.empty:
        st.info(
            f"No signals yet.\n\n"
            f"Signal log: `{SIGNALS_LOG}`\n\n"
            f"Run the engine: `cd ~/signal_engine && python3 main.py`"
        )
    else:
        settled  = df[df["outcome"].isin(["WIN","LOSS"])]
        wins_df  = settled[settled["outcome"] == "WIN"]
        loss_df  = settled[settled["outcome"] == "LOSS"]
        total_wr = round(len(wins_df)/len(settled)*100,1) if len(settled)>0 else 0

        m1,m2,m3,m4,m5,m6 = st.columns(6)
        m1.metric("TOTAL",    len(df))
        m2.metric("SETTLED",  len(settled))
        m3.metric("PENDING",  len(df)-len(settled))
        m4.metric("WINS",     len(wins_df))
        m5.metric("LOSSES",   len(loss_df))
        m6.metric("WIN RATE", f"{total_wr}%",
                  delta=f"{total_wr-50:.1f}% vs 50%", delta_color="normal")

        st.markdown("<hr style='border-color:#21262d;margin:14px 0;'>", unsafe_allow_html=True)

        # Equity curve
        st.markdown('<div class="po-hdr">EQUITY CURVE</div>', unsafe_allow_html=True)
        if not settled.empty and "pnl" in settled.columns:
            eq = settled.sort_values("ts").copy()
            eq["cumulative"] = eq["pnl"].cumsum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=eq["ts"], y=eq["cumulative"], mode="lines+markers",
                line=dict(color="#58a6ff", width=2),
                marker=dict(color=eq["outcome"].map({"WIN":"#3fb950","LOSS":"#f85149"}), size=5),
                name="Cumulative PnL",
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#484f58")
            fig.update_layout(
                height=240, template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0,r=0,t=0,b=0),
                xaxis=dict(gridcolor="#21262d"),
                yaxis=dict(gridcolor="#21262d", title="PnL (+1=WIN / -1=LOSS)"),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Per-asset + per-session
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown('<div class="po-hdr">WIN RATE BY ASSET</div>', unsafe_allow_html=True)
            if not settled.empty and "symbol" in settled.columns:
                by_sym = (
                    settled.groupby("symbol")
                    .apply(lambda x: pd.Series({
                        "Signals": len(x),
                        "Wins":    (x["outcome"]=="WIN").sum(),
                        "WR %":    round((x["outcome"]=="WIN").sum()/len(x)*100,1),
                    }), include_groups=False)
                    .reset_index().sort_values("WR %", ascending=False)
                )
                fig2 = go.Figure(go.Bar(
                    x=by_sym["symbol"], y=by_sym["WR %"],
                    marker_color=["#3fb950" if w>=55 else "#d29922" if w>=45 else "#f85149" for w in by_sym["WR %"]],
                    text=by_sym["WR %"].astype(str)+"%", textposition="outside",
                ))
                fig2.add_hline(y=50, line_dash="dash", line_color="#484f58", annotation_text="50% breakeven")
                fig2.update_layout(
                    height=220, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0,r=0,t=0,b=0),
                    yaxis=dict(range=[0,115], gridcolor="#21262d"),
                    xaxis=dict(gridcolor="#21262d"),
                )
                st.plotly_chart(fig2, use_container_width=True)
                by_sym["Status"] = by_sym["WR %"].apply(lambda w: "✅ KEEP" if w>=50 else ("⚠️ WATCH" if w>=40 else "❌ CUT"))
                st.dataframe(by_sym.set_index("symbol"), use_container_width=True)

        with col_r:
            st.markdown('<div class="po-hdr">WIN RATE BY SESSION</div>', unsafe_allow_html=True)
            if "session" in settled.columns and not settled.empty:
                by_sess = (
                    settled.groupby("session")
                    .apply(lambda x: pd.Series({
                        "Signals": len(x),
                        "WR %":    round((x["outcome"]=="WIN").sum()/len(x)*100,1),
                    }), include_groups=False)
                    .reset_index().sort_values("WR %", ascending=False)
                )
                fig3 = px.bar(
                    by_sess, x="session", y="WR %",
                    color="WR %", color_continuous_scale=["#f85149","#d29922","#3fb950"],
                    range_color=[30,70], text="WR %",
                )
                fig3.update_traces(texttemplate="%{text}%", textposition="outside")
                fig3.add_hline(y=50, line_dash="dash", line_color="#484f58")
                fig3.update_layout(
                    height=220, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0,r=0,t=0,b=0),
                    coloraxis_showscale=False,
                    xaxis=dict(gridcolor="#21262d"),
                    yaxis=dict(range=[0,115], gridcolor="#21262d"),
                )
                st.plotly_chart(fig3, use_container_width=True)
                st.dataframe(by_sess.set_index("session"), use_container_width=True)

        # Confidence vs outcome
        if not settled.empty and "confidence" in settled.columns:
            st.markdown('<div class="po-hdr">CONFIDENCE vs OUTCOME</div>', unsafe_allow_html=True)
            ca, cb = st.columns(2)
            with ca:
                s2 = settled.copy()
                s2["conf_bucket"] = pd.cut(s2["confidence"],
                    bins=[0,.6,.7,.8,.9,1.01], labels=["<60%","60-70%","70-80%","80-90%","90%+"])
                by_conf = (
                    s2.groupby("conf_bucket", observed=True)
                    .apply(lambda x: round((x["outcome"]=="WIN").sum()/len(x)*100,1), include_groups=False)
                    .reset_index(name="WR %")
                )
                fig4 = px.bar(by_conf, x="conf_bucket", y="WR %",
                    color="WR %", color_continuous_scale=["#f85149","#d29922","#3fb950"],
                    range_color=[30,80], text="WR %", title="WR% by Confidence")
                fig4.update_traces(texttemplate="%{text}%", textposition="outside")
                fig4.add_hline(y=50, line_dash="dash", line_color="#484f58")
                fig4.update_layout(height=240, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0,r=0,t=30,b=0), coloraxis_showscale=False, yaxis=dict(range=[0,115]))
                st.plotly_chart(fig4, use_container_width=True)

            with cb:
                if "direction" in settled.columns:
                    by_dir = (
                        settled.groupby("direction")
                        .apply(lambda x: pd.Series({"Signals":len(x),"WR %":round((x["outcome"]=="WIN").sum()/len(x)*100,1)}),
                               include_groups=False)
                        .reset_index()
                    )
                    fig5 = px.pie(by_dir, values="Signals", names="direction",
                        color="direction", color_discrete_map={"BUY":"#3fb950","SELL":"#f85149"},
                        title="BUY vs SELL split")
                    fig5.update_layout(height=240, template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=30,b=0))
                    st.plotly_chart(fig5, use_container_width=True)

        # Recent signals table
        st.markdown('<div class="po-hdr">RECENT SIGNALS</div>', unsafe_allow_html=True)
        show_cols = [c for c in ["ts","symbol","direction","session","confidence","adx","rsi","entry","exit_price","outcome","pnl"] if c in df.columns]
        disp = df.sort_values("ts", ascending=False).head(40)[show_cols].copy()
        if "ts" in disp.columns:
            disp["ts"] = disp["ts"].dt.strftime("%m-%d %H:%M")
        if "confidence" in disp.columns:
            disp["confidence"] = disp["confidence"].apply(lambda x: f"{x:.0%}")
        if "pnl" in disp.columns:
            disp["pnl"] = disp["pnl"].apply(lambda x: f"+{x}" if x and x>0 else str(x) if x is not None else "—")

        def colour_outcome(val):
            if val == "WIN":  return "color: #3fb950"
            if val == "LOSS": return "color: #f85149"
            return "color: #d29922"

        st.dataframe(
            disp.style.map(colour_outcome, subset=["outcome"]) if "outcome" in disp.columns else disp,
            use_container_width=True, hide_index=True,
        )

    st.markdown(
        f'<div style="font-size:10px;color:#484f58;font-family:Share Tech Mono,monospace;margin-top:12px;">'
        f'Source: {SIGNALS_LOG}</div>',
        unsafe_allow_html=True,
    )

# ── Auto-refresh ──────────────────────────────────────────────────────────────
st.caption(f"Auto-refreshes every {REFRESH_S}s")
time.sleep(REFRESH_S)
st.rerun()
