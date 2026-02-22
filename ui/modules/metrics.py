import datetime
import json
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from core.metrics import compute_kpis, compute_loop_health
from core.skill_registry import SkillRegistry
from core.event_index import update_index, query_context, query_events

TRAINING_REPORT_PATH = "data/strategy_training_report.jsonl"
TRAINING_CONFIG_PATH = "config/strategy_training.json"


def _format_pct(val):
    try:
        return f"{float(val)*100:.2f}%"
    except Exception:
        return "NA"


def _load_latest_loop_report(path="data/loop_health_report.jsonl"):
    if not os.path.exists(path):
        return None
    last_line = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line
    except Exception:
        return None
    if not last_line:
        return None
    try:
        rec = json.loads(last_line)
    except Exception:
        return None
    return rec if isinstance(rec, dict) else None


def _load_loop_health_history(path="data/loop_health_report.jsonl", limit=120):
    if not os.path.exists(path):
        return pd.DataFrame()
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                rows.append({
                    "ts": rec.get("ts"),
                    "health_score": rec.get("health_score"),
                    "outcome_attr_rate": rec.get("outcome_strategy_attrib_rate"),
                    "exec_rate": rec.get("execution_rate"),
                    "outcome_rate": rec.get("outcome_rate")
                })
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        try:
            df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        except Exception:
            pass
    return df


def _load_training_config(path=TRAINING_CONFIG_PATH):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_latest_training_report(path=TRAINING_REPORT_PATH):
    if not os.path.exists(path):
        return None
    last_line = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line
    except Exception:
        return None
    if not last_line:
        return None
    try:
        rec = json.loads(last_line)
    except Exception:
        return None
    return rec if isinstance(rec, dict) else None


def _summarize_training_report(rec):
    if not isinstance(rec, dict):
        return None
    strategies = rec.get("strategies", {}) if isinstance(rec.get("strategies", {}), dict) else {}
    total_samples = 0
    sum_score = 0.0
    sum_ret = 0.0
    sum_dd = 0.0
    for _, stats in strategies.items():
        if not isinstance(stats, dict):
            continue
        samples = int(stats.get("samples", 0) or 0)
        if samples <= 0:
            continue
        total_samples += samples
        sum_score += float(stats.get("avg_score", 0) or 0) * samples
        sum_ret += float(stats.get("avg_return", 0) or 0) * samples
        sum_dd += float(stats.get("avg_drawdown", 0) or 0) * samples
    avg_score = (sum_score / total_samples) if total_samples else 0.0
    avg_ret = (sum_ret / total_samples) if total_samples else 0.0
    avg_dd = (sum_dd / total_samples) if total_samples else 0.0
    return {
        "ts": rec.get("ts"),
        "mode": rec.get("mode"),
        "pool": rec.get("pool"),
        "days": rec.get("days"),
        "strategies": len(strategies),
        "samples": total_samples,
        "avg_score": avg_score,
        "avg_return": avg_ret,
        "avg_drawdown": avg_dd,
        "codes_total": rec.get("codes_total"),
        "codes_with_data": rec.get("codes_with_data")
    }


def _load_training_history(path=TRAINING_REPORT_PATH, limit=60):
    if not os.path.exists(path):
        return pd.DataFrame()
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                summary = _summarize_training_report(rec)
                if summary:
                    rows.append(summary)
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        try:
            df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        except Exception:
            pass
    return df


def _load_training_daily(path=TRAINING_REPORT_PATH, limit=120):
    df = _load_training_history(path=path, limit=None)
    if df is None or df.empty:
        return pd.DataFrame()
    if "ts" not in df.columns:
        return pd.DataFrame()
    df = df.sort_values("ts")
    df["date"] = df["ts"].dt.date
    daily = df.groupby("date", as_index=False).tail(1)
    if limit and len(daily) > limit:
        daily = daily.tail(limit)
    return daily


