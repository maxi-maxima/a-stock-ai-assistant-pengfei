import datetime
import json
import os
import sqlite3

from core.event_schema import validate_event
from core.logger import exception

from skills.risk_budget import max_drawdown


EVENT_BUS_PATH = "data/event_bus.jsonl"
TRADES_PATH = "data/trades.jsonl"


def _parse_ts(ts):
    if isinstance(ts, datetime.datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.datetime.fromisoformat(ts)
        except Exception:
            try:
                return datetime.datetime.fromisoformat(ts[:19])
            except Exception:
                return None
    return None


def load_event_bus(days=60, limit=None, return_meta=False):
    if not os.path.exists(EVENT_BUS_PATH):
        return ([], {"scanned": 0, "invalid": 0}) if return_meta else []
    cutoff = None
    if days is not None:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=int(days))
    out = []
    scanned = 0
    invalid = 0
    try:
        with open(EVENT_BUS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                scanned += 1
                ok, _ = validate_event(rec)
                if not ok:
                    invalid += 1
                    continue
                if cutoff:
                    ts = _parse_ts(rec.get("ts"))
                    if ts and ts < cutoff:
                        continue
                out.append(rec)
    except Exception as e:
        exception("metrics.load_event_bus_failed", e)
        return ([], {"scanned": scanned, "invalid": invalid}) if return_meta else []
    if limit and len(out) > limit:
        out = out[-limit:]
    if return_meta:
        return out, {"scanned": scanned, "invalid": invalid}
    return out


def load_trades(limit=2000):
    if not os.path.exists(TRADES_PATH):
        return []
    out = []
    try:
        with open(TRADES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception:
        return []
    if limit and len(out) > limit:
        out = out[-limit:]
    return out


def compute_kpis(events=None, trades=None):
    meta = {"scanned": 0, "invalid": 0}
    if events is None:
        try:
            events, meta = load_event_bus(return_meta=True)
        except Exception as e:
            exception("metrics.load_event_bus_failed", e)
            events = []
    else:
        meta = {"scanned": len(events), "invalid": 0}
    trades = trades if trades is not None else load_trades()

    decisions = [e for e in events if e.get("event") == "decision"]
    outcomes = [e for e in events if e.get("event") == "outcome"]
    decisions_by_id = {}
    for d in decisions:
        did = d.get("decision_id")
        if did:
            decisions_by_id[str(did)] = d

    pnl_list = []
    for e in outcomes:
        payload = e.get("payload", {}) if isinstance(e.get("payload", {}), dict) else {}
        pnl_pct = payload.get("pnl_pct")
        if pnl_pct is None:
            continue
        try:
            pnl_list.append(float(pnl_pct))
        except Exception:
            continue

    win_rate = (sum(1 for v in pnl_list if v > 0) / len(pnl_list)) if pnl_list else 0.0
    avg_pnl = (sum(pnl_list) / len(pnl_list)) if pnl_list else 0.0

    # environment strat stats (tag + strategy)
    tag_strategy = {}
    for e in outcomes:
        payload = e.get("payload", {}) if isinstance(e.get("payload", {}), dict) else {}
        pnl_pct = payload.get("pnl_pct")
        if pnl_pct is None:
            continue
        try:
            pnl_pct = float(pnl_pct)
        except Exception:
            continue
        did = payload.get("origin_decision_id") or e.get("decision_id")
        drec = decisions_by_id.get(str(did)) if did is not None else None
        if not drec:
            continue
        dp = drec.get("payload", {}) if isinstance(drec.get("payload", {}), dict) else {}
        tags = dp.get("context_tags") or []
        if not isinstance(tags, list):
            tags = []
        signal = dp.get("signal_source", {}) if isinstance(dp.get("signal_source", {}), dict) else {}
        strategies = []
        if signal.get("strategy"):
            strategies.append(str(signal.get("strategy")))
        if signal.get("strategies") and isinstance(signal.get("strategies"), list):
            strategies.extend([str(s) for s in signal.get("strategies") if s])
        if not strategies:
            strategies = ["unknown"]
        for tag in tags:
            tag = str(tag)
            if not tag:
                continue
            for strat in strategies:
                key = (tag, strat)
                bucket = tag_strategy.get(key, {"count": 0, "wins": 0, "pnl_sum": 0.0})
                bucket["count"] += 1
                if pnl_pct > 0:
                    bucket["wins"] += 1
                bucket["pnl_sum"] += pnl_pct
                tag_strategy[key] = bucket

    # policy overrides & action stats
    overrides = 0
    decision_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
    suggested_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
    tag_counts = {}
    for d in decisions:
        payload = d.get("payload", {}) if isinstance(d.get("payload", {}), dict) else {}
        suggested = str(payload.get("suggested_action") or "").upper()
        action = str(payload.get("action") or "").upper()
        if suggested and action and suggested != action:
            overrides += 1
        if action in decision_counts:
            decision_counts[action] += 1
        if suggested in suggested_counts:
            suggested_counts[suggested] += 1
        tags = payload.get("context_tags") or []
        if isinstance(tags, list):
            for t in tags:
                t = str(t)
                if not t:
                    continue
                tag_counts[t] = tag_counts.get(t, 0) + 1
    override_rate = (overrides / len(decisions)) if decisions else 0.0

    # equity & drawdown
    equity = []
    equity_curve = []
    for t in trades:
        if "equity" in t:
            try:
                eq = float(t.get("equity") or 0)
                equity.append(eq)
                equity_curve.append({"ts": t.get("ts"), "equity": eq})
            except Exception:
                pass
    mdd = max_drawdown(equity) if equity else 0.0
    last_equity = equity[-1] if equity else 0.0

    # drawdown segments
    drawdown_segments = []
    if equity_curve:
        peak = equity_curve[0]["equity"]
        peak_ts = equity_curve[0]["ts"]
        trough = peak
        trough_ts = peak_ts
        in_dd = False
        max_dd = 0.0
        for row in equity_curve[1:]:
            eq = row["equity"]
            ts = row["ts"]
            if eq >= peak:
                if in_dd:
                    drawdown_segments.append({
                        "start": peak_ts,
                        "end": ts,
                        "trough": trough_ts,
                        "max_drawdown": max_dd
                    })
                peak = eq
                peak_ts = ts
                trough = eq
                trough_ts = ts
                in_dd = False
                max_dd = 0.0
            else:
                in_dd = True
                dd = (eq / peak - 1.0) if peak else 0.0
                if dd < max_dd:
                    max_dd = dd
                    trough = eq
                    trough_ts = ts
        if in_dd:
            drawdown_segments.append({
                "start": peak_ts,
                "end": equity_curve[-1]["ts"],
                "trough": trough_ts,
                "max_drawdown": max_dd
            })

    # win/loss streak
    streak = 0
    last_sign = 0
    for v in pnl_list[::-1]:
        sign = 1 if v > 0 else (-1 if v < 0 else 0)
        if last_sign == 0:
            last_sign = sign
        if sign == 0 or sign != last_sign:
            break
        streak += 1
    streak_type = "win" if last_sign > 0 else ("loss" if last_sign < 0 else "flat")

    # tag-strategy stats table (top by count)
    tag_strategy_rows = []
    for (tag, strat), v in tag_strategy.items():
        count = v.get("count", 0) or 0
        if count <= 0:
            continue
        win = v.get("wins", 0) or 0
        pnl_sum = v.get("pnl_sum", 0.0) or 0.0
        tag_strategy_rows.append({
            "tag": tag,
            "strategy": strat,
            "count": count,
            "win_rate": win / count if count else 0.0,
            "avg_pnl_pct": pnl_sum / count if count else 0.0
        })
    tag_strategy_rows = sorted(tag_strategy_rows, key=lambda x: (x["count"], x["avg_pnl_pct"]), reverse=True)[:30]

    # last 30 days pnl distribution
    pnl_30d = []
    cutoff_30d = datetime.datetime.now() - datetime.timedelta(days=30)
    for e in outcomes:
        ts = _parse_ts(e.get("ts"))
        if ts and ts < cutoff_30d:
            continue
        payload = e.get("payload", {}) if isinstance(e.get("payload", {}), dict) else {}
        pnl_pct = payload.get("pnl_pct")
        if pnl_pct is None:
            continue
        try:
            pnl_30d.append(float(pnl_pct))
        except Exception:
            continue

    # top drawdowns by depth
    drawdown_segments = sorted(drawdown_segments, key=lambda x: x.get("max_drawdown", 0), reverse=False)[:5]

    return {
        "decisions": len(decisions),
        "outcomes": len(outcomes),
        "win_rate": win_rate,
        "avg_pnl_pct": avg_pnl,
        "override_rate": override_rate,
        "override_count": overrides,
        "decision_counts": decision_counts,
        "suggested_counts": suggested_counts,
        "tag_counts": tag_counts,
        "tag_strategy_stats": tag_strategy_rows,
        "streak": {"type": streak_type, "count": streak},
        "max_drawdown": mdd,
        "last_equity": last_equity,
        "recent_outcomes": outcomes[-10:] if outcomes else [],
        "equity_curve": equity_curve,
        "pnl_30d": pnl_30d,
        "drawdown_segments": drawdown_segments,
        "event_bus_scanned": meta.get("scanned", 0),
        "event_bus_invalid": meta.get("invalid", 0)
    }


def _filter_by_days(records, days):
    if not days:
        return records
    try:
        days = int(days)
    except Exception:
        return records
    if days <= 0:
        return records
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    out = []
    for r in records:
        ts = _parse_ts(r.get("ts")) if isinstance(r, dict) else None
        if ts is None or ts >= cutoff:
            out.append(r)
    return out


def _get_strategy_from_signal(signal_source):
    if not isinstance(signal_source, dict):
        return None
    strat = signal_source.get("strategy")
    if isinstance(strat, str) and strat.strip():
        return strat.strip()
    strategies = signal_source.get("strategies")
    if isinstance(strategies, list):
        for s in strategies:
            if isinstance(s, str) and s.strip():
                return s.strip()
    if isinstance(strategies, str) and strategies.strip():
        return strategies.strip()
    votes = signal_source.get("votes") or signal_source.get("strategy_votes")
    if isinstance(votes, list):
        best_name = None
        best_weight = None
        for v in votes:
            if not isinstance(v, dict):
                continue
            name = v.get("strategy") or v.get("name")
            w = v.get("weight", 0)
            try:
                w = float(w)
            except Exception:
                w = 0.0
            if name and (best_weight is None or w > best_weight):
                best_name = name
                best_weight = w
        if best_name:
            return best_name
    return None


def _load_skill_stats(db_path):
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT name, total_calls, hits, avg_return, scan_hits, reward_sum, reward_count, last_reward, last_reward_ts "
            "FROM strategy_stats"
        ).fetchall()
        conn.close()
    except Exception:
        return None
    stats = []
    for r in rows:
        stats.append({
            "name": r[0],
            "total_calls": r[1] or 0,
            "hits": r[2] or 0,
            "avg_return": r[3] or 0.0,
            "scan_hits": r[4] or 0,
            "reward_sum": r[5] or 0.0,
            "reward_count": r[6] or 0,
            "last_reward": r[7] or 0.0,
            "last_reward_ts": r[8] or ""
        })
    return stats


def compute_loop_health(days=60, limit=None):
    events = load_event_bus(days=days, limit=limit)
    trades = load_trades(limit=limit or 2000)
    trades = _filter_by_days(trades, days)

    decisions = [e for e in events if isinstance(e, dict) and e.get("event") == "decision"]
    executions = [e for e in events if isinstance(e, dict) and e.get("event") == "execution"]
    outcomes = [e for e in events if isinstance(e, dict) and e.get("event") == "outcome"]

    decision_ids = set(d.get("decision_id") for d in decisions if d.get("decision_id"))
    exec_ids = set(e.get("decision_id") for e in executions if e.get("decision_id"))
    out_ids = set(o.get("decision_id") for o in outcomes if o.get("decision_id"))

    decisions_no_exec = sum(1 for d in decisions if d.get("decision_id") and d.get("decision_id") not in exec_ids)
    decisions_no_out = sum(1 for d in decisions if d.get("decision_id") and d.get("decision_id") not in out_ids)

    exec_missing_id = sum(1 for e in executions if not e.get("decision_id"))
    out_missing_id = sum(1 for o in outcomes if not o.get("decision_id"))
    out_orphan = sum(1 for o in outcomes if o.get("decision_id") and o.get("decision_id") not in decision_ids)

    out_with_strategy = 0
    for o in outcomes:
        payload = o.get("payload", {}) if isinstance(o.get("payload", {}), dict) else {}
        strat = _get_strategy_from_signal(payload.get("signal_source"))
        if strat:
            out_with_strategy += 1

    buys = [t for t in trades if isinstance(t, dict) and t.get("action") == "BUY"]
    sells = [t for t in trades if isinstance(t, dict) and t.get("action") == "SELL"]
    buy_missing_id = sum(1 for t in buys if not t.get("decision_id"))
    sell_missing_origin = sum(1 for t in sells if not (t.get("origin_decision_id") or t.get("decision_id")))
    sell_with_strategy = 0
    for t in sells:
        strat = _get_strategy_from_signal(t.get("signal_source"))
        if strat:
            sell_with_strategy += 1
    trade_total = len(trades)
    trade_missing_decision = buy_missing_id + sell_missing_origin
    trade_decision_rate = (trade_total - trade_missing_decision) / trade_total if trade_total else 0.0

    skill_stats = _load_skill_stats("data/skills.db")
    if skill_stats is None:
        skill_summary = {"strategies": 0, "rewarded": 0}
    else:
        skill_summary = {
            "strategies": len(skill_stats),
            "rewarded": sum(1 for s in skill_stats if (s.get("reward_count") or 0) > 0)
        }

    bias_path = "data/feature_weight_bias.json"
    bias_ts = ""
    if os.path.exists(bias_path):
        try:
            with open(bias_path, "r", encoding="utf-8") as f:
                bias = json.load(f)
            if isinstance(bias, dict):
                bias_ts = str(bias.get("updated_at") or "")
        except Exception:
            bias_ts = ""

    override_path = "data/threshold_overrides.json"
    override_ts = ""
    if os.path.exists(override_path):
        try:
            with open(override_path, "r", encoding="utf-8") as f:
                ov = json.load(f)
            if isinstance(ov, dict):
                override_ts = str(ov.get("updated_at") or "")
        except Exception:
            override_ts = ""

    decisions_n = len(decisions)
    executions_n = len(executions)
    outcomes_n = len(outcomes)
    outcome_attr_rate = (out_with_strategy / outcomes_n) if outcomes_n else 0.0
    sell_attr_rate = (sell_with_strategy / len(sells)) if sells else 0.0
    exec_rate = (executions_n / decisions_n) if decisions_n else 0.0
    outcome_rate = (outcomes_n / decisions_n) if decisions_n else 0.0
    decision_event_missing = 1 if (trade_total > 0 and decisions_n == 0) else 0

    score = 100.0
    if decisions_n:
        score -= 40.0 * (decisions_no_exec / decisions_n)
        score -= 30.0 * (decisions_no_out / decisions_n)
    if executions_n:
        score -= 10.0 * (exec_missing_id / executions_n)
    if outcomes_n:
        score -= 10.0 * (out_missing_id / outcomes_n)
        score -= 10.0 * (out_orphan / outcomes_n)
        score -= 20.0 * (1.0 - outcome_attr_rate)
    if len(sells):
        score -= 10.0 * (1.0 - sell_attr_rate)
    if trade_total:
        score -= 15.0 * (trade_missing_decision / trade_total)
        if decisions_n == 0:
            score -= 20.0
    score = max(0.0, min(100.0, score))
    if score >= 85:
        status = "OK"
    elif score >= 70:
        status = "WARN"
    else:
        status = "FAIL"

    return {
        "decisions": len(decisions),
        "executions": len(executions),
        "outcomes": len(outcomes),
        "decisions_no_execution": decisions_no_exec,
        "decisions_no_outcome": decisions_no_out,
        "execution_missing_id": exec_missing_id,
        "outcome_missing_id": out_missing_id,
        "outcome_orphan": out_orphan,
        "outcome_strategy_attrib": out_with_strategy,
        "trade_buys": len(buys),
        "trade_sells": len(sells),
        "buy_missing_decision_id": buy_missing_id,
        "sell_missing_origin_id": sell_missing_origin,
        "sell_strategy_attrib": sell_with_strategy,
        "trade_total": trade_total,
        "trade_missing_decision_id": trade_missing_decision,
        "trade_decision_rate": trade_decision_rate,
        "decision_event_missing": decision_event_missing,
        "skill_summary": skill_summary,
        "bias_updated_at": bias_ts,
        "threshold_overrides_updated_at": override_ts,
        "health_score": score,
        "health_status": status,
        "execution_rate": exec_rate,
        "outcome_rate": outcome_rate,
        "outcome_strategy_attrib_rate": outcome_attr_rate,
        "sell_strategy_attrib_rate": sell_attr_rate
    }
