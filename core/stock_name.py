try:
    import streamlit as st
except Exception:
    st = None

from skills.data_factory import DataSkillFactory

_SKILL = None
_FALLBACK_CACHE = {}


def _get_skill():
    global _SKILL
    if _SKILL is None:
        _SKILL = DataSkillFactory.get_skill("tushare")
    return _SKILL


def _get_cache():
    if st is not None:
        try:
            cache = st.session_state.setdefault("name_cache", {})
            if isinstance(cache, dict):
                return cache
        except Exception:
            pass
    return _FALLBACK_CACHE


def resolve_name(code):
    if code is None:
        return ""
    code_str = str(code).strip()
    if not code_str:
        return ""
    cache = _get_cache()
    if code_str in cache:
        return cache[code_str]
    name = code_str
    try:
        info = _get_skill().get_stock_basic_info(code_str)
        if isinstance(info, dict):
            name = info.get("name") or code_str
    except Exception:
        name = code_str
    cache[code_str] = name
    return name


def display_name(code, with_code=False):
    name = resolve_name(code)
    if with_code and code:
        return f"{name} ({code})"
    return name


def map_names_in_df(df, cols=None, with_code=False):
    if df is None:
        return df
    try:
        if df.empty:
            return df
    except Exception:
        return df
    out = df.copy()
    if cols is None:
        cols = ["code", "ts_code", "symbol", "代码", "标的", "股票"]
    for col in cols:
        if col in out.columns:
            out[col] = out[col].apply(lambda v: display_name(v, with_code=with_code))
    return out
