import json
import os
from collections import Counter, deque

import pandas as pd
import streamlit as st


EVENT_BUS_PATH = "data/event_bus.jsonl"


def _load_agent_reports(max_lines=5000):
    if not os.path.exists(EVENT_BUS_PATH):
        return []
    try:
        with open(EVENT_BUS_PATH, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=max_lines)
    except Exception:
        return []

    reports = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if not isinstance(rec, dict) or rec.get("event") != "agent_report":
            continue
        payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
        reports.append({
            "ts": rec.get("ts") or payload.get("ts"),
            "agent_id": payload.get("agent_id"),
            "agent_type": payload.get("agent_type"),
            "status": payload.get("status"),
            "summary": payload.get("summary"),
            "run_id": payload.get("run_id"),
            "version": payload.get("version"),
            "duration_ms": payload.get("duration_ms"),
            "source": rec.get("source"),
            "details": payload.get("details"),
            "metrics": payload.get("metrics"),
            "recommendations": payload.get("recommendations"),
            "tags": payload.get("tags"),
        })
    return reports


def _build_label(rec):
    ts = rec.get("ts") or ""
    agent = rec.get("agent_id") or rec.get("agent_type") or "unknown"
    status = rec.get("status") or "idle"
    return f"{ts} | {agent} | {status}"


def render():
    st.subheader("Agent Timeline")

    max_lines = int(st.number_input("Read last N lines from event bus", min_value=200, max_value=20000, value=5000, step=200))
    reports = _load_agent_reports(max_lines=max_lines)

    if not reports:
        st.info("No agent reports found in event bus.")
        return

    agent_ids = sorted({r.get("agent_id") for r in reports if r.get("agent_id")})
    statuses = ["ok", "warn", "fail", "idle"]

    cols = st.columns(2)
    with cols[0]:
        agent_filter = st.multiselect("Agent filter", agent_ids, default=agent_ids)
    with cols[1]:
        status_filter = st.multiselect("Status filter", statuses, default=statuses)

    filtered = []
    for r in reports:
        if agent_filter and r.get("agent_id") not in agent_filter:
            continue
        if status_filter and r.get("status") not in status_filter:
            continue
        filtered.append(r)

    if not filtered:
        st.warning("No records match current filters.")
        return

    status_counts = Counter([r.get("status") for r in filtered])
    st.caption("Status counts: " + ", ".join([f"{k}:{v}" for k, v in status_counts.items()]))

    df = pd.DataFrame([{
        "ts": r.get("ts"),
        "agent_id": r.get("agent_id"),
        "status": r.get("status"),
        "summary": r.get("summary"),
        "run_id": r.get("run_id"),
        "duration_ms": r.get("duration_ms"),
        "source": r.get("source")
    } for r in filtered])

    st.dataframe(df, use_container_width=True)

    options = [_build_label(r) for r in filtered]
    selected = st.selectbox("View details", options, index=0)
    idx = options.index(selected)
    rec = filtered[idx]

    st.markdown("**Summary**")
    st.write(rec.get("summary") or "")

    st.markdown("**Metrics**")
    st.json(rec.get("metrics") or {})

    st.markdown("**Details**")
    st.json(rec.get("details") or {})

    st.markdown("**Recommendations**")
    st.write(rec.get("recommendations") or [])

    st.markdown("**Tags**")
    st.write(rec.get("tags") or [])
