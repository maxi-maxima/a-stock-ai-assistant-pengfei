import os
import json
import hashlib
import streamlit as st
import pandas as pd
import yaml

from skills.data_factory import TushareMaster
import skills.data_factory as data_factory
from core.blindbox_report import load_blindbox_health_snapshot
from core.portfolio import VirtualPortfolio
from core.memory import MemoryManager
from core.knowledge_base import KnowledgeBase
from core.ta_utils import resolve_ma_periods, ma_series
from core.tri_brain import TriBrainCouncil

SECURE_SETTINGS_PATH = "data/secure_settings.json"
AUTH_PATH = "data/system_auth.json"
CONFIG_PATH = "config/llm_config.yaml"


def _status(val):
    if val is None:
        return "EMPTY"
    if isinstance(val, pd.DataFrame):
        return "OK" if not val.empty else "EMPTY"
    if isinstance(val, (list, dict, str)):
        return "OK" if len(val) > 0 else "EMPTY"
    return "OK"


def _detail(val):
    if val is None:
        return "None"
    if isinstance(val, pd.DataFrame):
        return f"rows={len(val)} cols={len(val.columns)}"
    if isinstance(val, dict):
        return f"keys={len(val)}"
    if isinstance(val, list):
        return f"items={len(val)}"
    if isinstance(val, str):
        return f"len={len(val)}"
    return str(val)


def _ensure_instances(scanner, portfolio, memory, kb):
    tm = None
    if scanner is not None:
        tm = getattr(scanner, "data_skill", None)
    if tm is None:
        tm = TushareMaster()
    if portfolio is None:
        portfolio = VirtualPortfolio("data/real_portfolio.json")
    if memory is None:
        memory = MemoryManager()
    if kb is None:
        kb = KnowledgeBase()
    return tm, portfolio, memory, kb


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _mask_token(token):
    if not token:
        return ""
    token = str(token)
    if len(token) <= 6:
        return "*" * len(token)
    return token[:2] + "*" * (len(token) - 4) + token[-2:]


def _hash_password(password, salt):
    raw = (salt + password).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _get_auth_record():
    return _load_json(AUTH_PATH, {})


def _set_password(new_password):
    salt = os.urandom(8).hex()
    record = {"salt": salt, "hash": _hash_password(new_password, salt)}
    return _save_json(AUTH_PATH, record)


def _verify_password(password):
    env_pw = os.getenv("SYSTEM_ADMIN_PASSWORD")
    if env_pw:
        return password == env_pw
    record = _get_auth_record()
    salt = record.get("salt")
    stored = record.get("hash")
    if not salt or not stored:
        return False
    return _hash_password(password, salt) == stored


def _load_config_token():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            conf = yaml.safe_load(f) or {}
        return str(conf.get("system", {}).get("tushare_token", "") or "").strip()
    except Exception:
        return ""


def _load_secure_token():
    data = _load_json(SECURE_SETTINGS_PATH, {})
    return str(data.get("tushare_token", "") or "").strip()


def _save_secure_token(token):
    data = _load_json(SECURE_SETTINGS_PATH, {})
    if token:
        data["tushare_token"] = token.strip()
    else:
        data.pop("tushare_token", None)
    return _save_json(SECURE_SETTINGS_PATH, data)


def _check_tushare(tm, code):
    token = getattr(getattr(tm, "market", None), "token", "")
    pro_ok = getattr(getattr(tm, "market", None), "pro", None) is not None
    last_trade = None
    try:
        last_trade = tm.get_last_trade_date()
    except Exception:
        last_trade = None
    hist = None
    try:
        hist = tm.get_history(code, days=30)
    except Exception:
        hist = None
    hist_rows = len(hist) if isinstance(hist, pd.DataFrame) else 0

    ts_ok = bool(token) and pro_ok and last_trade is not None
    if ts_ok and hist_rows > 0:
        source = "Tushare"
    elif hist_rows > 0 and data_factory.ak is not None:
        source = "AkShare"
    else:
        source = "None"

    return {
        "token_present": bool(token),
        "token_len": len(token) if token else 0,
        "pro_ok": pro_ok,
        "last_trade_date": str(last_trade) if last_trade else "",
        "history_rows": hist_rows,
        "source": source,
        "ts_lib": data_factory.ts is not None,
        "ak_lib": data_factory.ak is not None,
    }


