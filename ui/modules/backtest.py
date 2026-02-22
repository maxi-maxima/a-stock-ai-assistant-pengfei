import io
import json
import zipfile

import pandas as pd
import streamlit as st

from skills.scanner import MarketScanner
from core.learning_log import log_event
from core.skill_registry import SkillRegistry


def _parse_codes(text):
    if not text:
        return []
    for sep in ["，", ";", "；", "\n", " "]:
        text = text.replace(sep, ",")
    parts = [p.strip().upper() for p in text.split(",") if p.strip()]
    seen = set()
    out = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _parse_weights(text):
    if not text:
        return []
    for sep in ["，", ";", "；", "\n", " "]:
        text = text.replace(sep, ",")
    vals = []
    for p in text.split(","):
        if p.strip():
            try:
                vals.append(float(p))
            except Exception:
                pass
    return vals


def _build_zip_file(file_map):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in file_map.items():
            if content is None:
                continue
            zf.writestr(name, content)
    buf.seek(0)
    return buf


def render(backtester):
    st.header("⏳ 时光回测 (Strategy Backtester)")

    scanner = MarketScanner()
    strat_list = scanner.get_strategy_list()

    tab_single, tab_multi = st.tabs(["单标的回测", "多标的回测"])

    with tab_single:
        with st.container():
            c1, c2, c3 = st.columns([1, 1, 2])
            code = c1.text_input("回测标的", "000001.SZ")
            strategy = c2.selectbox("选择策略", strat_list)
            backtest_days = c3.slider("回溯历史天数", 100, 1000, 365)

        st.divider()

        with st.expander("✨ AI 策略参数寻优 (Auto-Optimizer)", expanded=False):
            c1, c2 = st.columns(2)
            opt_mode = c1.selectbox("优化模式", ["简单", "Walk-Forward"])
            window_count = c2.slider("Walk-Forward 窗口数", 2, 6, 3)
            opt_exec_label = st.selectbox("Execution Model", ["Next Open", "Close"], key="opt_exec")
            opt_execution = "next_open" if opt_exec_label == "Next Open" else "close"
            oc1, oc2, oc3, oc4 = st.columns(4)
            opt_commission = oc1.number_input("Commission (Optimizer)", 0.0, 0.01, 0.0003, 0.0001, format="%.4f", key="opt_commission")
            opt_slippage = oc2.number_input("Slippage (Optimizer)", 0.0, 0.01, 0.0005, 0.0001, format="%.4f", key="opt_slippage")
            opt_stamp_duty = oc3.number_input("Stamp Duty (Optimizer)", 0.0, 0.01, 0.001, 0.0001, format="%.4f", key="opt_stamp_duty")
            opt_lot_size = oc4.number_input("Lot Size (Optimizer)", 1, 1000, 100, 10, key="opt_lot_size")
            st.caption("不知道设多少止盈止损？让 AI 帮您跑一遍穷举测试，找到收益率最高的组合。")
            if st.button("⚡ 启动 AI 寻优计算"):
                with st.spinner("AI 正在疯狂计算参数组合..."):
                    df_opt = scanner.data_skill.get_history(code, days=backtest_days)
                    if df_opt.empty:
                        st.error("数据不足")
                    else:
                        opt_context = backtester.collect_system_params(code)
                        best_params = backtester.optimize(
                            df_opt,
                            strategy,
                            mode="walk_forward" if opt_mode == "Walk-Forward" else "simple",
                            window_count=window_count,
                            execution=opt_execution,
                            commission=opt_commission,
                            slippage=opt_slippage,
                            stamp_duty=opt_stamp_duty,
                            lot_size=int(opt_lot_size),
                            context=opt_context
                        )
                        if best_params:
                            top1 = best_params[0]
                            train_ret = top1.get('ret', 0)
                            test_ret = top1.get('test_ret', 0)
                            st.success(f"🏆 发现最佳参数！训练收益 {train_ret:.2f}% | 测试收益 {test_ret:.2f}%")

                            st.session_state['opt_tp'] = top1['tp'] * 100
                            st.session_state['opt_sl'] = top1['sl'] * 100
                            st.session_state['opt_days'] = top1['days']
                            backtester.save_best_params(strategy, top1)
                            try:
                                registry = SkillRegistry()
                                strategy_code = backtester._get_strategy_code(strategy)
                                reward = float(top1.get("score", test_ret or train_ret or 0) or 0) / 100.0
                                registry.update_reward(strategy_code, reward, source="backtest_opt")
                            except Exception:
                                pass

                            df_best = pd.DataFrame(best_params)
                            df_best['tp'] = df_best['tp'].apply(lambda x: f"{x*100:.0f}%")
                            df_best['sl'] = df_best['sl'].apply(lambda x: f"{x*100:.0f}%")
                            df_best['ret'] = df_best['ret'].apply(lambda x: f"{x:.2f}%")
                            if 'test_ret' in df_best.columns:
                                df_best['test_ret'] = df_best['test_ret'].apply(lambda x: f"{x:.2f}%")
                            if 'test_dd' in df_best.columns:
                                df_best['test_dd'] = df_best['test_dd'].apply(lambda x: f"{x*100:.2f}%")
                            if 'score' in df_best.columns:
                                df_best['score'] = df_best['score'].apply(lambda x: f"{x:.2f}")
                            if 'win' in df_best.columns:
                                df_best['win'] = df_best['win'].apply(lambda x: f"{x:.1f}%")

                            st.dataframe(
                                df_best,
                                column_config={
                                    "tp": "止盈", "sl": "止损", "days": "持仓天数",
                                    "ret": "训练收益", "test_ret": "测试收益",
                                    "test_dd": "测试最大回撤", "score": "综合评分",
                                    "win": "胜率", "trades": "交易数"
                                },
                                use_container_width=True
                            )
                        else:
                            st.warning("该策略在所有参数组合下均无交易，可能是不适合该股票。")

        st.subheader("⚙️ 运行回测")

        saved = backtester.get_saved_params(strategy)
        def_tp = st.session_state.get('opt_tp', (saved.get("tp") or 0.1) * 100)
        def_sl = st.session_state.get('opt_sl', (saved.get("sl") or 0.05) * 100)
        def_days = st.session_state.get('opt_days', int(saved.get("days") or 20))

        col_a, col_b, col_c = st.columns(3)
        tp_pct = col_a.number_input("🎯 止盈幅度 (%)", 1.0, 500.0, float(def_tp), 1.0)
        sl_pct = col_b.number_input("🛡️ 止损幅度 (%)", 1.0, 50.0, float(def_sl), 0.5)
        max_days = col_c.number_input("⏳ 平盘周期 (天)", 1, 365, int(def_days))

        col_d, col_e = st.columns(2)
        position_pct = col_d.slider("仓位比例", 0.1, 1.0, 1.0, 0.1)
        exec_label = col_e.selectbox("成交模型", ["次日开盘", "当日收盘"])
        execution = "next_open" if exec_label == "次日开盘" else "close"

        with st.expander("Trading Costs", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            commission = c1.number_input("Commission", 0.0, 0.01, 0.0003, 0.0001, format="%.4f")
            slippage = c2.number_input("Slippage", 0.0, 0.01, 0.0005, 0.0001, format="%.4f")
            stamp_duty = c3.number_input("Stamp Duty", 0.0, 0.01, 0.001, 0.0001, format="%.4f")
            lot_size = c4.number_input("Lot Size", 1, 1000, 100, 10)

        bench_label = st.selectbox("Benchmark", ["None", "000001.SH (SSE)", "399300.SZ (CSI300)"])
        bench_code = None
        if bench_label.startswith("000001"):
            bench_code = "000001.SH"
        elif bench_label.startswith("399300"):
            bench_code = "399300.SZ"


        if st.button("🚀 开始回测 (基于上方参数)", type="primary"):
            with st.spinner("回测中..."):
                df = scanner.data_skill.get_history(code, days=backtest_days)
                if df.empty:
                    st.error("数据不足")
                    return

                res = backtester.run(
                    df,
                    strategy,
                    take_profit=tp_pct/100,
                    stop_loss=sl_pct/100,
                    max_days=int(max_days),
                    position_pct=position_pct,
                    execution=execution,
                    commission=commission,
                    slippage=slippage,
                    stamp_duty=stamp_duty,
                    lot_size=int(lot_size)
                )

                if "error" in res:
                    st.error(res['error'])
                    return

                ret = res['return_pct']

                bench_df = None
                bench_ret = None
                if bench_code:
                    bench_df = scanner.data_skill.get_history(bench_code, days=backtest_days)
                    if not bench_df.empty:
                        try:
                            start_date = df.iloc[30]['date']
                            bench_df = bench_df[bench_df['date'] >= start_date]
                        except Exception:
                            pass
                        if len(bench_df) >= 2:
                            bench_ret = (bench_df.iloc[-1]['close'] / bench_df.iloc[0]['close'] - 1) * 100

                st.divider()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("策略收益", f"{ret:.2f}%", delta=f"{res['final']-res['initial']:.0f}")
                m2.metric("年化收益", f"{res.get('annualized_return', 0):.2f}%")
                m3.metric("最大回撤", f"{(res.get('max_drawdown', 0) or 0)*100:.2f}%")
                m4.metric("夏普比率", f"{res.get('sharpe', 0):.2f}")

                sell_trades = len([t for t in res['trades'] if t.get("action") == "SELL"])
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("交易次数", f"{sell_trades}")
                m6.metric("胜率", f"{res.get('win_rate', 0):.1f}%")
                pf = res.get("profit_factor", 0)
                m7.metric("盈亏比", f"{pf:.2f}" if pf != float("inf") else "INF")
                m8.metric("平均持仓", f"{res.get('avg_hold_days', 0):.1f}天")

                m9, m10, m11, m12 = st.columns(4)
                m9.metric("最大连亏", f"{res.get('max_consecutive_losses', 0)}")
                m10.metric("持仓占用", f"{res.get('exposure', 0)*100:.1f}%")
                m11.metric("风险等级", res.get("risk_level", "N/A"))
                m12.metric("评分", f"{res.get('score', 0):.2f}")

                b1, b2, b3 = st.columns(3)
                b1.metric("基准收益", f"{res.get('benchmark_return_pct', 0):.2f}%")
                b2.metric("超额收益", f"{res.get('excess_return_pct', 0):.2f}%")
                b3.metric("基准年化", f"{res.get('benchmark_annualized_return', 0):.2f}%")

                dq = res.get("data_quality", {}) if isinstance(res.get("data_quality", {}), dict) else {}
                if dq:
                    st.caption(f"数据质量: rows={dq.get('rows', 0)} dup_dates={dq.get('dup_dates', 0)}")

                if res.get("drawdown_start"):
                    st.caption(f"最大回撤区间: {res.get('drawdown_start')} → {res.get('drawdown_end')}")

                try:
                    log_event("backtest_run", {
                        "code": code,
                        "strategy": strategy,
                        "take_profit": tp_pct/100,
                        "stop_loss": sl_pct/100,
                        "max_days": int(max_days),
                        "position_pct": position_pct,
                        "execution": execution,
                        "return_pct": ret,
                        "score": res.get("score"),
                        "win_rate": res.get("win_rate"),
                        "max_drawdown": res.get("max_drawdown"),
                        "sharpe": res.get("sharpe")
                    })
                except Exception:
                    pass
                try:
                    registry = SkillRegistry()
                    strategy_code = backtester._get_strategy_code(strategy)
                    reward = float(res.get("score", ret) or 0) / 100.0
                    registry.update_reward(strategy_code, reward, source="backtest_run")
                except Exception:
                    pass

                eq_df = res.get("equity_curve")
                trades_df = pd.DataFrame(res['trades']) if res.get('trades') else pd.DataFrame()

                st.plotly_chart(backtester.plot_result(df, res, benchmark_df=bench_df), use_container_width=True)

                eq_csv = None
                if eq_df is not None and not eq_df.empty:
                    eq_csv = eq_df.to_csv(index=False)
                    st.download_button("Download Equity Curve CSV", eq_csv, file_name=f"{code}_equity_curve.csv", mime="text/csv")

                trades_csv = None
                if not trades_df.empty:
                    trades_csv = trades_df.to_csv(index=False)
                    st.download_button("Download Trades CSV", trades_csv, file_name=f"{code}_trades.csv", mime="text/csv")

                report_summary = {
                    "code": code,
                    "strategy": strategy,
                    "backtest_days": int(backtest_days),
                    "params": {
                        "take_profit": float(tp_pct / 100),
                        "stop_loss": float(sl_pct / 100),
                        "max_days": int(max_days),
                        "position_pct": float(position_pct),
                        "execution": execution,
                        "commission": float(commission),
                        "slippage": float(slippage),
                        "stamp_duty": float(stamp_duty),
                        "lot_size": int(lot_size)
                    },
                    "metrics": {
                        "return_pct": float(ret),
                        "annualized_return": float(res.get("annualized_return", 0)),
                        "score": float(res.get("score", 0)),
                        "max_drawdown": float(res.get("max_drawdown", 0) or 0),
                        "sharpe": float(res.get("sharpe", 0)),
                        "win_rate": float(res.get("win_rate", 0)),
                        "profit_factor": float(res.get("profit_factor", 0)) if res.get("profit_factor", 0) != float("inf") else "INF",
                        "avg_hold_days": float(res.get("avg_hold_days", 0)),
                        "max_consecutive_losses": int(res.get("max_consecutive_losses", 0)),
                        "exposure": float(res.get("exposure", 0)),
                        "risk_level": res.get("risk_level", "N/A"),
                        "benchmark_return_pct": float(res.get("benchmark_return_pct", 0)),
                        "benchmark_annualized_return": float(res.get("benchmark_annualized_return", 0)),
                        "excess_return_pct": float(res.get("excess_return_pct", 0))
                    },
                    "benchmark": {
                        "code": bench_code,
                        "return_pct": float(bench_ret) if bench_ret is not None else None
                    },
                    "generated_at": pd.Timestamp.now().isoformat()
                }
                report_files = {
                    "summary.json": json.dumps(report_summary, ensure_ascii=True, indent=2),
                    "equity.csv": eq_csv,
                    "trades.csv": trades_csv
                }
                report_zip = _build_zip_file(report_files)
                st.download_button("Download Full Report", report_zip, file_name=f"{code}_report.zip", mime="application/zip")

                with st.expander("📝 交易明细"):
                    if not trades_df.empty:
                        st.dataframe(trades_df, use_container_width=True)
                    else:
                        st.info("无交易记录")

    with tab_multi:
        st.caption("多标的回测会逐个回测并汇总，属于策略稳定性观察。")
        codes_text = st.text_area("标的列表 (逗号/换行)", "000001.SZ, 600519.SH")
        m1, m2 = st.columns(2)
        strategy_m = m1.selectbox("策略", strat_list, key="multi_strategy")
        backtest_days_m = m2.slider("回溯历史天数", 100, 1000, 365, key="multi_days")

        col_a, col_b, col_c = st.columns(3)
        tp_pct = col_a.number_input("止盈幅度 (%)", 1.0, 500.0, 10.0, 1.0, key="multi_tp")
        sl_pct = col_b.number_input("止损幅度 (%)", 1.0, 50.0, 5.0, 0.5, key="multi_sl")
        max_days = col_c.number_input("平盘周期 (天)", 1, 365, 20, key="multi_days_hold")

        col_d, col_e = st.columns(2)
        position_pct = col_d.slider("仓位比例", 0.1, 1.0, 1.0, 0.1, key="multi_pos")
        exec_label = col_e.selectbox("成交模型", ["次日开盘", "当日收盘"], key="multi_exec")
        execution = "next_open" if exec_label == "次日开盘" else "close"

        with st.expander("Trading Costs (Multi)", expanded=False):
            c1m, c2m, c3m, c4m = st.columns(4)
            commission_m = c1m.number_input("Commission", 0.0, 0.01, 0.0003, 0.0001, format="%.4f", key="multi_comm")
            slippage_m = c2m.number_input("Slippage", 0.0, 0.01, 0.0005, 0.0001, format="%.4f", key="multi_slip")
            stamp_duty_m = c3m.number_input("Stamp Duty", 0.0, 0.01, 0.001, 0.0001, format="%.4f", key="multi_duty")
            lot_size_m = c4m.number_input("Lot Size", 1, 1000, 100, 10, key="multi_lot")

        weight_mode = st.selectbox("Weight Mode", ["Equal Weight", "Custom Weights"], key="multi_weight_mode")
        weights_text = ""
        if weight_mode == "Custom Weights":
            weights_text = st.text_input("Weights (comma separated)", "", key="multi_weights")

        bench_label_m = st.selectbox("Benchmark", ["None", "000001.SH (SSE)", "399300.SZ (CSI300)"], key="multi_bench")
        bench_code_m = None
        if bench_label_m.startswith("000001"):
            bench_code_m = "000001.SH"
        elif bench_label_m.startswith("399300"):
            bench_code_m = "399300.SZ"

        if st.button("🚀 开始多标的回测"):
            codes = _parse_codes(codes_text)
            if not codes:
                st.warning("请先输入标的列表。")
            else:
                weights = _parse_weights(weights_text) if weight_mode == "Custom Weights" else []
                if weight_mode == "Custom Weights" and len(weights) != len(codes):
                    st.warning("Weights count mismatch; using equal weights.")
                    weights = []
                rows = []
                equity_curves = []
                equity_weights = []
                for idx, c in enumerate(codes):
                    weight_val = float(weights[idx]) if weights and idx < len(weights) else 1.0
                    df = scanner.data_skill.get_history(c, days=backtest_days_m)
                    if df.empty:
                        rows.append({"code": c, "weight": weight_val, "error": "数据不足"})
                        continue
                    res = backtester.run(
                        df,
                        strategy_m,
                        take_profit=tp_pct/100,
                        stop_loss=sl_pct/100,
                        max_days=int(max_days),
                        position_pct=position_pct,
                        execution=execution,
                        commission=commission_m,
                        slippage=slippage_m,
                        stamp_duty=stamp_duty_m,
                        lot_size=int(lot_size_m)
                    )
                    if "error" in res:
                        rows.append({"code": c, "weight": weight_val, "error": res.get("error")})
                        continue
                    eq_df = res.get("equity_curve")
                    eq_norm = backtester.normalize_equity_curve(eq_df)
                    if eq_norm is not None and not eq_norm.empty:
                        equity_curves.append(eq_norm)
                        equity_weights.append(weight_val)
                    sell_trades = len([t for t in res.get("trades", []) if t.get("action") == "SELL"])
                    rows.append({
                        "code": c,
                        "weight": weight_val,
                        "return_pct": res.get("return_pct", 0),
                        "benchmark_return_pct": res.get("benchmark_return_pct", 0),
                        "excess_return_pct": res.get("excess_return_pct", 0),
                        "annualized": res.get("annualized_return", 0),
                        "max_dd": res.get("max_drawdown", 0),
                        "sharpe": res.get("sharpe", 0),
                        "win_rate": res.get("win_rate", 0),
                        "trades": sell_trades
                    })

                df_rows = pd.DataFrame(rows)
                st.dataframe(df_rows, use_container_width=True)
                summary_csv = df_rows.to_csv(index=False) if not df_rows.empty else None
                if summary_csv:
                    st.download_button("Download Summary CSV", summary_csv, file_name="multi_summary.csv", mime="text/csv")

                portfolio = None
                ok_rows = [r for r in rows if "error" not in r]
                if ok_rows:
                    avg_ret = sum(r.get("return_pct", 0) for r in ok_rows) / len(ok_rows)
                    avg_excess = sum(r.get("excess_return_pct", 0) for r in ok_rows) / len(ok_rows)
                    avg_ann = sum(r.get("annualized", 0) for r in ok_rows) / len(ok_rows)
                    avg_dd = sum(r.get("max_dd", 0) for r in ok_rows) / len(ok_rows)
                    avg_sh = sum(r.get("sharpe", 0) for r in ok_rows) / len(ok_rows)
                    st.caption(f"平均收益: {avg_ret:.2f}% | 平均超额: {avg_excess:.2f}% | 平均年化: {avg_ann:.2f}% | 平均回撤: {abs(avg_dd)*100:.2f}% | 平均夏普: {avg_sh:.2f}")
                    if equity_curves:
                        portfolio = backtester.combine_equity_curves(equity_curves, weights=equity_weights, base_value=1.0)
                        if portfolio is not None and not portfolio.empty:
                            if weight_mode == "Custom Weights" and equity_weights:
                                st.caption("Portfolio curve uses custom weights.")
                            else:
                                st.caption("Portfolio curve uses equal-weighted normalized equity.")
                            pm = backtester.compute_metrics_from_equity_curve(portfolio, base_capital=1.0)
                            p1, p2, p3, p4 = st.columns(4)
                            p1.metric("Portfolio Return", f"{pm.get('return_pct', 0):.2f}%")
                            p2.metric("Annualized", f"{pm.get('annualized_return', 0):.2f}%")
                            p3.metric("Max Drawdown", f"{(pm.get('max_drawdown', 0) or 0)*100:.2f}%")
                            p4.metric("Sharpe", f"{pm.get('sharpe', 0):.2f}")

                            bench_df = None
                            if bench_code_m:
                                bench_df = scanner.data_skill.get_history(bench_code_m, days=backtest_days_m)
                                if bench_df is not None and not bench_df.empty:
                                    try:
                                        start_date = portfolio.iloc[0]["date"]
                                        bench_df = bench_df[bench_df["date"] >= start_date]
                                    except Exception:
                                        pass

                            fig = backtester.plot_equity_curve(portfolio, benchmark_df=bench_df, title="Portfolio Equity")
                            if fig is not None:
                                st.plotly_chart(fig, use_container_width=True)

                            port_csv = portfolio.to_csv(index=False)
                            st.download_button("Download Portfolio Equity CSV", port_csv, file_name="portfolio_equity.csv", mime="text/csv")

                if summary_csv:
                    report_summary = {
                        "codes": codes,
                        "weights_input": weights if weight_mode == "Custom Weights" else "equal",
                        "weights_used": equity_weights,
                        "strategy": strategy_m,
                        "backtest_days": int(backtest_days_m),
                        "params": {
                            "take_profit": float(tp_pct / 100),
                            "stop_loss": float(sl_pct / 100),
                            "max_days": int(max_days),
                            "position_pct": float(position_pct),
                            "execution": execution,
                            "commission": float(commission_m),
                            "slippage": float(slippage_m),
                            "stamp_duty": float(stamp_duty_m),
                            "lot_size": int(lot_size_m)
                        },
                        "benchmark": {
                            "code": bench_code_m
                        },
                        "generated_at": pd.Timestamp.now().isoformat()
                    }
                    report_files = {
                        "summary.csv": summary_csv,
                        "settings.json": json.dumps(report_summary, ensure_ascii=True, indent=2)
                    }
                    if portfolio is not None and not portfolio.empty:
                        report_files["portfolio_equity.csv"] = portfolio.to_csv(index=False)
                    report_zip = _build_zip_file(report_files)
                    st.download_button("Download Full Report (Multi)", report_zip, file_name="multi_report.zip", mime="application/zip")
