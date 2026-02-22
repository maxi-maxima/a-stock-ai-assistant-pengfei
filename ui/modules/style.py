import json
import os

import streamlit as st

from core.learning_log import log_event
from core.stock_name import display_name


def _parse_codes(text):
    if not text:
        return []
    for sep in ["，", "\n", ";", "；", " "]:
        text = text.replace(sep, ",")
    parts = [p.strip() for p in text.split(",") if p.strip()]
    seen = set()
    out = []
    for p in parts:
        code = p.upper()
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _load_profile():
    path = "config/style_profile.json"
    if not os.path.exists(path):
        return {}, path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except Exception:
        return {}, path

def render(learner, memory):
    st.header("🧬 风格 DNA 实验室")

    source_name = getattr(getattr(learner, "data_skill", None), "source_name", "Unknown")
    pro_ok = bool(getattr(getattr(getattr(learner, "data_skill", None), "market", None), "pro", None))
    try:
        from skills import data_factory as _df
        ak_ok = _df.ak is not None
    except Exception:
        ak_ok = False
    st.caption(f"数据源: {source_name} | Tushare Pro: {'OK' if pro_ok else 'Unavailable'} | Akshare: {'OK' if ak_ok else 'Unavailable'}")

    profile, profile_path = _load_profile()
    if profile:
        with st.expander("🧬 当前 DNA 档案", expanded=False):
            st.json(profile)
    else:
        st.caption("当前暂无 DNA 档案。")

    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🗑️ 清空 DNA"):
            try:
                if os.path.exists(profile_path):
                    os.remove(profile_path)
                st.success("已清空 DNA 档案。")
            except Exception:
                st.error("清空失败，请检查文件权限。")

    tab1, tab2 = st.tabs(["🧬 特征提取", "🎓 强制教学"])

    with tab1:
        st.markdown("告诉 AI 你喜欢的股票，它将提取特征并用于扫描。")
        txt = st.text_area("样本代码 (逗号/换行分隔)", "600519.SH, 600036.SH")
        if st.button("🧬 提取 DNA"):
            samps = _parse_codes(txt)
            if not samps:
                st.warning("请先输入至少 1 个有效代码。")
            else:
                prof, logs = learner.learn_from_examples(samps)
                if isinstance(prof, dict):
                    st.success("DNA 提取成功！")
                    st.write(prof)
                    if prof.get("behavior"):
                        st.info(f"行为画像: 风险偏好={prof['behavior'].get('risk_appetite')} | 持仓偏好={prof['behavior'].get('holding_preference')} | 活跃度={prof['behavior'].get('activity_level')}")
                    log_event("dna_extract", {"samples": samps, "profile": prof})
                else:
                    st.error("提取失败")
                if logs:
                    st.text_area("处理日志", "\n".join(logs), height=140)

    with tab2:
        st.info("在这里输入股票，告诉 AI：‘这就是我要的买点’。AI 会分析尾盘数据并死死记住。")
        teach_code = st.text_input("教学样本代码", "000001.SZ")
        if st.button("🎓 强制教学"):
            with st.status("正在分析样本特征...") as s:
                res, msg = learner.analyze_teaching_case(teach_code)
                if res:
                    s.update(label="特征提取完成", state="complete")
                    st.text_area("分析摘要", res.get("analysis", ""), height=140)
                    if res.get("tech_data"):
                        with st.expander("技术数据", expanded=False):
                            st.json(res.get("tech_data"))
                    detail = {"core_view": res['analysis'], "final_verdict": "用户强制教学样本"}
                    memory.save_episode(teach_code, "BUY", res['price'], detail, manual_teach=True)
                    log_event("teaching_case", {"code": teach_code, "price": res.get("price"), "analysis": res.get("analysis")})
                    st.success(f"✅ 已将 {display_name(teach_code, with_code=True)} 设为永久买入案例！")
                else: st.error(msg)
