import datetime

import streamlit as st


def _tags_to_list(tags):
    if tags is None:
        return []
    if isinstance(tags, (list, tuple, set)):
        return [str(t).strip() for t in tags if str(t).strip()]
    text = str(tags)
    for sep in [",", ";", "|", "/", " ", "\uFF0C", "\uFF1B", "\u3001"]:
        text = text.replace(sep, ",")
    return [t.strip() for t in text.split(",") if t.strip()]


def _tags_to_text(tags):
    return "/".join(_tags_to_list(tags))


def _get_skill_summaries(kb):
    try:
        knowledge_list = kb.get_all_knowledge()
    except Exception:
        return []
    summaries = []
    for item in knowledge_list:
        tags_list = _tags_to_list(item.get("tags"))
        if "skill_summary" in tags_list:
            summaries.append(item)
    summaries.sort(key=lambda x: str(x.get("title", "")))
    return summaries


def _render_skill_summaries(kb):
    summaries = _get_skill_summaries(kb)
    if not summaries:
        return
    with st.expander("🧭 技能速览", expanded=False):
        for item in summaries:
            title = item.get("title", "无标题")
            tags = _tags_to_text(item.get("tags"))
            content = str(item.get("content", "")).strip()
            structure = item.get("structure", {}) if isinstance(item.get("structure", {}), dict) else {}
            st.markdown(f"**{title}**  `{tags}`")
            if content:
                st.caption(content[:200] + ("..." if len(content) > 200 else ""))
            if structure.get("conditions"):
                st.caption(f"触发条件: {structure.get('conditions')}")
            if structure.get("risk"):
                st.caption(f"风险: {structure.get('risk')}")
            st.divider()


def _parse_time(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value)
        except Exception:
            pass
    return datetime.datetime.min

