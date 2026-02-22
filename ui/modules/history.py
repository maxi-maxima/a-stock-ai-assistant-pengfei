import datetime
import json

import pandas as pd
import streamlit as st

from core.knowledge_base import KnowledgeBase
from core.learning_log import load_events, summarize_knowledge_effects


def _to_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value[:10])
        except Exception:
            return None
    return None


def _date_in_range(ts, start_date, end_date):
    d = _to_date(ts)
    if d is None:
        return False
    if start_date and d < start_date:
        return False
    if end_date and d > end_date:
        return False
    return True


def _short_text(text, width=80):
    if text is None:
        return ""
    text = str(text).strip()
    if len(text) <= width:
        return text
    return text[:width] + "..."


def _compute_trade_stats(start_date, end_date):
    events = load_events(5000)
    sells = []
    for e in events:
        if e.get("event") != "paper_trade":
            continue
        if not _date_in_range(e.get("ts"), start_date, end_date):
            continue
        payload = e.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if payload.get("action") != "SELL":
            continue
        pnl = payload.get("pnl", 0) or 0
        try:
            pnl = float(pnl)
        except Exception:
            pnl = 0.0
        code = str(payload.get("code", "") or "").strip().upper()
        sells.append({"code": code, "pnl": pnl})

    total = len(sells)
    wins = sum(1 for s in sells if s["pnl"] > 0)
    win_rate = wins / total if total else 0.0
    total_pnl = sum(s["pnl"] for s in sells) if total else 0.0
    avg_pnl = total_pnl / total if total else 0.0
    best = max(sells, key=lambda s: s["pnl"]) if sells else None
    worst = min(sells, key=lambda s: s["pnl"]) if sells else None

    by_code = {}
    for s in sells:
        if not s["code"]:
            continue
        by_code[s["code"]] = by_code.get(s["code"], 0.0) + s["pnl"]
    top_codes = sorted(by_code.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "sells": total,
        "win_rate": win_rate,
        "win_rate_str": f"{win_rate * 100:.1f}%" if total else "—",
        "total_pnl": total_pnl,
        "total_pnl_str": f"{total_pnl:.2f}" if total else "—",
        "avg_pnl": avg_pnl,
        "avg_pnl_str": f"{avg_pnl:.2f}" if total else "—",
        "best": best,
        "worst": worst,
        "top_codes": [{"code": c, "pnl": v} for c, v in top_codes]
    }


def _build_markdown(report):
    rng = report.get("range", {})
    summary = report.get("memory_summary", {})
    trade = report.get("trade_stats", {})
    records = report.get("records", [])
    kb_effects = report.get("knowledge_effects", {}) or {}
    start = rng.get("start", "")
    end = rng.get("end", "")

    lines = [f"# 历史军情报告 ({start} ~ {end})", ""]
    lines.append("## 记忆概览")
    lines.append(f"- 记录数: {summary.get('total', 0)}")
    lines.append(f"- 涉及标的: {summary.get('unique_codes', 0)}")
    buy = summary.get("by_action", {}).get("BUY", 0)
    sell = summary.get("by_action", {}).get("SELL", 0)
    lines.append(f"- BUY/SELL: {buy}/{sell}")
    lines.append(f"- 最新记录: {summary.get('last_ts') or '—'}")
    top_codes = summary.get("top_codes") or []
    if top_codes:
        top_str = ", ".join([f"{c.get('code')}({c.get('count')})" for c in top_codes if c.get('code')])
    else:
        top_str = "—"
    lines.append(f"- Top标的: {top_str}")
    lines.append("")

    lines.append("## 交易战报")
    lines.append(f"- 平仓次数: {trade.get('sells', 0)}")
    lines.append(f"- 胜率: {trade.get('win_rate_str', '—')}")
    lines.append(f"- 总盈亏: {trade.get('total_pnl_str', '—')}")
    lines.append(f"- 平均盈亏: {trade.get('avg_pnl_str', '—')}")
    if trade.get("best"):
        lines.append(f"- 最佳: {trade['best'].get('code')} {trade['best'].get('pnl', 0):.2f}")
    if trade.get("worst"):
        lines.append(f"- 最差: {trade['worst'].get('code')} {trade['worst'].get('pnl', 0):.2f}")
    lines.append("")

    kb_titles = kb_effects.get("by_title", []) if isinstance(kb_effects, dict) else []
    if kb_titles:
        lines.append("## 战法命中效果")
        for item in kb_titles[:5]:
            title = item.get("title")
            hits = item.get("hits", 0)
            win_rate = item.get("win_rate_str", "—")
            avg_pnl = item.get("avg_pnl", 0)
            lines.append(f"- {title}: 命中 {hits} 次 | 胜率 {win_rate} | 平均盈亏 {avg_pnl:.2f}")
        lines.append("")

    lines.append("## 最近记录")
    for rec in records[:10]:
        ts = rec.get("ts") or rec.get("date") or ""
        code = rec.get("code") or ""
        action = rec.get("action") or ""
        price_val = rec.get("price")
        if isinstance(price_val, (int, float)):
            price_str = f"{price_val:.2f}"
        else:
            price_str = str(price_val or "")
        core = _short_text(rec.get("core"), 80).replace("\n", " ")
        lines.append(f"- {ts} {code} {action} {price_str} {core}")

    return "\n".join(lines)