def _check_financial_interface(tm, code):
    res = {"income": "EMPTY", "balance": "EMPTY", "cashflow": "EMPTY"}
    detail = {}
    try:
        inc = tm.financial.get_income_statement(code)
        if isinstance(inc, tuple):
            inc = inc[0]
        res["income"] = _status(inc)
        detail["income"] = _detail(inc)
    except Exception as e:
        res["income"] = "ERROR"
        detail["income"] = str(e)
    try:
        bs = tm.financial.get_balance_sheet(code)
        if isinstance(bs, tuple):
            bs = bs[0]
        res["balance"] = _status(bs)
        detail["balance"] = _detail(bs)
    except Exception as e:
        res["balance"] = "ERROR"
        detail["balance"] = str(e)
    try:
        cf = tm.financial.get_cashflow(code)
        if isinstance(cf, tuple):
            cf = cf[0]
        res["cashflow"] = _status(cf)
        detail["cashflow"] = _detail(cf)
    except Exception as e:
        res["cashflow"] = "ERROR"
        detail["cashflow"] = str(e)
    return res, detail


def _build_interface_status(pack, morning_pack, ref, feat, macro):
    rows = []

    def add(name, val):
        rows.append({"Interface": name, "Status": _status(val), "Detail": _detail(val)})

    add("history", pack.get("history"))
    add("market_index", pack.get("market_index"))
    add("stock_info", pack.get("stock_info"))
    add("valuation", pack.get("valuation"))
    add("stock_news", pack.get("stock_news"))
    add("money_flow", pack.get("money_flow"))
    add("sector_flow", pack.get("sector_flow"))
    add("chip_perf", pack.get("chip_perf"))
    add("global_index", pack.get("global_index"))
    add("tech_factors", pack.get("tech_factors"))
    add("macro_indices", morning_pack.get("indices"))
    add("macro_news", morning_pack.get("news"))

    if ref is not None:
        add("reference_pack", ref)
    if feat is not None:
        add("feature_pack", feat)
    if macro is not None:
        add("macro_pack", macro)

    return rows