def render(kb):
    st.header("📚 知识库 (Knowledge Base)")
    st.caption("管理您的交易战法、经典理论与心得。AI 在决策时会参考这些内容。")
    _render_skill_summaries(kb)
    
    # --- 1. 新增知识区域 ---
    with st.expander("✍️ 录入新战法", expanded=False):
        with st.form("add_kb_form"):
            new_title = st.text_input("标题 (如：MACD底背离)", key="kb_new_title")
            new_tags = st.text_input("标签 (如：技术面/趋势/抄底)", key="kb_new_tags")
            new_content = st.text_area("内容 (详细描述战法逻辑)", height=150, key="kb_new_content")
            with st.expander("结构化字段 (可选)", expanded=False):
                new_timeframe = st.text_input("适用周期", key="kb_new_timeframe")
                new_conditions = st.text_area("触发条件", height=80, key="kb_new_conditions")
                new_invalidations = st.text_area("失效条件", height=80, key="kb_new_invalidations")
                new_risk = st.text_input("风险提示", key="kb_new_risk")
                new_examples = st.text_area("例子/案例", height=80, key="kb_new_examples")
            
            submitted = st.form_submit_button("💾 保存入库")
            if submitted and new_title and new_content:
                structure = {
                    "timeframe": new_timeframe,
                    "conditions": new_conditions,
                    "invalidations": new_invalidations,
                    "risk": new_risk,
                    "examples": new_examples
                }
                kb.add_knowledge_structured(new_title, new_content, new_tags, structure=structure)
                st.success(f"✅ 《{new_title}》 已录入！")
                st.rerun()

    st.divider()

    # --- 1.5 粘贴整理导入 ---
    with st.expander("📥 粘贴整理导入", expanded=False):
        st.caption("支持粘贴多条文本、JSON 或 YAML，系统会自动整理为知识库结构。")
        raw_text = st.text_area("粘贴内容", height=220, key="kb_import_raw")
        default_tags = st.text_input("默认标签 (可选)", key="kb_import_tags")
        split_entries = st.checkbox("自动分割多条", value=True, key="kb_import_split")
        use_llm = st.checkbox("使用 Kimi 整理 (需配置 green_brain)", value=False, key="kb_import_llm")
        if st.button("测试 Kimi 连通性", key="kb_kimi_ping"):
            try:
                from core.knowledge_llm import KimiKnowledgeOrganizer
                ok, msg, model = KimiKnowledgeOrganizer().test_connection()
                if ok:
                    st.success(f"Kimi 连接正常 ({model})：{msg}")
                else:
                    st.error(f"Kimi 连接失败：{msg}")
            except Exception as e:
                st.error(f"Kimi 测试异常: {e}")
        auto_score = st.checkbox("自动打分", value=True, key="kb_import_score")
        dedup = st.checkbox("去重", value=True, key="kb_import_dedup")
        merge_similar = st.checkbox("合并相似战法", value=True, key="kb_import_merge")
        threshold = st.slider("相似度阈值", min_value=0.60, max_value=0.95, value=0.78, step=0.01, key="kb_import_threshold")

        c1, c2 = st.columns(2)
        if c1.button("解析预览"):
            try:
                preview = kb.parse_copied_knowledge(
                    raw_text,
                    default_tags=default_tags,
                    split_entries=split_entries,
                    use_llm=use_llm
                )
                st.session_state["kb_import_preview"] = preview
            except Exception:
                st.session_state["kb_import_preview"] = []
        if use_llm:
            if getattr(kb, "_last_llm_ok", False):
                st.caption("已使用 Kimi 整理。")
            elif getattr(kb, "_last_llm_used", False):
                st.warning("Kimi 整理失败，已回退规则解析。请检查密钥或文本长度。")

        if c2.button("导入知识库"):
            try:
                result = kb.import_copied_knowledge(
                    raw_text,
                    default_tags=default_tags,
                    split_entries=split_entries,
                    auto_score=auto_score,
                    dedup=dedup,
                    merge_similar=merge_similar,
                    similarity_threshold=threshold,
                    use_llm=use_llm
                )
                st.success(
                    f"✅ 已导入 {result.get('added', 0)} 条知识 | 合并 {result.get('merged', 0)} | 跳过 {result.get('skipped', 0)}"
                )
                st.session_state["kb_import_preview"] = result.get("items", [])
                st.rerun()
            except Exception:
                st.error("导入失败，请检查格式")

        preview_items = st.session_state.get("kb_import_preview", [])
        if preview_items:
            rows = []
            for item in preview_items:
                if not isinstance(item, dict):
                    continue
                structure = item.get("structure", {}) if isinstance(item.get("structure", {}), dict) else {}
                rows.append({
                    "title": item.get("title", ""),
                    "tags": _tags_to_text(item.get("tags")),
                    "timeframe": structure.get("timeframe", ""),
                    "conditions": structure.get("conditions", "")[:60],
                    "risk": structure.get("risk", "")[:60]
                })
            if rows:
                st.dataframe(rows, use_container_width=True)

    st.divider()

    # --- 2. 知识列表与管理 ---
    st.subheader("🗂️ 现存兵法")
    
    knowledge_list = kb.get_all_knowledge()

    q1, q2, q3 = st.columns([2, 2, 1])
    with q1:
        query = st.text_input("搜索", placeholder="标题 / 正文 / 标签")
    with q2:
        tag_options = sorted({t for item in knowledge_list for t in _tags_to_list(item.get("tags"))})
        selected_tags = st.multiselect("标签筛选", tag_options)
    with q3:
        sort_mode = st.selectbox("排序", ["最新更新", "最早更新", "标题A-Z"])
    
    if not knowledge_list:
        st.info("知识库目前空空如也，快去添加您的第一条战法吧！")
    else:
        filtered = []
        query_l = (query or "").strip().lower()
        for item in knowledge_list:
            title = str(item.get("title", ""))
            content = str(item.get("content", ""))
            tags_list = _tags_to_list(item.get("tags"))
            if query_l:
                hit = query_l in title.lower() or query_l in content.lower() or query_l in " ".join(tags_list).lower()
                if not hit:
                    continue
            if selected_tags:
                if not set(tags_list).intersection(set(selected_tags)):
                    continue
            filtered.append(item)

        if sort_mode == "最新更新":
            filtered.sort(key=lambda x: _parse_time(x.get("updated_at")), reverse=True)
        elif sort_mode == "最早更新":
            filtered.sort(key=lambda x: _parse_time(x.get("updated_at")), reverse=False)
        else:
            filtered.sort(key=lambda x: str(x.get("title", "")))

        if not filtered:
            st.info("暂无符合条件的条目。")
        else:
            for i, item in enumerate(filtered):
                title = item.get("title", "无标题")
                content = item.get("content", "")
                tags = _tags_to_text(item.get("tags"))
                updated_at = item.get("updated_at") or item.get("date") or ""
                structure = item.get("structure", {}) if isinstance(item.get("structure"), dict) else {}
                stats = item.get("stats", {}) if isinstance(item.get("stats"), dict) else {}
                hits = stats.get("hits", 0)
                likes = stats.get("likes", 0)
                dislikes = stats.get("dislikes", 0)
                wins = stats.get("wins", 0)
                losses = stats.get("losses", 0)
                pnl_sum = stats.get("pnl_sum", 0)
                pnl_count = stats.get("pnl_count", 0)
                last_used = stats.get("last_used_at", "")
                last_pnl_at = stats.get("last_pnl_at", "")

                c1, c2 = st.columns([6, 1])
                with c1:
                    with st.expander(f"📘 {title}  [{tags}]"):
                        st.caption(f"更新时间: {updated_at}")
                        if hits or likes or dislikes or last_used or pnl_count:
                            pnl_avg = float(pnl_sum) / pnl_count if pnl_count else 0.0
                            st.caption(
                                f"参考热度: {hits} | 👍 {likes} | 👎 {dislikes} | "
                                f"胜负: {wins}/{losses} | 平均盈亏: {pnl_avg:.2f} | "
                                f"最近使用: {last_used} | 最近战果: {last_pnl_at}"
                            )
                        st.markdown(content)
                        if structure:
                            st.markdown("**结构化字段**")
                            if structure.get("timeframe"):
                                st.markdown(f"- 适用周期: {structure.get('timeframe')}")
                            if structure.get("conditions"):
                                st.markdown(f"- 触发条件: {structure.get('conditions')}")
                            if structure.get("invalidations"):
                                st.markdown(f"- 失效条件: {structure.get('invalidations')}")
                            if structure.get("risk"):
                                st.markdown(f"- 风险: {structure.get('risk')}")
                            if structure.get("examples"):
                                st.markdown(f"- 例子: {structure.get('examples')}")
                        with st.form(f"edit_{i}"):
                            new_title = st.text_input("标题", value=title, key=f"title_{i}")
                            new_tags = st.text_input("标签", value=tags, key=f"tags_{i}")
                            new_content = st.text_area("内容", value=content, height=150, key=f"content_{i}")
                            with st.expander("结构化字段", expanded=False):
                                new_timeframe = st.text_input("适用周期", value=structure.get("timeframe", ""), key=f"timeframe_{i}")
                                new_conditions = st.text_area("触发条件", value=structure.get("conditions", ""), height=80, key=f"conditions_{i}")
                                new_invalidations = st.text_area("失效条件", value=structure.get("invalidations", ""), height=80, key=f"invalidations_{i}")
                                new_risk = st.text_input("风险提示", value=structure.get("risk", ""), key=f"risk_{i}")
                                new_examples = st.text_area("例子/案例", value=structure.get("examples", ""), height=80, key=f"examples_{i}")
                            if st.form_submit_button("保存修改"):
                                new_structure = {
                                    "timeframe": new_timeframe,
                                    "conditions": new_conditions,
                                    "invalidations": new_invalidations,
                                    "risk": new_risk,
                                    "examples": new_examples
                                }
                                ok, msg = kb.update_knowledge_structured(title, new_title, new_content, new_tags, structure=new_structure)
                                if ok:
                                    st.success("已更新。")
                                    st.rerun()
                                else:
                                    st.error(msg)

                with c2:
                    st.write("")
                    if st.button("🗑️ 删除", key=f"del_{i}", type="secondary"):
                        confirm = kb.delete_knowledge(title)
                        if confirm:
                            st.toast(f"已删除: {title}", icon="🗑️")
                            st.rerun()
                        else:
                            st.error("删除失败")
    
    st.caption(f"共计 {len(knowledge_list)} 条战法。")