def render():
    st.header("\u7cfb\u7edfKPI")
    kpis = compute_kpis()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("\u51b3\u7b56\u6b21\u6570", kpis.get("decisions", 0))
    c2.metric("\u7ed3\u679c\u6b21\u6570", kpis.get("outcomes", 0))
    c3.metric("\u80dc\u7387", _format_pct(kpis.get("win_rate", 0)))
    c4.metric("\u5e73\u5747\u6536\u76ca", _format_pct(kpis.get("avg_pnl_pct", 0)))

    c5, c6, c7 = st.columns(3)
    c5.metric("\u7b56\u7565\u8986\u76d6\u7387", _format_pct(kpis.get("override_rate", 0)))
    c6.metric("\u6700\u5927\u56de\u64a4", _format_pct(kpis.get("max_drawdown", 0)))
    c7.metric("\u6700\u65b0\u6743\u76ca", f"{kpis.get('last_equity', 0):.0f}")

    st.caption(
        f"\u8986\u76d6\u6b21\u6570: {kpis.get('override_count', 0)} | "
        f"\u6700\u8fd1\u8fde\u80dc/\u8fde\u8d25: {kpis.get('streak', {}).get('type')} {kpis.get('streak', {}).get('count')}"
    )

    if "loop_health" not in st.session_state:
        report = _load_latest_loop_report()
        if report:
            st.session_state["loop_health"] = report
            st.session_state["loop_health_ts"] = report.get("ts", "")
            st.session_state["loop_health_source"] = "report"

    st.divider()
    st.subheader("\u95ed\u73af\u5065\u5eb7\u68c0\u67e5")
    run_check = st.button("\u8fd0\u884c\u95ed\u73af\u68c0\u67e5")
    if run_check:
        try:
            st.session_state["loop_health"] = compute_loop_health()
            st.session_state["loop_health_ts"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state["loop_health_source"] = "manual"
        except Exception:
            st.session_state["loop_health"] = None

    health = st.session_state.get("loop_health")
    if health:
        ts = st.session_state.get("loop_health_ts", "")
        if ts:
            st.caption(f"\u6700\u540e\u8fd0\u884c\u65f6\u95f4: {ts}")
        src = st.session_state.get("loop_health_source")
        if src == "report":
            st.caption("\u6570\u636e\u6765\u6e90: \u6bcf\u65e5\u95ed\u73af\u62a5\u544a")
        elif src == "manual":
            st.caption("\u6570\u636e\u6765\u6e90: \u624b\u52a8\u89e6\u53d1")

        h1, h2, h3, h4 = st.columns(4)
        h1.metric("\u51b3\u7b56", health.get("decisions", 0))
        h2.metric("\u6267\u884c", health.get("executions", 0))
        h3.metric("\u7ed3\u679c", health.get("outcomes", 0))
        h4.metric("\u7ed3\u679c\u5f52\u56e0\u7387", _format_pct(health.get("outcome_strategy_attrib_rate", 0)))

        a1, a2, a3, a4 = st.columns(4)
        a1.metric("\u51b3\u7b56\u65e0\u6267\u884c", health.get("decisions_no_execution", 0))
        a2.metric("\u51b3\u7b56\u65e0\u7ed3\u679c", health.get("decisions_no_outcome", 0))
        a3.metric("\u6267\u884c\u7f3aID", health.get("execution_missing_id", 0))
        a4.metric("\u7ed3\u679c\u7f3aID", health.get("outcome_missing_id", 0))

        b1, b2, b3, b4 = st.columns(4)
        b1.metric("\u7ed3\u679c\u5b64\u513f", health.get("outcome_orphan", 0))
        b2.metric("\u5356\u51fa\u5f52\u56e0\u7387", _format_pct(health.get("sell_strategy_attrib_rate", 0)))
        b3.metric("\u6267\u884c\u7387", _format_pct(health.get("execution_rate", 0)))
        b4.metric("\u7ed3\u679c\u7387", _format_pct(health.get("outcome_rate", 0)))

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Trade decision rate", _format_pct(health.get("trade_decision_rate", 0)))
        d2.metric("Trades missing decision", health.get("trade_missing_decision_id", 0))
        d3.metric("Decision events missing", health.get("decision_event_missing", 0))
        trade_total = health.get("trade_total")
        if trade_total is None:
            trade_total = (health.get("trade_buys", 0) or 0) + (health.get("trade_sells", 0) or 0)
        d4.metric("Trades", trade_total)
        if (health.get("decision_event_missing") or 0) > 0:
            st.warning("\u68c0\u6d4b\u5230\u6709\u4ea4\u6613\u4f46\u65e0\u51b3\u7b56\u4e8b\u4ef6\uff0c\u5efa\u8bae\u56de\u586b\u6216\u786e\u8ba4\u51b3\u7b56\u94fe\u8def\u3002")

        c1, c2, c3 = st.columns(3)
        c1.metric("\u5065\u5eb7\u8bc4\u5206", f"{float(health.get('health_score', 0) or 0):.1f}")
        c2.metric("\u5065\u5eb7\u72b6\u6001", health.get("health_status", "NA"))
        skill_summary = health.get("skill_summary", {}) if isinstance(health.get("skill_summary", {}), dict) else {}
        c3.metric("\u6709\u5956\u52b1\u7b56\u7565", skill_summary.get("rewarded", 0))

        st.caption(f"skills.db \u7b56\u7565\u603b\u6570: {skill_summary.get('strategies', 0)}")
        st.caption(f"\u6743\u91cd\u504f\u7f6e\u66f4\u65b0\u65f6\u95f4: {health.get('bias_updated_at') or 'n/a'}")
        st.caption(f"\u9608\u503c\u8986\u76d6\u66f4\u65b0\u65f6\u95f4: {health.get('threshold_overrides_updated_at') or 'n/a'}")
    else:
        st.info("\u6682\u65e0\u65e5\u62a5\uff0c\u70b9\u51fb\u4e0a\u65b9\u6309\u94ae\u8fd0\u884c\u95ed\u73af\u68c0\u67e5")

    history = _load_loop_health_history()
    st.subheader("\u95ed\u73af\u8d8b\u52bf")
    if history is not None and not history.empty:
        df_hist = history.copy()
        if "ts" in df_hist.columns:
            df_hist = df_hist.set_index("ts")
        cols = [c for c in ["health_score", "outcome_attr_rate", "exec_rate", "outcome_rate"] if c in df_hist.columns]
        if cols:
            st.line_chart(df_hist[cols])
        else:
            st.info("\u65e0\u53ef\u5c55\u793a\u7684\u8d8b\u52bf\u6570\u636e")
    else:
        st.info("\u6682\u65e0\u95ed\u73af\u62a5\u544a\u8d8b\u52bf\u6570\u636e")

    st.subheader("\u95ed\u73af\u65e5\u62a5\u5386\u53f2")
    if history is not None and not history.empty:
        show_df = history.tail(50).copy()
        st.dataframe(show_df, use_container_width=True)
        try:
            st.download_button("\u5bfc\u51fa\u95ed\u73af\u65e5\u62a5CSV", history.to_csv(index=False), file_name="loop_health_report.csv", mime="text/csv")
        except Exception:
            pass
    else:
        st.info("\u6682\u65e0\u95ed\u73af\u65e5\u62a5\u5386\u53f2")

    st.divider()
    st.subheader("\u7b56\u7565\u8bad\u7ec3\u5668")

    if "training_report" not in st.session_state:
        latest = _load_latest_training_report()
        if latest:
            st.session_state["training_report"] = latest
            st.session_state["training_report_ts"] = latest.get("ts", "")
            st.session_state["training_report_source"] = "report"

    cfg = _load_training_config()
    with st.expander("\u8bad\u7ec3\u914d\u7f6e", expanded=False):
        if cfg:
            st.json(cfg)
        else:
            st.caption("\u672a\u627e\u5230 config/strategy_training.json\uff0c\u5c06\u4f7f\u7528\u9ed8\u8ba4\u914d\u7f6e\u3002")

    run_train = st.button("\u8fd0\u884c\u7b56\u7565\u8bad\u7ec3 (\u53ef\u80fd\u8017\u65f6)", type="primary")
    if run_train:
        progress = st.progress(0, text="\u51c6\u5907\u8bad\u7ec3...")
        def _progress_cb(done, total, message=None):
            try:
                total = int(total or 0)
            except Exception:
                total = 0
            try:
                done = int(done or 0)
            except Exception:
                done = 0
            pct = 0
            if total > 0:
                pct = int(min(100, max(0, round(done / total * 100))))
            text = message or f"\u8bad\u7ec3\u8fdb\u5ea6: {pct}%"
            progress.progress(pct, text=text)
        with st.spinner("\u6b63\u5728\u8bad\u7ec3\u591a\u7b56\u7565\u7ec4\u5408\u2026"):
            try:
                from core.strategy_trainer import run_training
                report = run_training(progress_callback=_progress_cb)
                st.session_state["training_report"] = report
                st.session_state["training_report_ts"] = report.get("ts", "")
                st.session_state["training_report_source"] = "manual"
                progress.progress(100, text="\u8bad\u7ec3\u5b8c\u6210")
            except Exception:
                st.session_state["training_report"] = None
                progress.progress(0, text="\u8bad\u7ec3\u5931\u8d25")

    treport = st.session_state.get("training_report")
    if treport:
        ts = st.session_state.get("training_report_ts", "")
        if ts:
            st.caption(f"\u6700\u540e\u8fd0\u884c\u65f6\u95f4: {ts}")
        src = st.session_state.get("training_report_source")
        if src == "report":
            st.caption("\u6570\u636e\u6765\u6e90: \u5386\u53f2\u8bad\u7ec3\u62a5\u544a")
        elif src == "manual":
            st.caption("\u6570\u636e\u6765\u6e90: \u624b\u52a8\u89e6\u53d1")

        summary = _summarize_training_report(treport) or {}
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("\u7b56\u7565\u6570\u91cf", summary.get("strategies", 0))
        t2.metric("\u6837\u672c\u6570", summary.get("samples", 0))
        t3.metric("\u5e73\u5747\u5206\u6570", f"{float(summary.get('avg_score', 0) or 0):.2f}")
        t4.metric("\u5e73\u5747\u6536\u76ca", f"{float(summary.get('avg_return', 0) or 0):.2f}%")

        u1, u2, u3, u4 = st.columns(4)
        u1.metric("\u5e73\u5747\u56de\u64a4", f"{float(summary.get('avg_drawdown', 0) or 0):.2f}%")
        u2.metric("\u8bad\u7ec3\u6a21\u5f0f", summary.get("mode", ""))
        u3.metric("\u6807\u7684\u6c60", summary.get("pool", ""))
        u4.metric("\u6570\u636e\u8986\u76d6", f"{summary.get('codes_with_data', 0)}/{summary.get('codes_total', 0)}")

        strat_rows = []
        strategies = treport.get("strategies", {}) if isinstance(treport.get("strategies", {}), dict) else {}
        for _, s in strategies.items():
            if not isinstance(s, dict):
                continue
            strat_rows.append({
                "strategy": s.get("strategy"),
                "code": s.get("strategy_code"),
                "samples": s.get("samples", 0),
                "avg_score": s.get("avg_score", 0),
                "avg_return": s.get("avg_return", 0),
                "avg_drawdown": s.get("avg_drawdown", 0),
                "errors": s.get("errors", 0),
                "skipped": s.get("skipped", 0)
            })
        if strat_rows:
            df_tr = pd.DataFrame(strat_rows)
            df_tr = df_tr.sort_values("avg_score", ascending=False)
            st.dataframe(df_tr, use_container_width=True)
        else:
            st.info("\u8be5\u6b21\u8bad\u7ec3\u65e0\u53ef\u7528\u7ed3\u679c\u3002")

        wl = treport.get("watchlist_update", {}) if isinstance(treport.get("watchlist_update", {}), dict) else {}
        if wl:
            st.caption(f"\u81ea\u52a8\u80a1\u7968\u6c60: updated={wl.get('updated')} | count={wl.get('count', 0)} | scope={wl.get('source_scope')}")

        sp = treport.get("strategy_pools_update", {}) if isinstance(treport.get("strategy_pools_update", {}), dict) else {}
        if sp:
            st.caption(f"\u7b56\u7565\u6c60\u751f\u6210: updated={sp.get('updated')} | keys={sp.get('count', 0)} | scope={sp.get('source_scope')}")

        try:
            st.download_button("\u4e0b\u8f7d\u6700\u65b0\u8bad\u7ec3\u62a5\u544a", json.dumps(treport, ensure_ascii=False, indent=2), file_name="strategy_training_latest.json", mime="application/json")
        except Exception:
            pass
    else:
        st.info("\u6682\u65e0\u8bad\u7ec3\u62a5\u544a\u3002")

    st.subheader("\u7b56\u7565\u8bad\u7ec3\u8d8b\u52bf")
    tr_hist = _load_training_history()
    if tr_hist is not None and not tr_hist.empty:
        df_tr = tr_hist.copy()
        if "ts" in df_tr.columns:
            df_tr = df_tr.set_index("ts")
        cols = [c for c in ["avg_score", "avg_return", "avg_drawdown", "samples"] if c in df_tr.columns]
        if cols:
            st.line_chart(df_tr[cols])
        else:
            st.info("\u65e0\u53ef\u5c55\u793a\u7684\u8bad\u7ec3\u8d8b\u52bf\u6570\u636e")
    else:
        st.info("\u6682\u65e0\u8bad\u7ec3\u8d8b\u52bf\u6570\u636e")

    st.subheader("\u8bad\u7ec3\u6bcf\u65e5\u770b\u677f")
    daily = _load_training_daily()
    if daily is not None and not daily.empty:
        df_day = daily.copy()
        if "date" in df_day.columns:
            df_day = df_day.set_index("date")
        cols = [c for c in ["avg_score", "avg_return", "avg_drawdown", "samples"] if c in df_day.columns]
        if cols:
            st.line_chart(df_day[cols])
        show_cols = ["date", "strategies", "samples", "avg_score", "avg_return", "avg_drawdown", "codes_with_data", "codes_total"]
        df_show = daily.copy()
        df_show = df_show[[c for c in show_cols if c in df_show.columns]]
        st.dataframe(df_show.tail(30), use_container_width=True)
        try:
            st.download_button("\u4e0b\u8f7d\u8bad\u7ec3\u6bcf\u65e5CSV", daily.to_csv(index=False), file_name="strategy_training_daily.csv", mime="text/csv")
        except Exception:
            pass
    else:
        st.info("\u6682\u65e0\u6bcf\u65e5\u8bad\u7ec3\u6570\u636e")

    st.subheader("\u5f53\u524d\u7b56\u7565\u6c60 (Auto Pool)")
    try:
        from core.strategy_pool import load_pool, pool_enabled
        pool = load_pool()
        enabled = pool_enabled()
        if not enabled:
            st.caption("\u5df2\u5173\u95ed\u7b56\u7565\u6c60\uff0c\u82e5\u9700\u542f\u7528\uff0c\u8bf7\u5728 config/strategy_training.json \u4e2d\u8bbe\u7f6e use_strategy_pool=true")
        if pool and isinstance(pool.get("strategies", []), list):
            st.caption(f"\u6700\u540e\u66f4\u65b0: {pool.get('updated_at','')}")
            df_pool = pd.DataFrame(pool.get("strategies", []))
            if not df_pool.empty:
                st.dataframe(df_pool, use_container_width=True)
            else:
                st.info("\u7b56\u7565\u6c60\u4e3a\u7a7a")
        else:
            st.info("\u6682\u65e0\u7b56\u7565\u6c60\u6570\u636e")
    except Exception:
        st.info("\u6682\u65e0\u7b56\u7565\u6c60\u6570\u636e")

    st.subheader("\u8bad\u7ec3\u62a5\u544a\u5386\u53f2")
    if tr_hist is not None and not tr_hist.empty:
        st.dataframe(tr_hist.tail(50), use_container_width=True)
        try:
            st.download_button("\u4e0b\u8f7d\u8bad\u7ec3\u62a5\u544aCSV", tr_hist.to_csv(index=False), file_name="strategy_training_history.csv", mime="text/csv")
        except Exception:
            pass
    else:
        st.info("\u6682\u65e0\u8bad\u7ec3\u62a5\u544a\u5386\u53f2")

    st.subheader("\u6743\u76ca\u66f2\u7ebf")
    eq = kpis.get("equity_curve", []) or []
    if eq:
        df_eq = pd.DataFrame(eq)
        st.line_chart(df_eq.set_index("ts")["equity"])
    else:
        st.info("\u6682\u65e0\u6743\u76ca\u66f2\u7ebf\u6570\u636e")

    st.subheader("\u56de\u64a4\u533a\u95f4 Top 5")
    dd = kpis.get("drawdown_segments", []) or []
    if dd:
        df_dd = pd.DataFrame(dd)
        if "max_drawdown" in df_dd.columns:
            df_dd["max_drawdown"] = df_dd["max_drawdown"].apply(lambda x: f"{float(x)*100:.2f}%")
        st.dataframe(df_dd, use_container_width=True)
    else:
        st.info("\u6682\u65e0\u56de\u64a4\u533a\u95f4")

    st.subheader("\u52a8\u4f5c\u5206\u5e03 (Policy vs Suggested)")
    dc = kpis.get("decision_counts", {}) or {}
    sc = kpis.get("suggested_counts", {}) or {}
    dist_df = pd.DataFrame({"policy": dc, "suggested": sc}).fillna(0).astype(int)
    st.dataframe(dist_df, use_container_width=True)

    st.subheader("\u60c5\u666f\u6807\u7b7e Top")
    tags = kpis.get("tag_counts", {}) or {}
    if tags:
        tag_df = pd.DataFrame(sorted(tags.items(), key=lambda x: x[1], reverse=True)[:15], columns=["tag", "count"])
        st.dataframe(tag_df, use_container_width=True)
    else:
        st.info("\u6682\u65e0\u6807\u7b7e\u7edf\u8ba1")

    st.subheader("\u8fd130\u5929\u6536\u76ca\u7bb1\u7ebf\u56fe")
    pnl_30d = kpis.get("pnl_30d", []) or []
    if pnl_30d:
        df_pnl = pd.DataFrame({"pnl_pct": pnl_30d})
        fig = px.box(df_pnl, y="pnl_pct", points="outliers")
        fig.update_layout(yaxis_tickformat=".2%")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("\u6682\u65e030\u5929\u6536\u76ca\u6570\u636e")

    st.divider()
    st.subheader("\u8fd1\u671f\u7ed3\u679c (Outcome)")
    rows = []
    for rec in kpis.get("recent_outcomes", []):
        payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
        rows.append({
            "ts": rec.get("ts"),
            "code": rec.get("code"),
            "pnl": payload.get("pnl"),
            "pnl_pct": payload.get("pnl_pct"),
            "signal_source": payload.get("signal_source")
        })
    if rows:
        df = pd.DataFrame(rows)
        if "pnl_pct" in df.columns:
            df["pnl_pct"] = df["pnl_pct"].apply(lambda x: "" if x is None else f"{float(x)*100:.2f}%")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("\u6682\u65e0\u7ed3\u679c\u6570\u636e")

    st.divider()
    st.subheader("\u7b56\u7565\u6392\u884c\u699c (Bandit \u6743\u91cd)")
    try:
        registry = SkillRegistry()
        df = registry.get_leaderboard()
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("\u6682\u65e0\u7b56\u7565\u6570\u636e")
    except Exception:
        st.info("\u6682\u65e0\u7b56\u7565\u6570\u636e")

    st.subheader("\u7b56\u7565 x \u60c5\u666f \u6807\u7b7e\u7edf\u8ba1")
    tag_stats = kpis.get("tag_strategy_stats", []) or []
    if tag_stats:
        df_ts = pd.DataFrame(tag_stats)
        if "win_rate" in df_ts.columns:
            df_ts["win_rate"] = df_ts["win_rate"].apply(lambda x: f"{float(x)*100:.1f}%")
        if "avg_pnl_pct" in df_ts.columns:
            df_ts["avg_pnl_pct"] = df_ts["avg_pnl_pct"].apply(lambda x: f"{float(x)*100:.2f}%")
        st.dataframe(df_ts, use_container_width=True)
    else:
        st.info("\u6682\u65e0\u7b56\u7565\u60c5\u666f\u7edf\u8ba1")

    st.divider()
    st.subheader("\u4e8b\u4ef6\u7d22\u5f15\u68c0\u7d22")
    q1, q2, q3 = st.columns([1, 2, 1])
    code = q1.text_input("\u4ee3\u7801", "")
    query = q2.text_input("\u5173\u952e\u5b57", "")
    use_range = st.checkbox("\u542f\u7528\u65f6\u95f4\u8fc7\u6ee4", value=False)
    d1, d2 = st.columns(2)
    today = datetime.date.today()
    start_date = d1.date_input("\u5f00\u59cb\u65e5\u671f", value=today)
    end_date = d2.date_input("\u7ed3\u675f\u65e5\u671f", value=today)
    if not use_range:
        start_date = None
        end_date = None
    if q3.button("\u67e5\u8be2"):
        try:
            update_index()
            lines = query_context(code=code or None, query_text=query or "", limit=10, start_date=start_date, end_date=end_date)
            if lines:
                st.text("\\n".join(lines))
            else:
                st.info("\u65e0\u5339\u914d\u7ed3\u679c")
        except Exception:
            st.info("\u7d22\u5f15\u67e5\u8be2\u5931\u8d25")

    if st.button("\u5bfc\u51faCSV"):
        try:
            update_index()
            rows = query_events(code=code or None, query_text=query or "", start_date=start_date, end_date=end_date, limit=500)
            if rows:
                df_exp = pd.DataFrame(rows)
                st.download_button("\u4e0b\u8f7d\u4e8b\u4ef6CSV", df_exp.to_csv(index=False), file_name="event_index_export.csv", mime="text/csv")
            else:
                st.info("\u65e0\u53ef\u5bfc\u51fa\u6570\u636e")
        except Exception:
            st.info("\u5bfc\u51fa\u5931\u8d25")