def _build_context_snapshot(code, pack, ref, feat, macro, portfolio, memory, kb, deep=False):
    hist = pack.get("history")
    latest_price = 0
    ma20 = 0
    p_mid1 = None
    pct_chg = None
    vol = None
    last_date = None
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        latest = hist.iloc[-1]
        try:
            latest_price = float(latest.get("close", 0) or 0)
        except Exception:
            latest_price = 0
        try:
            pct_chg = latest.get("pct_chg")
        except Exception:
            pct_chg = None
        try:
            vol = latest.get("vol")
        except Exception:
            vol = None
        try:
            last_date = str(latest.get("date"))
        except Exception:
            last_date = None
        try:
            periods = resolve_ma_periods()
            p_mid1 = periods.get('mid1', 20)
            if len(hist) >= p_mid1:
                ma20 = float(ma_series(hist["close"], p_mid1).iloc[-1])
        except Exception:
            ma20 = 0
    p_mid1 = None

    idx = pack.get("market_index", {}) or {}
    info = pack.get("stock_info", {}) or {}

    market_data = {
        "latest_price": latest_price,
        "index_context": f"INDEX {idx.get('trend', '')}",
        "sector_context": f"{info.get('name', code)} | {info.get('industry', '')}",
        "stock_name": info.get("name", code),
        "last_date": last_date,
        "pct_chg": pct_chg,
        "vol": vol,
    }

    label = f"ema{p_mid1}" if p_mid1 else "ema"
    technical_analysis = f"price={latest_price}, {label}={ma20:.2f}, pct={pct_chg}"

    funds = portfolio.get_fund_info() if portfolio else {}
    pos = portfolio.get_specific_position(code) if portfolio else {}
    position_context = f"available {funds.get('principal', 0):.0f}"
    user_position = {}

    if pos and pos.get("volume", 0) > 0:
        vol_pos = pos.get("volume", 0)
        cost = pos.get("cost", 0.0)
        profit = (latest_price - cost) * vol_pos if latest_price and cost else 0
        pct = (latest_price - cost) / cost * 100 if cost else 0
        position_context += f" | pos {vol_pos} cost {cost} pnl {profit:.0f} ({pct:.1f}%)"
        user_position = {
            "code": code,
            "volume": vol_pos,
            "cost": cost,
            "profit": profit,
            "profit_pct": pct,
        }
    else:
        position_context += " | no position"

    news_list = pack.get("stock_news", []) or []
    news_str = "\n".join(news_list[:3]) if news_list else ""

    mem_ctx = ""
    if memory:
        try:
            mem_ctx = memory.retrieve_context(code, query_text=technical_analysis)
        except Exception:
            mem_ctx = ""

    kb_ctx = ""
    if kb:
        try:
            kb_query = " ".join(
                [
                    str(technical_analysis or ""),
                    str(market_data.get("index_context", "")),
                    str(market_data.get("sector_context", "")),
                    str(market_data.get("stock_name", "")),
                    news_str,
                ]
            ).strip()
            kb_ctx = kb.build_context(kb_query, limit=5).get("context")
        except Exception:
            kb_ctx = ""

    morning_guidance = ""
    try:
        mr = st.session_state.get("morning_result")
        if isinstance(mr, dict):
            morning_guidance = mr.get("view") or ""
    except Exception:
        morning_guidance = ""

    context = {
        "macro_env": news_str,
        "macro_data": macro or {},
        "market_tech": technical_analysis,
        "tech_factors": pack.get("tech_factors", {}),
        "market_data": market_data,
        "position_info": position_context,
        "user_position_detail": user_position,
        "user_fund_detail": funds,
        "capital": pack.get("money_flow", {}),
        "chip": pack.get("chip_perf", {}),
        "news": news_list[:5],
        "fundamental": pack.get("valuation", {}),
        "reference": ref or {},
        "features": feat or {},
        "morning_briefing_guidance": morning_guidance,
        "memory": mem_ctx,
        "knowledge_base": kb_ctx,
    }

    if not deep:
        context["reference"] = None
        context["features"] = None
        context["macro_data"] = None

    return context


def _build_coverage_rows(context, deep=False):
    order = [
        "morning_briefing_guidance",
        "macro_env",
        "macro_data",
        "market_tech",
        "tech_factors",
        "market_data",
        "position_info",
        "user_position_detail",
        "user_fund_detail",
        "capital",
        "chip",
        "news",
        "fundamental",
        "reference",
        "features",
        "memory",
        "knowledge_base",
    ]

    rows = []
    for k in order:
        val = context.get(k)
        status = _status(val)
        detail = _detail(val)
        if k in ("reference", "features", "macro_data") and not deep:
            status = "OFF"
            detail = "deep check disabled"
        if k == "morning_briefing_guidance" and status == "EMPTY":
            detail = "run tactical morning briefing first"
        rows.append({"Param": k, "Status": status, "Detail": detail})
    return rows


