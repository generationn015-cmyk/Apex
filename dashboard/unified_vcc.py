import streamlit as st
import pandas as pd
import json
from pathlib import Path
import time

# CLAUDE-CODE PIXEL VCC DASHBOARD
st.set_page_config(page_title="CLAUDE-CODE VCC", layout="wide")

# CSS for VT323/Pixel Art Aesthetic
st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=VT323&display=swap" rel="stylesheet">
    <style>
    body {
        background-color: #0e1117;
        color: #00ff00;
        font-family: 'VT323', monospace;
    }
    .stApp {
        background-color: #0e1117;
    }
    .pixel-card {
        border: 2px solid #00ff00;
        padding: 20px;
        border-radius: 5px;
        background: #1a1c23;
        box-shadow: 5px 5px 0px #000;
        margin-bottom: 20px;
    }
    .status-ok { color: #00ff00; text-shadow: 0 0 10px #00ff00; }
    .status-hunting { color: #ff00ff; animation: pulse 1.5s infinite; }
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.3; }
        100% { opacity: 1; }
    }
    h1, h2, h3, p, span {
        font-family: 'VT323', monospace !important;
        color: #00ff00 !important;
    }
    </style>
""", unsafe_allow_request_safe=True)

st.title("█ CLAUDE-CODE // VIRTUAL CONTROL CENTER █")

col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="pixel-card"><h2>--- BOT 1: ELITE SQUAD ---</h2>', unsafe_allow_html=True)
    st.markdown('<p class="status-hunting">>> STATUS: SCANNING_INTRA_DAY_ALPHA...</p>', unsafe_allow_html=True)
    st.markdown('<p>MARKETS: NVDA, BTC, SOL</p>', unsafe_allow_html=True)
    st.markdown('<p>CAPITAL: $100.00</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="pixel-card"><h2>--- BOT 2: SPECIAL OPS ---</h2>', unsafe_allow_html=True)
    st.markdown('<p class="status-ok">>> STATUS: 3_ACTIVE_SNIPES_DEPLOYED</p>', unsafe_allow_html=True)
    st.markdown('<p>MARKETS: POLYMARKET_NEWS_CRYPTO</p>', unsafe_allow_html=True)
    st.markdown('<p>CAPITAL: $100.00 ($30.00 Working)</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="pixel-card"><h3>EQUITY_TRAJECTORY_STREAM</h3>', unsafe_allow_html=True)
# Mock Chart using pixel style
chart_data = pd.DataFrame([200, 201, 203, 208], columns=["USD"])
st.line_chart(chart_data)
st.markdown('</div>', unsafe_allow_html=True)

st.write("SCR_001 // MISSION_BRIEFING_IN_T-MINUS_8_HOURS")
