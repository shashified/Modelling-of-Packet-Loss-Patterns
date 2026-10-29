"""Packet-Loss Lab: the final product of the case study.

    streamlit run lab.py

Page 1, Real Network Lab (Phase 2): record real packet captures and see every statistic as charts.
Page 2, Simulation Lab (Phase 1): the simulated Good/Bad networks from the study.
"""
import streamlit as st

st.set_page_config(page_title="Packet-Loss Lab", page_icon="📡", layout="wide")

nav = st.navigation([
    st.Page("realworld/dashboard.py", title="Real Network Lab (Phase 2)", icon="📶", default=True),
    st.Page("app.py", title="Simulation Lab (Phase 1)", icon="🧪"),
])
nav.run()