def run_self_check(code, scanner=None, portfolio=None, memory=None, kb=None, deep=False):
    tm, portfolio, memory, kb = _ensure_instances(scanner, portfolio, memory, kb)

    pack = {}
    try:
        pack = tm.get_full_analysis_pack(code)
    except Exception:
        pack = {}

    morning_pack = {}
    try:
        morning_pack = tm.get_morning_pack()
    except Exception:
        morning_pack = {}

    ref = feat = macro = None
    if deep:
        try:
            ref = tm.get_reference_pack(code)
        except Exception:
            ref = {}
        try:
            feat = tm.get_feature_pack(code)
        except Exception:
            feat = {}
        try:
            macro = tm.get_macro_pack()
        except Exception:
            macro = {}

    connectivity = _check_tushare(tm, code)
    fin_status, fin_detail = _check_financial_interface(tm, code)
    interface_rows = _build_interface_status(pack, morning_pack, ref, feat, macro)
    context = _build_context_snapshot(code, pack, ref, feat, macro, portfolio, memory, kb, deep=deep)
    coverage_rows = _build_coverage_rows(context, deep=deep)

    return {
        "connectivity": connectivity,
        "interfaces": interface_rows,
        "coverage": coverage_rows,
        "financial": fin_status,
        "financial_detail": fin_detail,
    }


