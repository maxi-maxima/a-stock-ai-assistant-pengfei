def _translate_status(value):
    mapping = {
        "active": "启用",
        "watch": "观察",
        "disabled": "停用",
        "open": "持有中",
        "closed": "已结束",
    }
    key = str(value or "").strip().lower()
    return mapping.get(key, str(value or ""))


def _format_float(value, digits=4):
    try:
        return round(float(value), digits)
    except Exception:
        return value


def _rename_rows(rows, column_map, status_keys=None, float_keys=None):
    out = []
    status_keys = set(status_keys or [])
    float_keys = set(float_keys or [])
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        new_row = {}
        for old_key, new_key in column_map.items():
            value = row.get(old_key)
            if old_key in status_keys:
                value = _translate_status(value)
            elif old_key in float_keys:
                value = _format_float(value)
            new_row[new_key] = value
        out.append(new_row)
    return out


def _format_strategy_rows(rows):
    return _rename_rows(
        rows,
        {
            "strategy_id": "策略编号",
            "status": "状态",
            "weight": "当前权重",
            "hold_days": "持有天数",
            "calls": "调用次数",
            "buys": "买入次数",
            "closed_trades": "已完成交易数",
            "wins": "盈利次数",
            "avg_realized_pnl": "平均已实现收益率",
            "last_realized_pnl": "最近一次收益率",
            "updated_at": "更新时间",
        },
        status_keys={"status"},
        float_keys={"weight", "avg_realized_pnl", "last_realized_pnl"},
    )


def _format_position_rows(rows):
    return _rename_rows(
        rows,
        {
            "decision_id": "决策编号",
            "code": "股票代码",
            "strategy_id": "策略编号",
            "buy_date": "买入日期",
            "planned_exit_date": "计划平仓日",
            "hold_days": "持有天数",
            "buy_price": "买入价格",
            "shares": "股数",
            "status": "状态",
            "created_at": "创建时间",
        },
        status_keys={"status"},
        float_keys={"buy_price"},
    )


def _format_report_rows(rows):
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "交易日期": row.get("trade_date"),
                "新开仓数": row.get("opened_count"),
                "已平仓数": row.get("closed_count"),
                "调权次数": row.get("reward_updates"),
                "已实现盈亏": _format_float(row.get("realized_pnl_sum"), digits=2),
                "本轮策略": row.get("chosen_strategy_id"),
                "本轮股票": row.get("selected_code"),
                "执行结果": "成功" if bool(row.get("ok")) else "失败",
            }
        )
    return out


def _parse_task_query_summary(text):
    mapping = {
        "TaskName": "任务名称",
        "Next Run Time": "下次运行时间",
        "Last Run Time": "上次运行时间",
        "Last Result": "最近执行结果",
        "Status": "任务状态",
        "Schedule Type": "调度类型",
        "Start Time": "开始时间",
    }
    rows = []
    for line in str(text or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in mapping:
            rows.append({"项目": mapping[key], "内容": value})
    return rows