def render(memory):
    st.header("📜 历史军情 & 周报")

    today = datetime.date.today()
    range_mode = st.radio("时间范围", ["近7天", "近30天", "自定义"], horizontal=True)
    if range_mode == "自定义":
        date_range = st.date_input("选择日期", value=(today - datetime.timedelta(days=6), today))
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date = end_date = date_range if date_range else today
    else:
        days = 7 if range_mode == "近7天" else 30
        end_date = today
        start_date = today - datetime.timedelta(days=days - 1)

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        code_filter = st.text_input("代码筛选", placeholder="如 600519 / 000001")
    with c2:
        action_filter = st.multiselect("动作筛选", ["BUY", "SELL", "HOLD", "WATCH", "TEACH"], default=[])
    with c3:
        limit = st.slider("显示条数", 50, 500, 200, step=50)

    records = memory.list_episodes(
        start_date=start_date,
        end_date=end_date,
        code=code_filter or None,
        action=action_filter or None,
        limit=limit
    )
    summary = memory.summarize_episodes(records, start_date=start_date, end_date=end_date)
    trade_stats = _compute_trade_stats(start_date, end_date)

    source_set = {r.get("source") for r in records if isinstance(r, dict) and r.get("source")}
    if source_set:
        st.caption("数据源: " + "、".join(sorted(source_set)))
    else:
        st.caption("数据源: 无")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("记忆条数", summary.get("total", 0))
    m2.metric("涉及标的", summary.get("unique_codes", 0))
    buy_cnt = summary.get("by_action", {}).get("BUY", 0)
    sell_cnt = summary.get("by_action", {}).get("SELL", 0)
    m3.metric("BUY/SELL", f"{buy_cnt}/{sell_cnt}")
    m4.metric("最新记录", summary.get("last_ts") or "—")

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("平仓次数", trade_stats.get("sells", 0))
    t2.metric("胜率", trade_stats.get("win_rate_str", "—"))
    t3.metric("总盈亏", trade_stats.get("total_pnl_str", "—"))
    t4.metric("平均盈亏", trade_stats.get("avg_pnl_str", "—"))

    if trade_stats.get("top_codes"):
        top_str = ", ".join(
            [f"{c['code']}({c['pnl']:.2f})" for c in trade_stats["top_codes"] if c.get("code")]
        )
        st.caption(f"Top 盈亏标的: {top_str}")

    if st.button("📝 生成战况总结"):
        text = summary.get("text") or ""
        if trade_stats.get("sells", 0) > 0:
            text += (
                f"\n\n交易战报: 平仓 {trade_stats.get('sells', 0)} 次，胜率 {trade_stats.get('win_rate_str', '—')}，"
                f"总盈亏 {trade_stats.get('total_pnl_str', '—')}，平均盈亏 {trade_stats.get('avg_pnl_str', '—')}。"
            )
            if trade_stats.get("best"):
                text += f"\n最佳: {trade_stats['best'].get('code')} {trade_stats['best'].get('pnl', 0):.2f}"
            if trade_stats.get("worst"):
                text += f"\n最差: {trade_stats['worst'].get('code')} {trade_stats['worst'].get('pnl', 0):.2f}"
        st.text_area("战况总结", text or "暂无数据", height=240)

    st.divider()
    st.subheader("📚 战法命中效果")
    kb_lookback = st.selectbox("归因窗口 (天)", [3, 7, 14, 30], index=1)
    kb_effects = summarize_knowledge_effects(
        lookback_days=kb_lookback,
        start_date=start_date,
        end_date=end_date
    )
    by_title = kb_effects.get("by_title", [])
    if by_title:
        df_rows = []
        for item in by_title:
            df_rows.append({
                "战法": item.get("title"),
                "命中次数": item.get("hits", 0),
                "胜": item.get("wins", 0),
                "负": item.get("losses", 0),
                "胜率": item.get("win_rate_str", "—"),
                "总盈亏": f"{item.get('pnl_sum', 0):.2f}",
                "平均盈亏": f"{item.get('avg_pnl', 0):.2f}",
                "最近交易": item.get("last_ts", "")
            })
        st.dataframe(pd.DataFrame(df_rows), use_container_width=True, hide_index=True)

        kb = KnowledgeBase()
        if st.button("同步战法效果到知识库"):
            ok = kb.update_effect_stats(by_title)
            if ok:
                st.success("已同步战法效果到知识库。")
            else:
                st.warning("未同步（可能无可用数据）。")

        if kb_effects.get("links"):
            with st.expander("交易-战法关联明细", expanded=False):
                rows = []
                for link in kb_effects.get("links", []):
                    rows.append({
                        "时间": link.get("ts"),
                        "代码": link.get("code"),
                        "盈亏": link.get("pnl"),
                        "战法": ", ".join(link.get("titles", []))
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("暂无可归因的战法效果数据。")

    st.divider()
    st.subheader("记录明细")
    if records:
        rows = []
        for r in records:
            price_val = r.get("price")
            if isinstance(price_val, (int, float)):
                price_str = f"{price_val:.2f}"
            else:
                price_str = str(price_val or "")
            rows.append({
                "时间": r.get("ts") or r.get("date"),
                "代码": r.get("code"),
                "动作": r.get("action"),
                "价格": price_str,
                "类型": r.get("type"),
                "观点": _short_text(r.get("core"), 80)
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("暂无符合条件的记录。")

    st.divider()
    st.subheader("导出")
    report = {
        "range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "memory_summary": summary,
        "trade_stats": trade_stats,
        "knowledge_effects": kb_effects,
        "records": records
    }
    json_data = json.dumps(report, ensure_ascii=False, indent=2)
    st.download_button("下载 JSON", data=json_data, file_name="history_report.json", mime="application/json")
    md_data = _build_markdown(report)
    st.download_button("下载 Markdown", data=md_data, file_name="history_report.md", mime="text/markdown")

    with st.expander("原始记录 (JSON)"):
        st.json(report if records else {"message": "empty"})
