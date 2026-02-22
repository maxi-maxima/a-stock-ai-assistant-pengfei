import random
import time
import datetime
import streamlit as st

from core.experience_store import ExperienceStore
from core.event_bus import EventBus
from core.trade_simulator import PaperBroker
from core.xiaoliuren import XiaoLiuRen, action_to_cn
from skills.data_factory import DataSkillFactory


def _load_stock_basic_cache():
    cache = st.session_state.get("luck_stock_basic")
    if isinstance(cache, dict) and cache.get("map"):
        return cache
    name_map = {}
    multi_map = {}
    try:
        skill = DataSkillFactory.get_skill("tushare")
        rows = skill.get_all_stocks()
        for r in rows or []:
            name = str(r.get("name", "")).strip()
            code = str(r.get("code", "")).strip().upper()
            if not name or not code:
                continue
            if name in name_map and name_map[name] != code:
                multi_map.setdefault(name, set()).update({name_map[name], code})
            else:
                name_map[name] = code
    except Exception:
        pass
    cache = {"map": name_map, "multi": multi_map}
    st.session_state["luck_stock_basic"] = cache
    return cache


def _resolve_chinese_name(name):
    cache = _load_stock_basic_cache()
    name_map = cache.get("map", {})
    multi_map = cache.get("multi", {})
    if name in multi_map:
        return random.choice(sorted(list(multi_map.get(name) or [])))
    return name_map.get(name)


def _parse_codes(text):
    if not text:
        return [], []
    raw = str(text)
    for sep in ["\n", ",", "，", ";", "；", "|", " "]:
        raw = raw.replace(sep, ",")
    tokens = [t.strip().upper() for t in raw.split(",") if t.strip()]
    out = []
    unresolved = []
    for t in tokens:
        if t.endswith(".SH") or t.endswith(".SZ"):
            out.append(t)
        elif t.isdigit() and len(t) == 6:
            suffix = ".SH" if t.startswith("6") else ".SZ"
            out.append(t + suffix)
        else:
            resolved = _resolve_chinese_name(t)
            if resolved:
                out.append(resolved)
            else:
                unresolved.append(t)
    seen = set()
    uniq = []
    for c in out:
        if c not in seen:
            uniq.append(c)
            seen.add(c)
    return uniq, unresolved


def _get_latest_price(code):
    try:
        skill = DataSkillFactory.get_skill("tushare")
        df = skill.get_history(code, days=30)
        if df is not None and not df.empty:
            return float(df.iloc[-1]["close"])
    except Exception:
        return None
    return None


def _log_decision_event(code, payload, decision_id, source="luck"):
    try:
        bus = EventBus()
        payload = payload if isinstance(payload, dict) else {}
        event_payload = dict(payload)
        if "action" in event_payload and "suggested_action" not in event_payload:
            event_payload["suggested_action"] = event_payload.get("action")
        bus.log(
            "decision",
            payload=event_payload,
            code=code,
            decision_id=decision_id,
            source=source
        )
    except Exception:
        pass


def _execute_buy(code, coin_flips=None, signal_source=None, decision_meta=None):
    price = _get_latest_price(code)
    if not price or price <= 0:
        return False, "无法获取价格，未执行"
    broker = PaperBroker("data/paper_portfolio.json")
    finfo = broker.portfolio.get_fund_info()
    available = float(finfo.get("available", 0) or 0)
    if available <= 0:
        return False, "可用资金不足，未执行"
    exp = ExperienceStore()
    signal_source = signal_source or {"source": "luck"}
    payload = {
        "code": code,
        "action": "BUY",
        "coin_flips": coin_flips or [],
        "signal_source": signal_source
    }
    if decision_meta:
        payload["meta"] = decision_meta
    decision_id = exp.log_decision(payload)
    _log_decision_event(code, payload, decision_id)
    ok, msg = broker.buy(
        code,
        price,
        available,
        reason="luck",
        decision_id=decision_id,
        signal_source=signal_source,
        features=decision_meta
    )
    return ok, msg


def _execute_sell(code, signal_source=None, decision_meta=None):
    price = _get_latest_price(code)
    if not price or price <= 0:
        return False, "无法获取价格，未执行"
    broker = PaperBroker("data/paper_portfolio.json")
    pos = broker.portfolio.get_specific_position(code)
    if not pos or pos.get("volume", 0) <= 0:
        return False, "无持仓"
    exp = ExperienceStore()
    signal_source = signal_source or {"source": "luck"}
    payload = {
        "code": code,
        "action": "SELL",
        "signal_source": signal_source
    }
    if decision_meta:
        payload["meta"] = decision_meta
    decision_id = exp.log_decision(payload)
    _log_decision_event(code, payload, decision_id)
    ok, msg = broker.sell(
        code,
        price,
        reason="luck",
        decision_id=decision_id,
        signal_source=signal_source,
        features=decision_meta
    )
    return ok, msg


