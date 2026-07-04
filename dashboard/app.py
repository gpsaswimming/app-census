"""Read-only analytics dashboard (Streamlit) — the read side of app-census.

Phase 0: a runnable shell. Phase 4 ports the gpsa-census analytics onto the new
DOB-free Postgres schema and retires the old Python SDIF parser + import path.
"""

from __future__ import annotations

import os

import streamlit as st

st.set_page_config(page_title="GPSA Census", page_icon="🏊", layout="wide")

st.title("GPSA Census")
st.caption("Read-only analytics over the app-census Postgres store.")

st.info(
    "Phase 0 scaffold. Analytics arrive in Phase 4, reading from the DOB-free "
    "schema built in Phase 2 and populated by the ingest service (Phase 3)."
)

db_url = os.getenv("DATABASE_URL", "(unset)")
st.write("**DATABASE_URL:**", db_url.split("@")[-1] if "@" in db_url else db_url)
