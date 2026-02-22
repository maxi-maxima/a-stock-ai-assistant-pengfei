import os
import json
import datetime
import pandas as pd
import streamlit as st

from core.watchlist import (
    WATCHLIST_PATH,
    append_entries,
    load_entries,
    save_entries,
    normalize_code,
)
from core.stock_name import resolve_name
from skills.data_factory import DataSkillFactory


def _load_name_maps(force=False):
    cache = st.session_state.get("watchlist_name_map")
    if isinstance(cache, dict) and cache.get("code_to_name") and not force:
        return cache
    code_to_name = {}
    name_to_code = {}
    try:
        skill = DataSkillFactory.get_skill("tushare")
        rows = skill.get_all_stocks()
        for r in rows or []:
            code = r.get("code") or r.get("ts_code") or r.get("symbol")
            name = r.get("name")
            if not code or not name:
                continue
            code = normalize_code(code)
            if not code:
                continue
            code_to_name[code] = name
            name_to_code[name] = code
    except Exception:
        pass
    cache = {
        "code_to_name": code_to_name,
        "name_to_code": name_to_code,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    st.session_state["watchlist_name_map"] = cache
    return cache


def _display_name(code, code_to_name):
    if not code:
        return ""
    name = code_to_name.get(code)
    if name:
        return name
    try:
        return resolve_name(code) or code
    except Exception:
        return code


def _parse_codes_text(text):
    if not text:
        return [], []
    raw = str(text)
    for sep in ["\n", ",", "，", ";", "；", "|", " "]:
        raw = raw.replace(sep, ",")
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    out = []
    unresolved = []
    name_map = _load_name_maps()
    name_to_code = name_map.get("name_to_code", {}) if isinstance(name_map, dict) else {}
    for t in tokens:
        code = normalize_code(t)
        if code and (code.endswith(".SH") or code.endswith(".SZ") or (code.isdigit() and len(code) == 6)):
            out.append(code)
            continue
        # try resolve by chinese name
        mapped = name_to_code.get(t)
        if mapped:
            out.append(mapped)
        else:
            unresolved.append(t)
    # unique preserve order
    seen = set()
    uniq = []
    for c in out:
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq, unresolved


def _file_mtime(path):
    if not os.path.exists(path):
        return ""
    try:
        ts = os.path.getmtime(path)
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _get_latest_price(code):
    try:
        skill = DataSkillFactory.get_skill("tushare")
        df = skill.get_history(code, days=30)
        if df is not None and not df.empty:
            return float(df.iloc[-1]["close"])
    except Exception:
        return None
    return None


def render():
    st.header("\u89c2\u5bdf\u6c60")
    st.caption(f"\u5b58\u50a8\u4f4d\u7f6e: {WATCHLIST_PATH}")

    entries = load_entries()
    codes = [e.get("code") for e in entries if e.get("code")]
    name_maps = _load_name_maps()
    code_to_name = name_maps.get("code_to_name", {}) if isinstance(name_maps, dict) else {}
    col1, col2, col3 = st.columns(3)
    col1.metric("\u6807\u7684\u6570\u91cf", len(codes))
    col2.metric("\u6587\u4ef6\u72b6\u6001", "\u5b58\u5728" if os.path.exists(WATCHLIST_PATH) else "\u4e0d\u5b58\u5728")
    col3.metric("\u6700\u540e\u66f4\u65b0", _file_mtime(WATCHLIST_PATH) or "n/a")
    meta_cols = st.columns([1, 1, 2])
    with meta_cols[0]:
        if st.button("\u5237\u65b0\u540d\u79f0\u5e93"):
            name_maps = _load_name_maps(force=True)
            code_to_name = name_maps.get("code_to_name", {}) if isinstance(name_maps, dict) else {}
            st.success("\u540d\u79f0\u5e93\u5df2\u66f4\u65b0")
            st.rerun()
    with meta_cols[1]:
        st.caption(f"\u540d\u79f0\u5e93\u6570\u91cf: {len(code_to_name)}")
    with meta_cols[2]:
        st.caption(f"\u540d\u79f0\u5e93\u66f4\u65b0: {name_maps.get('updated_at', 'n/a') if isinstance(name_maps, dict) else 'n/a'}")
    if codes and not code_to_name:
        st.info("\u540d\u79f0\u5e93\u4e3a\u7a7a\uff0c\u53ef\u80fd\u9700\u8981\u914d\u7f6e Tushare Token\uff0c\u6216\u70b9\u51fb\u201c\u5237\u65b0\u540d\u79f0\u5e93\u201d\u91cd\u8bd5\u3002")

    st.divider()
    st.subheader("\u89c2\u5bdf\u6c60\u5217\u8868")
    if entries:
        rows = []
        for e in entries:
            code = e.get("code")
            rows.append({
                "name": _display_name(code, code_to_name),
                "code": code,
                "init_price": e.get("init_price"),
                "source": e.get("source") or "unknown",
                "source_detail": e.get("source_detail") or "",
                "added_at": e.get("added_at") or ""
            })
        df = pd.DataFrame(rows)
        # price cache
        price_cache = st.session_state.get("watchlist_price_cache", {})
        if st.button("\u5237\u65b0\u73b0\u4ef7/\u80dc\u7387"):
            new_cache = {}
            for c in codes:
                new_cache[c] = _get_latest_price(c)
            st.session_state["watchlist_price_cache"] = new_cache
            price_cache = new_cache
            st.success("\u73b0\u4ef7\u5df2\u66f4\u65b0")
        if isinstance(price_cache, dict) and price_cache:
            df["current_price"] = df["code"].map(lambda c: price_cache.get(c))
            def _calc_ret(row):
                try:
                    p0 = float(row.get("init_price") or 0)
                    p1 = float(row.get("current_price") or 0)
                    if p0 > 0 and p1 > 0:
                        return (p1 - p0) / p0
                except Exception:
                    return None
                return None
            df["return_pct"] = df.apply(_calc_ret, axis=1)
            valid = df["return_pct"].dropna()
            if not valid.empty:
                win_rate = (valid > 0).mean() * 100
                st.caption(f"\u80dc\u7387: {win_rate:.1f}%  (\u6709\u4ef7\u683c\u7684 {len(valid)} \u53ea)")
        keyword = st.text_input("\u641c\u7d22", placeholder="\u8f93\u5165\u540d\u79f0\u6216\u4ee3\u7801")
        if keyword:
            kw = str(keyword).strip()
            if kw:
                df = df[df["name"].str.contains(kw, case=False, na=False) | df["code"].str.contains(kw, case=False, na=False)]
        # format
        if "init_price" in df.columns:
            df["init_price"] = df["init_price"].apply(lambda v: f"{float(v):.2f}" if v is not None else "")
        if "current_price" in df.columns:
            df["current_price"] = df["current_price"].apply(lambda v: f"{float(v):.2f}" if v is not None else "")
        if "return_pct" in df.columns:
            df["return_pct"] = df["return_pct"].apply(lambda v: f"{float(v)*100:.2f}%" if v is not None else "")
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "\u5bfc\u51faCSV",
            df.to_csv(index=False),
            file_name="watchlist.csv",
            mime="text/csv"
        )
        st.download_button(
            "\u5bfc\u51faJSON",
            json.dumps({"codes": codes}, ensure_ascii=False, indent=2),
            file_name="watchlist.json",
            mime="application/json"
        )
    else:
        st.info("\u89c2\u5bdf\u6c60\u4e3a\u7a7a")

    st.divider()
    st.subheader("\u7ef4\u62a4\u89c2\u5bdf\u6c60")
    add_text = st.text_area(
        "\u6dfb\u52a0\u4ee3\u7801",
        height=120,
        placeholder="\u652f\u6301\u4ee3\u7801\u6216\u4e2d\u6587\u540d\u79f0\uff0c\u6362\u884c/\u9017\u53f7/\u7a7a\u683c\u5206\u9694"
    )
    add_cols = st.columns([1, 2, 1])
    with add_cols[0]:
        if st.button("\u6dfb\u52a0\u5230\u89c2\u5bdf\u6c60"):
            new_codes, unresolved = _parse_codes_text(add_text)
            if unresolved:
                st.warning("\u672a\u8bc6\u522b: " + ", ".join(unresolved))
            if not new_codes:
                st.warning("\u6ca1\u6709\u53ef\u7528\u4ee3\u7801")
            else:
                entries_to_add = [{"code": c, "source": "manual", "source_detail": "\u89c2\u5bdf\u6c60\u9875"} for c in new_codes]
                merged = append_entries(entries_to_add, fill_price=True, fill_name=True)
                st.success(f"\u5df2\u5199\u5165 {len(new_codes)} \u4e2a\u6807\u7684\uff0c\u73b0\u6709 {len(merged)} \u4e2a")
                st.rerun()

    if codes:
        remove_sel = st.multiselect("\u4ece\u89c2\u5bdf\u6c60\u79fb\u9664", codes)
        with add_cols[2]:
            if st.button("\u79fb\u9664\u6240\u9009"):
                if not remove_sel:
                    st.warning("\u8bf7\u5148\u9009\u62e9\u8981\u79fb\u9664\u7684\u4ee3\u7801")
                else:
                    keep_set = set(remove_sel)
                    kept = [e for e in entries if e.get("code") not in keep_set]
                    save_entries(kept)
                    st.success(f"\u5df2\u79fb\u9664 {len(remove_sel)} \u4e2a\u6807\u7684\uff0c\u5269\u4f59 {len(kept)} \u4e2a")
                    st.rerun()