def _toss_coins(n=3, delay=0.6):
    placeholder = st.empty()
    flips = []
    for i in range(n):
        flip = random.choice(["正", "反"])
        flips.append(flip)
        placeholder.write(f"投币 {i + 1}/{n}: " + " ".join(flips))
        time.sleep(delay)
    placeholder.write("投币结果: " + " ".join(flips))
    return flips


def _build_xlr_meta(result):
    final = result["final"]
    lunar = result["lunar"]
    solar = result["solar"]
    return {
        "xiaoliuren": {
            "palace": final.name,
            "palace_emoji": final.emoji,
            "action": final.action,
            "solar": solar.strftime("%Y-%m-%d %H:%M"),
            "lunar": {
                "month": lunar.month,
                "day": lunar.day,
                "hour_branch": lunar.hour_branch,
            }
        }
    }


def _pick_trade_code(codes, action):
    if action == "SELL":
        broker = PaperBroker("data/paper_portfolio.json")
        held = []
        for c in codes:
            pos = broker.portfolio.get_specific_position(c)
            if pos and pos.get("volume", 0) > 0:
                held.append(c)
        if not held:
            return None, "这些代码没有持仓可卖"
        return random.choice(held), None
    if not codes:
        return None, "没有可用代码"
    return (codes[0] if len(codes) == 1 else random.choice(codes)), None


def render():
    st.header("🎲 纯运气")
    text = st.text_area("股票列表", height=120, placeholder="输入股票代码，逗号/空格/换行分隔")

    method = st.radio("决策方式", ["抛硬币", "小六壬"], horizontal=True)
    xlr_result = None
    if method == "小六壬":
        use_custom = st.checkbox("自定义时间", value=False)
        dt = None
        if use_custom:
            d = st.date_input("日期", value=datetime.date.today())
            t = st.time_input("时间", value=datetime.datetime.now().time().replace(second=0, microsecond=0))
            dt = datetime.datetime.combine(d, t)
        xlr = XiaoLiuRen()
        xlr_result = xlr.predict(dt)
        final = xlr_result["final"]
        st.markdown(f"**小六壬落宫**: {final.emoji} {final.name}")
        st.caption(f"解释: {final.meaning}")
        st.caption(f"建议: {action_to_cn(final.action)}")

    if st.button("随机决定", type="primary"):
        codes, unresolved = _parse_codes(text)
        if unresolved:
            st.write("未识别：", ", ".join(unresolved))
        if not codes:
            st.write("请输入股票")
            return

        if method == "抛硬币":
            flips = _toss_coins()
            heads = flips.count("正")
            action = "BUY" if heads >= 2 else "HOLD"
            if action == "BUY":
                code, _ = _pick_trade_code(codes, action)
                ok, msg = _execute_buy(
                    code,
                    coin_flips=flips,
                    signal_source={"source": "luck", "method": "coin"}
                )
                st.write(f"随机结果: 买入 {code}")
                st.write(msg)
            else:
                exp = ExperienceStore()
                payload = {
                    "code": ",".join(codes),
                    "action": "HOLD",
                    "coin_flips": flips,
                    "signal_source": {"source": "luck", "method": "coin"}
                }
                decision_id = exp.log_decision(payload)
                _log_decision_event(",".join(codes), payload, decision_id)
                st.write("随机结果: 不买")
            return

        if not xlr_result:
            xlr_result = XiaoLiuRen().predict()
        final = xlr_result["final"]
        action = final.action
        meta = _build_xlr_meta(xlr_result)
        signal_source = {
            "source": "luck",
            "method": "xiaoliuren",
            "palace": final.name
        }

        if action == "BUY":
            code, err = _pick_trade_code(codes, action)
            if err:
                st.write(err)
                return
            ok, msg = _execute_buy(code, signal_source=signal_source, decision_meta=meta)
            st.write(f"小六壬结果: 买入 {code}")
            st.write(msg)
        elif action == "SELL":
            code, err = _pick_trade_code(codes, action)
            if err:
                st.write(err)
                return
            ok, msg = _execute_sell(code, signal_source=signal_source, decision_meta=meta)
            st.write(f"小六壬结果: 卖出 {code}")
            st.write(msg)
        else:
            exp = ExperienceStore()
            payload = {
                "code": ",".join(codes),
                "action": "HOLD",
                "signal_source": signal_source,
                "meta": meta
            }
            decision_id = exp.log_decision(payload)
            _log_decision_event(",".join(codes), payload, decision_id)
            st.write("小六壬结果: 观望")
