"""
APEX Trading HQ — Unified Dashboard
Two sections:
  Tab 1 — APEX  : crypto perps (Lighter.xyz) — 4 agents, live PnL
  Tab 2 — Pocket Option : Signal Engine forex signals (XAU/USD, USD/JPY, GBP/USD…)

Run:
  uv run streamlit run dashboard/app.py
  (from apex/ root)
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

# ── Shared CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

* { font-family: 'Inter', sans-serif !important; }
.block-container { padding: 16px 24px !important; }

/* Stats bar */
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
.stat-label { font-size:10px; color:#8b949e; margin-top:3px; text-transform:uppercase; letter-spacing:0.5px; }

/* Trading floor grid */
.floor-grid {
    display:grid; grid-template-columns:repeat(auto-fill, minmax(300px,1fr));
    gap:14px; margin:14px 0;
}
.station-card {
    background:#161b22; border:1px solid #30363d; border-radius:12px;
    padding:18px; transition:all .2s; position:relative; overflow:hidden;
}
.station-card:hover { border-color:#58a6ff; transform:translateY(-2px); box-shadow:0 8px 24px rgba(0,0,0,.3); }
.station-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.station-name { font-size:15px; font-weight:700; color:#e6edf3; }
.station-sub  { font-size:11px; color:#8b949e; }
.status-wrap  { display:flex; align-items:center; gap:6px; font-size:12px; }
.status-dot   { width:8px; height:8px; border-radius:50%; display:inline-block; }
.status-active   { background:#3fb950; box-shadow:0 0 8px #3fb950; animation:pulse 1.5s infinite; }
.status-inactive { background:#484f58; }
@keyframes pulse { 0%,100%{opacity:1}50%{opacity:.5} }

.xp-track { width:100%; height:5px; background:#21262d; border-radius:3px; margin:8px 0; overflow:hidden; }
.xp-fill  { height:100%; border-radius:3px; background:linear-gradient(90deg,#58a6ff,#bc8cff); }
.xp-label { display:flex; justify-content:space-between; font-size:10px; color:#8b949e; margin-bottom:6px; }

.card-stats { display:grid; grid-template-columns:1fr 1fr; gap:7px; margin-top:10px; }
.card-stat  { background:#0d1117; padding:9px 7px; border-radius:7px; text-align:center; border:1px solid #21262d; }
.card-stat-val { font-size:15px; font-weight:700; }
.card-stat-lbl { font-size:9px; color:#8b949e; margin-top:2px; text-transform:uppercase; letter-spacing:.3px; }
.pos { color:#3fb950; }
.neg { color:#f85149; }

.ach-row { margin-top:10px; display:flex; flex-wrap:wrap; gap:5px; }
.ach-badge {
    background:linear-gradient(135deg,#1a3a4a,#161b22);
    border:1px solid #30363d; border-radius:8px; padding:3px 9px;
    font-size:10px; color:#e6edf3; display:inline-flex; align-items:center; gap:3px;
}
.ach-badge .ai { font-size:13px; }

.section-hdr {
    font-size:16px; font-weight:700; color:#e6edf3; margin:20px 0 10px;
    display:flex; align-items:center; gap:7px;
}

/* Trophy room */
.trophy-room { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px; margin:12px 0; }
.trophy {
    background:#161b22; border:1px solid #30363d; border-radius:9px;
    padding:10px; text-align:center; transition:all .2s;
}
.trophy:hover { border-color:#d29922; }
.trophy-icon { font-size:20px; }
.trophy-name { font-size:11px; font-weight:600; color:#e6edf3; margin-top:3px; }
.trophy-desc { font-size:9px; color:#8b949e; }
.trophy-locked { opacity:.2; }

/* Positions */
.pos-bar  { display:flex; flex-wrap:wrap; gap:7px; margin:8px 0; }
.pos-badge {
    background:#0d1117; border:1px solid #30363d; border-radius:18px;
    padding:5px 14px; font-size:12px; color:#e6edf3; display:inline-flex; align-items:center; gap:7px;
}

/* Pocket Option — terminal theme */
.po-hdr { color:#58a6ff; font-size:14px; letter-spacing:3px; margin:18px 0 6px; font-family:'Share Tech Mono',monospace; }
.po-card {
    background:#0d1117; border:1px solid #21262d; border-radius:8px;
    padding:12px 16px; margin:6px 0; font-family:'Share Tech Mono',monospace;
}
.po-signal-row { display:flex; align-items:center; gap:12px; flex-wrap:wrap; padding:6px 0; border-bottom:1px solid #21262d; }
.po-signal-row:last-child { border-bottom:none; }
.po-asset    { font-size:13px; font-weight:700; color:#e6edf3; min-width:80px; }
.po-dir-buy  { color:#3fb950; font-weight:700; font-size:12px; }
.po-dir-sell { color:#f85149; font-weight:700; font-size:12px; }
.po-win  { color:#3fb950; }
.po-loss { color:#f85149; }
.po-pend { color:#d29922; }
.session-badge {
    display:inline-block; padding:3px 10px; border-radius:10px; font-size:10px; font-weight:600;
    background:#1a3a4a; color:#58a6ff; border:1px solid #1f4a6a;
}
</style>
""", unsafe_allow_html=True)

