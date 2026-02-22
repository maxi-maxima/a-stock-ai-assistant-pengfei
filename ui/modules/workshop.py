import streamlit as st
import os
import pandas as pd
from core.code_gen import StrategyGenerator
from core.skill_registry import SkillRegistry  # 🔥


def render():
    st.header("🛠️ 技能工坊 (Skill Workshop)")
    st.markdown("在此通过 **自然语言** 编写新策略，并查看策略的 **实战表现**。")

    gen = StrategyGenerator()
    reg = SkillRegistry()  # 🔥

    tab1, tab2, tab3, tab4 = st.tabs([
        "⚡ Kimi 编写新策略",
        "📥 导入策略",
        "🗂️ 管理我的策略",
        "🏆 策略排行榜"
    ])

    with tab1:
        c1, c2 = st.columns([3, 1])
        strat_name = c1.text_input("策略英文名", placeholder="例如: kdj_buy")
        desc = st.text_area(
            "告诉 Kimi 你的逻辑",
            height=150,
            placeholder="例如：当 KDJ 金叉且收盘价站上 20 日均线时买入。"
        )

        if st.button("✨ 呼叫 Kimi 生成代码", type="primary", key="gen_code"):
            if not strat_name or not desc:
                st.error("请填写完整")
            else:
                with st.spinner("Kimi 正在编写..."):
                    code = gen.generate_code(desc)
                    st.session_state['generated_code'] = code
                    st.success("代码已生成，请核对。")

        if 'generated_code' in st.session_state:
            code_content = st.text_area(
                "Python 代码",
                value=st.session_state['generated_code'],
                height=300
            )
            c_test, c_save = st.columns([1, 1])
            if c_test.button("🧪 试跑", key="test_generated"):
                ok, err, result = gen.test_strategy(code_content)
                if ok:
                    st.success(f"试跑通过：{result}")
                else:
                    st.error(err)
            if c_save.button("💾 保存并激活", key="save_generated"):
                success, msg, saved_path, is_draft = gen.save_strategy(strat_name, code_content)
                if success:
                    st.success(f"策略已启用：{msg}")
                    del st.session_state['generated_code']
                    st.rerun()
                elif is_draft:
                    st.warning(msg)
                else:
                    st.error(msg)

    with tab2:
        st.subheader("导入策略")
        import_name = st.text_input("策略英文名", placeholder="例如: breakout_v1", key="import_name")
        import_code = st.text_area(
            "策略代码",
            height=300,
            key="import_code",
            placeholder="必须包含 def check(df): 并返回 (bool, str)"
        )
        c_test2, c_save2 = st.columns([1, 1])
        if c_test2.button("🧪 试跑", key="test_import"):
            ok, err, result = gen.test_strategy(import_code)
            if ok:
                st.success(f"试跑通过：{result}")
            else:
                st.error(err)
        if c_save2.button("📥 导入并保存", key="import_save"):
            if not import_name or not import_code:
                st.error("请填写策略名称和代码")
            else:
                success, msg, saved_path, is_draft = gen.save_strategy(import_name, import_code)
                if success:
                    st.success(f"策略已启用：{msg}")
                elif is_draft:
                    st.warning(msg)
                else:
                    st.error(msg)

    with tab3:
        st.subheader("已启用策略")
        if not os.path.exists("skills/strategies"):
            st.info("无")
        else:
            files = [f for f in os.listdir("skills/strategies") if f.endswith(".py")]
            if not files:
                st.info("无自定义策略")
            for f in files:
                with st.expander(f"📜 {f}"):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        with open(f"skills/strategies/{f}", "r", encoding="utf-8") as file:
                            st.code(file.read())
                    with c2:
                        if st.button("🗑️ 删除", key=f"del_{f}"):
                            gen.delete_strategy(f)
                            st.rerun()

        st.subheader("草稿策略")
        draft_dir = "skills/strategies_draft"
        draft_meta = gen.get_draft_meta()
        if not os.path.exists(draft_dir):
            st.info("无")
        else:
            draft_files = [f for f in os.listdir(draft_dir) if f.endswith(".py")]
            if not draft_files:
                st.info("无草稿策略")
            for f in draft_files:
                draft_path = os.path.join(draft_dir, f)
                with st.expander(f"📝 {f}"):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        meta = draft_meta.get(f, {})
                        if meta.get("error"):
                            st.error(f"校验失败原因：{meta.get('error')}")
                        if meta.get("updated_at"):
                            st.caption(f"更新时间：{meta.get('updated_at')}")
                        with open(draft_path, "r", encoding="utf-8") as file:
                            st.code(file.read())
                    with c2:
                        if st.button("✅ 启用", key=f"enable_{f}"):
                            try:
                                with open(draft_path, "r", encoding="utf-8") as file:
                                    code = file.read()
                            except Exception as e:
                                st.error(str(e))
                            else:
                                name = f.replace(".py", "")
                                success, msg, saved_path, is_draft = gen.save_strategy(name, code)
                                if success:
                                    try:
                                        os.remove(draft_path)
                                    except Exception:
                                        pass
                                    st.success(f"策略已启用：{msg}")
                                    st.rerun()
                                elif is_draft:
                                    st.warning(msg)
                                else:
                                    st.error(msg)
                        if st.button("🗑️ 删除", key=f"del_draft_{f}"):
                            try:
                                os.remove(draft_path)
                            except Exception as e:
                                st.error(str(e))
                            st.rerun()

    with tab4:
        st.subheader("🏆 策略优胜劣汰榜")
        st.caption("展示各策略在雷达扫描中的活跃度（未来将接入回测收益率）。")

        df = reg.get_leaderboard()
        if not df.empty:
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    "name": "策略名称",
                    "total_calls": st.column_config.ProgressColumn(
                        "累计命中次数",
                        format="%d",
                        min_value=0,
                        max_value=max(df['total_calls'])
                    ),
                    "last_used": "最近使用日期",
                    "last_params": "参数",
                    "hits": "实盘胜场(Todo)",
                    "avg_return": "平均收益(Todo)"
                },
                hide_index=True
            )
        else:
            st.info("暂无数据。快去【猎手雷达】多跑几次扫描吧！")