def render(scanner=None, real_portfolio=None, memory=None, kb=None):
    st.header("系统体检")
    with st.expander("盲盒实验机", expanded=False):
        snap = load_blindbox_health_snapshot()
        if not snap.get("available"):
            st.info("盲盒实验机尚未运行，先执行一次 `python tools/blindbox_daily_runner.py --once`")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最近交易日", snap.get("last_trade_date") or "-")
            c2.metric("当前持仓数", int(snap.get("open_positions", 0) or 0))
            c3.metric("活跃策略数", int(snap.get("active_strategies", 0) or 0))
            c4.metric("最近已实现盈亏", f"{float(snap.get('realized_pnl_sum', 0.0) or 0.0):.2f}")
            st.caption(
                f"补跑天数={snap.get('processed_days', 0)} | "
                f"新开仓={snap.get('opened_count', 0)} | "
                f"已平仓={snap.get('closed_count', 0)} | "
                f"当前头号策略={snap.get('top_strategy_id', '')} ({snap.get('top_strategy_weight', 0.0):.2f})"
            )

    with st.expander("🤖 三脑状态", expanded=False):
        council = TriBrainCouncil()
        active = list(council.brains.keys())
        st.write("当前启用脑区：", ", ".join(active) if active else "无")
        for name, meta in council.brains.items():
            st.caption(f"{name}: {meta.get('model')} @ {meta.get('base_url')}")

    with st.expander("🔐 Tushare Token 管理（需密码）", expanded=False):
        st.caption("优先级：环境变量 TUSHARE_TOKEN > 系统安全存储(data/secure_settings.json) > config/llm_config.yaml")

        env_token = os.getenv("TUSHARE_TOKEN", "").strip()
        secure_token = _load_secure_token()
        yaml_token = _load_config_token()

        st.write("环境变量:", "已设置" if env_token else "未设置")
        st.write("安全存储:", "已设置" if secure_token else "未设置")
        st.write("配置文件:", "已设置" if yaml_token else "未设置")

        auth_ok = st.session_state.get("sys_auth_ok", False)
        env_pw = os.getenv("SYSTEM_ADMIN_PASSWORD")
        auth_record = _get_auth_record()

        if not env_pw and not auth_record.get("hash"):
            st.info("未设置管理密码。请先设置一次密码（仅存储哈希）。")
            new_pw = st.text_input("设置管理密码", type="password", key="sys_new_pw")
            new_pw2 = st.text_input("确认管理密码", type="password", key="sys_new_pw2")
            if st.button("保存管理密码", key="sys_set_pw"):
                if not new_pw or len(new_pw) < 6:
                    st.error("密码至少 6 位")
                elif new_pw != new_pw2:
                    st.error("两次密码不一致")
                else:
                    if _set_password(new_pw):
                        st.success("管理密码已设置")
                    else:
                        st.error("保存失败，请检查写入权限")
        else:
            st.caption("已设置管理密码（环境变量或本地哈希）")

        if not auth_ok:
            pw = st.text_input("输入管理密码解锁", type="password", key="sys_auth_pw")
            if st.button("解锁", key="sys_unlock"):
                if _verify_password(pw):
                    st.session_state["sys_auth_ok"] = True
                    st.success("已解锁")
                else:
                    st.error("密码错误")

        if auth_ok:
            st.caption(f"当前安全存储 token: {_mask_token(secure_token) if secure_token else '无'}")
            new_token = st.text_input("更新 Tushare Token", type="password", key="sys_new_token")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("保存到安全存储", key="sys_save_token"):
                    if not new_token:
                        st.error("请输入 Token")
                    else:
                        if _save_secure_token(new_token):
                            st.success("已保存到安全存储")
                        else:
                            st.error("保存失败")
            with c2:
                if st.button("清空安全存储", key="sys_clear_token"):
                    if _save_secure_token(""):
                        st.success("已清空安全存储")
                    else:
                        st.error("清空失败")

            st.caption("修改后需重启或重新加载应用以生效。")

    code = st.text_input("Target Code", value="000001.SZ", key="syscheck_code")
    deep = st.checkbox("深度检查（参考/特征/宏观）", value=False, key="syscheck_deep")

    run = st.button("开始体检", type="primary", use_container_width=True)

    if run:
        st.session_state["syscheck_result"] = run_self_check(
            code,
            scanner=scanner,
            portfolio=real_portfolio,
            memory=memory,
            kb=kb,
            deep=deep,
        )
        st.session_state["syscheck_code_last"] = code
        st.session_state["syscheck_deep_last"] = deep

    result = st.session_state.get("syscheck_result")
    if not result:
        st.info("点击“开始体检”后生成结果")
        return

    # 1) Tushare connectivity
    st.subheader("数据接口连通性（Tushare）")
    conn = result.get("connectivity", {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("令牌状态", "正常" if conn.get("token_present") else "缺失")
    c2.metric("接口实例", "正常" if conn.get("pro_ok") else "缺失")
    c3.metric("最近交易日", conn.get("last_trade_date") or "无")
    c4.metric("数据来源", conn.get("source") or "无")

    st.caption(
        f"Tushare库={conn.get('ts_lib')} | AkShare库={conn.get('ak_lib')} | 历史数据行数={conn.get('history_rows')} | 令牌长度={conn.get('token_len')}"
    )

    # 2) Interface health
    st.subheader("接口健康度")
    df_iface = pd.DataFrame(result.get("interfaces", []))
    if not df_iface.empty:
        df_iface = df_iface.rename(columns={"Interface": "接口", "Status": "状态", "Detail": "详情"})
        st.dataframe(df_iface, use_container_width=True, hide_index=True)
    else:
        st.warning("接口列表为空")

    # 2.5) Financial interface
    st.subheader("财务接口")
    fin_status = result.get("financial", {})
    fin_detail = result.get("financial_detail", {})
    fin_rows = []
    for k in ["income", "balance", "cashflow"]:
        fin_rows.append({
            "接口": k,
            "状态": fin_status.get(k),
            "详情": fin_detail.get(k, "")
        })
    df_fin = pd.DataFrame(fin_rows)
    if not df_fin.empty:
        st.dataframe(df_fin, use_container_width=True, hide_index=True)
    else:
        st.warning("财务接口列表为空")

    # 3) Parameter coverage
    st.subheader("参数覆盖率")
    df_cov = pd.DataFrame(result.get("coverage", []))
    if not df_cov.empty:
        df_cov = df_cov.rename(columns={"Param": "参数", "Status": "状态", "Detail": "详情"})
        st.dataframe(df_cov, use_container_width=True, hide_index=True)
    else:
        st.warning("覆盖列表为空")

    st.caption("说明：morning_briefing_guidance 需要先在战术室跑一次早报")
