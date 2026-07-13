# -*- coding: utf-8 -*-
"""
📞 Call Ops Toolkit — Streamlit multipage app
  1. Queue Report Builder  (upload CSV/Excel → bifurcation → Excel download / push to Google Sheet)
  2. Bulk Call Transcriber (Google Sheet → Deepgram → transcript)

Both tools appear in the sidebar automatically via st.navigation.
"""

import streamlit as st

st.set_page_config(
    page_title="Call Ops Toolkit",
    page_icon="📞",
    layout="wide",
)

queue_page = st.Page(
    "views/queue_report.py",
    title="Queue Report Builder",
    icon="📊",
    default=True,
)

transcriber_page = st.Page(
    "views/transcriber.py",
    title="Bulk Call Transcriber",
    icon="🎙️",
)

nav = st.navigation(
    {"Tools": [queue_page, transcriber_page]},
    position="sidebar",
)

with st.sidebar:
    st.divider()
    st.caption("📞 Call Ops Toolkit • Queue bifurcation + Deepgram transcription")

nav.run()