# ── Paths ─────────────────────────────────────────────────────────────────────
_APEX_ROOT   = Path(__file__).parent.parent
_SE_ROOT     = Path.home() / "signal_engine"
STATE_FILE   = Path(os.getenv("STATE_FILE",    str(_APEX_ROOT / "logs"       / "state.json")))
SIGNALS_LOG  = Path(os.getenv("SIGNALS_LOG",   str(_SE_ROOT   / "signals_log.jsonl")))
SE_CFG_FILE  = Path(os.getenv("SE_CONFIG",     str(_SE_ROOT   / "engine_config.json")))
PAPER_LOG    = _APEX_ROOT / "logs" / "paper_trades.jsonl"

REFRESH_S = 30


def load_json(p):
    try:
        if Path(p).exists():
            with open(p) as f:
                return json.load(f)
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════
#  TABS
# ═══════════════════════════════════════════════════════════
tab_apex, tab_po = st.tabs(["⚡ APEX — Crypto Perps", "🎯 Pocket Option — Signal Engine"])


# ════════════════════════════════════════════════════════════════════════════════
#  TAB 1 — APEX
# ════════════════════════════════════════════════════════════════════════════════
with tab_apex:

    # ── Load state ──────────────────────────────────────────────────────────
    apex_state = load_json(STATE_FILE)

    if not apex_state:
        st.warning("No APEX state yet. Run `python3 main.py` to generate data.")
    else:
        stats        = apex_state.get("stats", {})
        last_signals = apex_state.get("last_signals", {})
        mode         = apex_state.get("mode", "paper").upper()
        cycle        = apex_state.get("cycle", 0)
        updated      = apex_state.get("updated_at", "")[:19].replace("T", " ")

        # ── Load paper trade log ────────────────────────────────────────
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

        # ── Agent definitions ───────────────────────────────────────────
        AGENT_META = {
            "ATLAS":    {"sprite": "⚓", "color": "#58a6ff",  "desc": "SMA + ADX + Volume"},
            "ORACLE":   {"sprite": "🔮", "color": "#3fb950",  "desc": "MACD + RSI + HTF"},
            "SNIPER":   {"sprite": "🎯", "color": "#d29922",  "desc": "Regime-switching"},
            "SENTINEL": {"sprite": "🛰️", "color": "#bc8cff",  "desc": "EMA + Keltner Squeeze"},
        }

        # ── Gamification helpers ────────────────────────────────────────
        ACH = {
            "First Blood":   "🩸", "Sharp Shooter": "🎯", "Profit Hunter": "💰",
            "Diamond Hands": "💎", "Sniper":        "🔫", "Unstoppable":   "🚀",
            "Risk Master":   "🛡️", "Veteran":       "⭐", "Comeback King": "♻️",
        }

        def check_ach(r):
            u = []
            g = lambda k, d=0: r.get(k, d)
            if g("total_pnl", 0) > 0:          u.append("First Blood")
            if g("win_rate", 0) >= 50:          u.append("Sharp Shooter")
            if g("total_pnl", 0) >= 50:         u.append("Profit Hunter")
            if g("total_trades", 0) >= 100:     u.append("Diamond Hands")
            if g("total_trades", 0) >= 10 and g("win_rate", 0) >= 60: u.append("Sniper")
            if g("total_pnl", 0) >= 100:        u.append("Unstoppable")
            if g("total_trades", 0) > 0:        u.append("Risk Master")
            if g("total_trades", 0) >= 500:     u.append("Veteran")
            return u

        def xp_from(r):
            v  = max(0, int(r.get("total_pnl", 0) * 2))
            v += max(0, int(r.get("win_rate", 0)))
            v += min(r.get("total_trades", 0) * 2, 200)
            return max(v, 0)

        def lvl(x): return x // 100

        # ── Global stats bar ────────────────────────────────────────────
        total_trades = stats.get("total_trades", 0)
        open_pos     = stats.get("open", 0)
        closed       = stats.get("closed", 0)
        win_rate     = stats.get("win_rate", 0)
        total_pnl    = stats.get("total_pnl", 0)

        pnl_cls  = "pos" if total_pnl >= 0 else "neg"
        mode_tag = "🔴 LIVE" if mode == "LIVE" else "📋 PAPER"

        def sbar(icon, val, lbl, cls=""):
            return (f'<div class="stat-item">'
                    f'<div class="stat-value {cls}">{icon} {html_lib.escape(str(val))}</div>'
                    f'<div class="stat-label">{lbl}</div></div>')

        st.markdown(f"""<div class="stats-bar">
            {sbar("⚡", mode_tag, "Mode")}
            {sbar("🔁", cycle, "Cycle")}
            {sbar("🧾", total_trades, "Trades")}
            {sbar("📂", open_pos, "Open")}
            {sbar("✅", closed, "Closed")}
            {sbar("🎯", f"{win_rate}%", "Win Rate", "pos" if win_rate >= 50 else "neg")}
            {sbar("💰", f"${total_pnl:+.2f}", "Net PnL", pnl_cls)}
            <div class="stat-item"><div class="stat-value" style="font-size:12px;color:#484f58;">Updated</div>
            <div class="stat-label">{updated} UTC</div></div>
        </div>""", unsafe_allow_html=True)

        # ── Mission Control agent cards ─────────────────────────────────
        st.markdown('<div class="section-hdr">🛰️ Mission Control</div>', unsafe_allow_html=True)
        st.markdown('<div class="floor-grid">', unsafe_allow_html=True)

        agent_names = list(AGENT_META.keys())
        for agent_name in agent_names:
            meta     = AGENT_META[agent_name]
            sigs     = last_signals.get(agent_name, [])
            is_live  = len(sigs) > 0
            sd       = "status-active" if is_live else "status-inactive"
            sl       = "SIGNAL" if is_live else "WATCHING"

            # Per-agent stats from paper log
            agent_r = {"total_trades": 0, "win_rate": 0, "total_pnl": 0, "wins": 0, "losses": 0}
            if not trades_df.empty and "agent" in trades_df.columns:
                ag = trades_df[trades_df["agent"] == agent_name]
                closed_ag = ag[ag["status"].isin(["WIN", "LOSS"])]
                wins_ag   = closed_ag[closed_ag["status"] == "WIN"]
                agent_r["total_trades"] = len(ag)
                agent_r["wins"]         = len(wins_ag)
                agent_r["losses"]       = len(closed_ag) - len(wins_ag)
                agent_r["win_rate"]     = round(len(wins_ag) / len(closed_ag) * 100, 1) if len(closed_ag) > 0 else 0
                agent_r["total_pnl"]    = round(closed_ag["pnl"].sum(), 2) if "pnl" in closed_ag.columns else 0

            x    = xp_from(agent_r)
            lv   = lvl(x)
            prog = min(x % 100, 100)
            ret  = agent_r["total_pnl"]
            wr_a = agent_r["win_rate"]
            sc   = "pos" if ret >= 0 else "neg"
            achs = check_ach(agent_r)
            ach_html = "".join(
                f'<span class="ach-badge"><span class="ai">{ACH.get(a,"⭐")}</span> {a}</span>'
                for a in achs
            ) or '<span style="color:#484f58;font-size:10px;">No achievements yet</span>'

            # Last signal detail
            sig_rows = ""
            for s in sigs[:3]:
                dir_cls = "pos" if s.get("signal") == "BUY" else "neg"
                sig_rows += (
                    f'<div style="margin-top:6px;font-size:11px;color:#8b949e;">'
                    f'<span style="color:{meta["color"]}">{s.get("asset","")}</span> '
                    f'<span class="{dir_cls}">{s.get("signal","")}</span> '
                    f'@ {s.get("entry_price",0):.4f} '
                    f'str={s.get("strength",0):.2f}</div>'
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
                    <div class="card-stat"><div class="card-stat-val {sc}">${ret:+.2f}</div><div class="card-stat-lbl">PnL</div></div>
                    <div class="card-stat"><div class="card-stat-val">{wr_a}%</div><div class="card-stat-lbl">Win Rate</div></div>
                    <div class="card-stat"><div class="card-stat-val">{agent_r['total_trades']}</div><div class="card-stat-lbl">Trades</div></div>
                    <div class="card-stat"><div class="card-stat-val pos">{agent_r['wins']}</div><div class="card-stat-lbl">Wins</div></div>
                </div>
                {sig_rows}
                <div class="ach-row">{ach_html}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # ── Equity curve ────────────────────────────────────────────────
        if not trades_df.empty and "pnl" in trades_df.columns:
            st.markdown('<div class="section-hdr">📈 Equity Curve</div>', unsafe_allow_html=True)
            closed_df = trades_df[trades_df["status"].isin(["WIN", "LOSS"])].copy()
            if not closed_df.empty and "closed_at" in closed_df.columns:
                closed_df["closed_at"] = pd.to_datetime(closed_df["closed_at"], utc=True, errors="coerce")
                closed_df = closed_df.sort_values("closed_at").dropna(subset=["closed_at"])
                closed_df["cumulative_pnl"] = closed_df["pnl"].cumsum()

                fig = go.Figure()
                for ag in closed_df["agent"].unique():
                    ag_df = closed_df[closed_df["agent"] == ag]
                    fig.add_trace(go.Scatter(
                        x=ag_df["closed_at"], y=ag_df["cumulative_pnl"].values,
                        name=ag, mode="lines+markers", line=dict(width=2),
                        marker=dict(size=4),
                    ))
                fig.add_hline(y=0, line_dash="dash", line_color="#484f58")
                fig.update_layout(
                    height=320, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=0, b=0),
                    xaxis=dict(gridcolor="#21262d"),
                    yaxis=dict(gridcolor="#21262d", title="Cumulative PnL ($)"),
                    hovermode="x unified",
                )
                st.plotly_chart(fig, use_container_width=True)

        # ── Recent trades table ──────────────────────────────────────────
        if not trades_df.empty:
            st.markdown('<div class="section-hdr">📋 Recent Trades</div>', unsafe_allow_html=True)
            show_cols = [c for c in ["opened_at", "agent", "asset", "direction",
                                     "entry_price", "stop_loss", "status", "pnl"]
                         if c in trades_df.columns]
            disp = trades_df.sort_values("opened_at", ascending=False).head(30)[show_cols]
            if "pnl" in disp.columns:
                disp["pnl"] = disp["pnl"].apply(
                    lambda x: f"+${x:.2f}" if x > 0 else f"-${abs(x):.2f}" if x < 0 else "$0.00"
                )
            st.dataframe(disp, use_container_width=True, hide_index=True)

        # ── Trophy Room ─────────────────────────────────────────────────
        st.markdown('<div class="section-hdr">🏆 Trophy Room</div>', unsafe_allow_html=True)
        # Gather all achievements across agents
        all_achs: dict[str, list[str]] = {}
        for ag_name in agent_names:
            if not trades_df.empty and "agent" in trades_df.columns:
                ag = trades_df[trades_df["agent"] == ag_name]
                cl = ag[ag["status"].isin(["WIN", "LOSS"])]
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
            locked  = len(holders) == 0
            st.markdown(f"""
            <div class="trophy{' trophy-locked' if locked else ''}">
                <div class="trophy-icon">{aicon}</div>
                <div class="trophy-name">{aname}</div>
                <div class="trophy-desc">{", ".join(holders) if not locked else "Locked"}</div>
            </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
#  TAB 2 — POCKET OPTION / SIGNAL ENGINE
# ════════════════════════════════════════════════════════════════════════════════
with tab_po:

    # ── Load signal log ──────────────────────────────────────────────────
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

    # ── Header ──────────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    now_h   = now_utc.hour
    utc_str = now_utc.strftime("%H:%M UTC")

    # Session detection
    SESSIONS = {
        "NY Morning": (13, 15),
        "NY Peak":    (15, 18),
        "NY Close":   (18, 20),
    }
    active_session = next(
        (name for name, (s, e) in SESSIONS.items() if s <= now_h < e),
        None
    )
    dead_zone = not active_session and (now_h >= 20 or now_h < 13)

    session_html = (
        f'<span class="session-badge">🟢 {active_session}</span>'
        if active_session else
        '<span class="session-badge" style="background:#1a1a1a;color:#484f58;border-color:#30363d;">⏸ Dead Zone</span>'
    )

    st.markdown(
        f'<div style="font-family:Share Tech Mono,monospace;">'
        f'<span style="font-size:20px;color:#58a6ff;letter-spacing:3px;font-weight:700;">'
        f'// POCKET OPTION — SIGNAL ENGINE //</span>'
        f'&nbsp;&nbsp;{session_html}'
        f'&nbsp;&nbsp;<small style="color:#484f58;">{utc_str}</small></div>',
        unsafe_allow_html=True,
    )

    # Session schedule
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    for col, (name, (sh, eh)) in zip([col_s1, col_s2, col_s3], SESSIONS.items()):
        is_now = name == active_session
        col.markdown(
            f'<div style="background:{"#0d2b1a" if is_now else "#0d1117"}; '
            f'border:1px solid {"#3fb950" if is_now else "#21262d"}; '
            f'border-radius:8px; padding:10px; text-align:center; '
            f'font-family:Share Tech Mono,monospace;">'
            f'<div style="font-size:11px; color:{"#3fb950" if is_now else "#8b949e"};">{name}</div>'
            f'<div style="font-size:13px; color:#e6edf3; margin-top:2px;">{sh}:00–{eh}:00 UTC</div>'
            f'<div style="font-size:10px; color:#484f58; margin-top:1px;">'
            f'{"▶ ACTIVE" if is_now else "STANDBY"}</div></div>',
            unsafe_allow_html=True,
        )
    col_s4.markdown(
        f'<div style="background:#1a0d0d; border:1px solid #3a1a1a; '
        f'border-radius:8px; padding:10px; text-align:center; font-family:Share Tech Mono,monospace;">'
        f'<div style="font-size:11px; color:#484f58;">Dead Zone</div>'
        f'<div style="font-size:13px; color:#e6edf3; margin-top:2px;">20:00–13:00 UTC</div>'
        f'<div style="font-size:10px; color:#484f58; margin-top:1px;">NO SIGNALS</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("<hr style='border-color:#21262d;margin:14px 0;'>", unsafe_allow_html=True)

    # ── Asset config cards ───────────────────────────────────────────────
    st.markdown('<div class="po-hdr">ASSET CONFIGURATION</div>', unsafe_allow_html=True)
    asset_cfg   = se_cfg.get("asset_config", {})
    default_min = se_cfg.get("min_score_default", 0.70)

    ASSET_META = {
        "XAU/USD": {"flag": "🥇", "name": "Gold"},
        "USD/JPY": {"flag": "🇯🇵", "name": "Dollar-Yen"},
        "GBP/USD": {"flag": "🇬🇧", "name": "Cable"},
        "EUR/USD": {"flag": "🇪🇺", "name": "Fiber"},
        "BTC/USD": {"flag": "₿",  "name": "Bitcoin"},
    }

    all_assets = list(ASSET_META.keys())
    a_cols     = st.columns(len(all_assets))
    for col, asset in zip(a_cols, all_assets):
        meta     = ASSET_META[asset]
        cfg_a    = asset_cfg.get(asset, {})
        wr_a     = cfg_a.get("backtest_wr", 0)
        expiry   = cfg_a.get("expiry", "—")
        min_sc   = cfg_a.get("min_score", default_min)
        premium  = asset in se_cfg.get("premium_assets", [])
        wr_col   = "#3fb950" if wr_a >= 55 else "#d29922" if wr_a >= 45 else "#f85149"
        col.markdown(
            f'<div style="background:#0d1117; border:1px solid {"#d29922" if premium else "#21262d"}; '
            f'border-radius:8px; padding:10px; text-align:center; font-family:Share Tech Mono,monospace;">'
            f'{"<div style=\'font-size:9px;color:#d29922;margin-bottom:2px;\'>⭐ PREMIUM</div>" if premium else ""}'
            f'<div style="font-size:20px;">{meta["flag"]}</div>'
            f'<div style="font-size:12px;font-weight:700;color:#e6edf3;margin-top:3px;">{asset}</div>'
            f'<div style="font-size:9px;color:#8b949e;">{meta["name"]}</div>'
            f'<div style="font-size:14px;color:{wr_col};font-weight:700;margin-top:5px;">{wr_a:.0f}%</div>'
            f'<div style="font-size:9px;color:#8b949e;">backtest WR</div>'
            f'<div style="font-size:9px;color:#484f58;margin-top:3px;">'
            f'exp={expiry}m  min={min_sc:.0%}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:#21262d;margin:14px 0;'>", unsafe_allow_html=True)

    if df.empty:
        st.info(
            f"No signals yet. Signal log: `{SIGNALS_LOG}`\n\n"
            f"Run the signal engine: `cd ~/signal_engine && python3 main.py`"
        )
    else:
        settled  = df[df["outcome"].isin(["WIN", "LOSS"])]
        wins_df  = settled[settled["outcome"] == "WIN"]
        loss_df  = settled[settled["outcome"] == "LOSS"]
        pending  = df[df["outcome"].notna() & ~df["outcome"].isin(["WIN","LOSS"])] if "outcome" in df.columns else pd.DataFrame()
        total_wr = round(len(wins_df) / len(settled) * 100, 1) if len(settled) > 0 else 0

        # ── Top metrics ─────────────────────────────────────────────────
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("TOTAL",    len(df))
        m2.metric("SETTLED",  len(settled))
        m3.metric("PENDING",  len(df) - len(settled))
        m4.metric("WINS",     len(wins_df))
        m5.metric("LOSSES",   len(loss_df))
        m6.metric("WIN RATE", f"{total_wr}%",
                  delta=f"{total_wr-50:.1f}% vs 50%",
                  delta_color="normal")

        st.markdown("<hr style='border-color:#21262d;margin:14px 0;'>", unsafe_allow_html=True)

        # ── Equity curve ────────────────────────────────────────────────
        st.markdown('<div class="po-hdr">EQUITY CURVE</div>', unsafe_allow_html=True)
        if not settled.empty and "pnl" in settled.columns:
            eq = settled.sort_values("ts").copy()
            eq["cumulative"] = eq["pnl"].cumsum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=eq["ts"], y=eq["cumulative"],
                mode="lines+markers",
                line=dict(color="#58a6ff", width=2),
                marker=dict(
                    color=eq["outcome"].map({"WIN": "#3fb950", "LOSS": "#f85149"}),
                    size=5,
                ),
                name="Cumulative PnL",
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#484f58")
            fig.update_layout(
                height=240, template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(gridcolor="#21262d"),
                yaxis=dict(gridcolor="#21262d", title="PnL (+1=WIN / -1=LOSS)"),
            )
            st.plotly_chart(fig, use_container_width=True)

        # ── Per-asset + per-session breakdown ───────────────────────────
        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown('<div class="po-hdr">WIN RATE BY ASSET</div>', unsafe_allow_html=True)
            if not settled.empty and "symbol" in settled.columns:
                by_sym = (
                    settled.groupby("symbol")
                    .apply(lambda x: pd.Series({
                        "Signals": len(x),
                        "Wins":    (x["outcome"] == "WIN").sum(),
                        "WR %":    round((x["outcome"] == "WIN").sum() / len(x) * 100, 1),
                    }), include_groups=False)
                    .reset_index()
                    .sort_values("WR %", ascending=False)
                )
                fig2 = go.Figure(go.Bar(
                    x=by_sym["symbol"], y=by_sym["WR %"],
                    marker_color=[
                        "#3fb950" if w >= 55 else "#d29922" if w >= 45 else "#f85149"
                        for w in by_sym["WR %"]
                    ],
                    text=by_sym["WR %"].astype(str) + "%",
                    textposition="outside",
                ))
                fig2.add_hline(y=50, line_dash="dash", line_color="#484f58",
                               annotation_text="50% breakeven")
                fig2.update_layout(
                    height=220, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=0, b=0),
                    yaxis=dict(range=[0, 115], gridcolor="#21262d"),
                    xaxis=dict(gridcolor="#21262d"),
                )
                st.plotly_chart(fig2, use_container_width=True)
                by_sym["Status"] = by_sym["WR %"].apply(
                    lambda w: "✅ KEEP" if w >= 50 else ("⚠️ WATCH" if w >= 40 else "❌ CUT")
                )
                st.dataframe(by_sym.set_index("symbol"), use_container_width=True)

        with col_r:
            st.markdown('<div class="po-hdr">WIN RATE BY SESSION</div>', unsafe_allow_html=True)
            if "session" in settled.columns and not settled.empty:
                by_sess = (
                    settled.groupby("session")
                    .apply(lambda x: pd.Series({
                        "Signals": len(x),
                        "WR %":    round((x["outcome"] == "WIN").sum() / len(x) * 100, 1),
                    }), include_groups=False)
                    .reset_index()
                    .sort_values("WR %", ascending=False)
                )
                fig3 = px.bar(
                    by_sess, x="session", y="WR %",
                    color="WR %",
                    color_continuous_scale=["#f85149", "#d29922", "#3fb950"],
                    range_color=[30, 70], text="WR %",
                )
                fig3.update_traces(texttemplate="%{text}%", textposition="outside")
                fig3.add_hline(y=50, line_dash="dash", line_color="#484f58")
                fig3.update_layout(
                    height=220, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=0, b=0),
                    coloraxis_showscale=False,
                    xaxis=dict(gridcolor="#21262d"),
                    yaxis=dict(range=[0, 115], gridcolor="#21262d"),
                )
                st.plotly_chart(fig3, use_container_width=True)
                st.dataframe(by_sess.set_index("session"), use_container_width=True)

        # ── Confidence vs outcome ───────────────────────────────────────
        if not settled.empty and "confidence" in settled.columns:
            st.markdown('<div class="po-hdr">CONFIDENCE vs OUTCOME</div>', unsafe_allow_html=True)
            c_a, c_b = st.columns(2)

            with c_a:
                s2 = settled.copy()
                s2["conf_bucket"] = pd.cut(
                    s2["confidence"],
                    bins=[0, 0.6, 0.7, 0.8, 0.9, 1.01],
                    labels=["<60%", "60-70%", "70-80%", "80-90%", "90%+"],
                )
                by_conf = (
                    s2.groupby("conf_bucket", observed=True)
                    .apply(lambda x: round((x["outcome"] == "WIN").sum() / len(x) * 100, 1),
                           include_groups=False)
                    .reset_index(name="WR %")
                )
                fig4 = px.bar(
                    by_conf, x="conf_bucket", y="WR %",
                    color="WR %",
                    color_continuous_scale=["#f85149", "#d29922", "#3fb950"],
                    range_color=[30, 80], text="WR %",
                    title="WR% by Confidence",
                )
                fig4.update_traces(texttemplate="%{text}%", textposition="outside")
                fig4.add_hline(y=50, line_dash="dash", line_color="#484f58")
                fig4.update_layout(
                    height=240, template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=30, b=0),
                    coloraxis_showscale=False,
                    yaxis=dict(range=[0, 115]),
                )
                st.plotly_chart(fig4, use_container_width=True)

            with c_b:
                if "direction" in settled.columns:
                    by_dir = (
                        settled.groupby("direction")
                        .apply(lambda x: pd.Series({
                            "Signals": len(x),
                            "WR %":    round((x["outcome"] == "WIN").sum() / len(x) * 100, 1),
                        }), include_groups=False)
                        .reset_index()
                    )
                    fig5 = px.pie(
                        by_dir, values="Signals", names="direction",
                        color="direction",
                        color_discrete_map={"BUY": "#3fb950", "SELL": "#f85149"},
                        title="BUY vs SELL split",
                    )
                    fig5.update_layout(
                        height=240, template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0, r=0, t=30, b=0),
                    )
                    st.plotly_chart(fig5, use_container_width=True)

        # ── Recent signals table ────────────────────────────────────────
        st.markdown('<div class="po-hdr">RECENT SIGNALS</div>', unsafe_allow_html=True)
        show_cols = [c for c in ["ts", "symbol", "direction", "session",
                                  "confidence", "adx", "rsi", "entry",
                                  "exit_price", "outcome", "pnl"]
                     if c in df.columns]
        disp = df.sort_values("ts", ascending=False).head(40)[show_cols].copy()
        if "ts" in disp.columns:
            disp["ts"] = disp["ts"].dt.strftime("%m-%d %H:%M")
        if "confidence" in disp.columns:
            disp["confidence"] = disp["confidence"].apply(lambda x: f"{x:.0%}")
        if "pnl" in disp.columns:
            disp["pnl"] = disp["pnl"].apply(
                lambda x: f"+{x}" if x and x > 0 else str(x) if x is not None else "—"
            )

        def colour_outcome(val):
            if val == "WIN":   return "color: #3fb950"
            if val == "LOSS":  return "color: #f85149"
            return "color: #d29922"

        st.dataframe(
            disp.style.map(colour_outcome, subset=["outcome"]) if "outcome" in disp.columns else disp,
            use_container_width=True,
            hide_index=True,
        )

    st.markdown(
        f'<div style="font-size:10px;color:#484f58;font-family:Share Tech Mono,monospace;margin-top:12px;">'
        f'Source: {SIGNALS_LOG} &nbsp;|&nbsp; Engine config: {SE_CFG_FILE}'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Auto-refresh ───────────────────────────────────────────────────────────────
st.caption(f"Auto-refreshes every {REFRESH_S}s")
time.sleep(REFRESH_S)
st.rerun()
