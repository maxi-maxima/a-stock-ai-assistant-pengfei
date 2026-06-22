#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Closed-loop health check for trading system.
"""
import argparse
import datetime
import json
import os
import sqlite3


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


def _load_jsonl(path, limit=None):
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    if limit and len(out) > limit:
        out = out[-limit:]
    return out


def _filter_days(recs, days):
    if not days:
        return recs
    try:
        days = int(days)
    except Exception:
        return recs
    if days <= 0:
        return recs
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    out = []
    for r in recs:
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


def _decision_action(payload):
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("action") or "").strip().upper()


def _decision_scope(decision):
    if not isinstance(decision, dict):
        return "advisory"
    payload = decision.get("payload", {}) if isinstance(decision.get("payload"), dict) else {}
    raw = payload.get("decision_scope") or payload.get("intent") or payload.get("mode")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    if bool(meta.get("auto_execute")):
        return "order"
    source = str(decision.get("source") or "").strip().lower()
    if source in {"paper_broker", "live_broker", "real_broker", "trade_engine", "execution_engine"}:
        return "order"
    return "advisory"


def _decision_requires_execution(decision):
    payload = decision.get("payload", {}) if isinstance(decision, dict) and isinstance(decision.get("payload"), dict) else {}
    action = _decision_action(payload)
    if action not in ("BUY", "SELL"):
        return False
    scope = _decision_scope(decision)
    return scope in {"order", "execution", "auto_trade", "trade"}


def _calc_execution_coverage(decisions, executions):
    actionable_ids = set()
    hold_count = 0
    other_count = 0
    advisory_actionable_count = 0
    for d in decisions:
        if not isinstance(d, dict):
            continue
        did = d.get("decision_id")
        if not did:
            continue
        payload = d.get("payload", {}) if isinstance(d.get("payload"), dict) else {}
        action = _decision_action(payload)
        if action in ("BUY", "SELL"):
            if _decision_requires_execution(d):
                actionable_ids.add(did)
            else:
                advisory_actionable_count += 1
        elif action == "HOLD":
            hold_count += 1
        else:
            other_count += 1

    exec_ids = set(e.get("decision_id") for e in executions if isinstance(e, dict) and e.get("decision_id"))
    linked_count = len(actionable_ids.intersection(exec_ids))
    actionable_count = len(actionable_ids)
    missing_count = max(0, actionable_count - linked_count)
    execution_rate = (linked_count / actionable_count) if actionable_count else 1.0
    return {
        "actionable_count": actionable_count,
        "advisory_actionable_count": advisory_actionable_count,
        "hold_count": hold_count,
        "other_count": other_count,
        "linked_count": linked_count,
        "missing_count": missing_count,
        "execution_rate": execution_rate,
    }


def _count_linked_outcome_decisions(decision_ids, out_ids):
    decision_ids = set(decision_ids or [])
    out_ids = set(out_ids or [])
    if not decision_ids or not out_ids:
        return 0
    return len(decision_ids.intersection(out_ids))


def _load_skill_stats(db_path):
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        rows = cur.execute("SELECT name, total_calls, hits, avg_return, scan_hits, reward_sum, reward_count, last_reward, last_reward_ts FROM strategy_stats").fetchall()
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


def main():
    parser = argparse.ArgumentParser(description="Closed-loop health check")
    parser.add_argument("--event-bus", default="data/event_bus.jsonl")
    parser.add_argument("--trades", default="data/trades.jsonl")
    parser.add_argument("--skills-db", default="data/skills.db")
    parser.add_argument("--limit", type=int, default=0, help="tail N lines from jsonl")
    parser.add_argument("--days", type=int, default=0, help="only include records within N days")
    parser.add_argument("--no-write", action="store_true", help="skip writing report files")
    parser.add_argument("--report-path", default="data/loop_health_report.jsonl", help="append report jsonl path")
    parser.add_argument("--latest-path", default="data/loop_health_latest.json", help="write latest report json path")
    args = parser.parse_args()

    events = _load_jsonl(args.event_bus, limit=args.limit or None)
    events = _filter_days(events, args.days)

    decisions = [e for e in events if isinstance(e, dict) and e.get("event") == "decision"]
    executions = [e for e in events if isinstance(e, dict) and e.get("event") == "execution"]
    outcomes = [e for e in events if isinstance(e, dict) and e.get("event") == "outcome"]

    decision_map = {}
    for d in decisions:
        if not isinstance(d, dict):
            continue
        did = d.get("decision_id")
        payload = d.get("payload", {}) if isinstance(d.get("payload"), dict) else {}
        if did and isinstance(payload, dict):
            decision_map[str(did)] = payload

    decision_ids = set(d.get("decision_id") for d in decisions if d.get("decision_id"))
    out_ids = set(o.get("decision_id") for o in outcomes if o.get("decision_id"))

    exec_cov = _calc_execution_coverage(decisions, executions)
    decisions_actionable_n = int(exec_cov.get("actionable_count", 0) or 0)
    decisions_advisory_actionable_n = int(exec_cov.get("advisory_actionable_count", 0) or 0)
    decisions_hold_n = int(exec_cov.get("hold_count", 0) or 0)
    decisions_other_n = int(exec_cov.get("other_count", 0) or 0)
    executions_linked_actionable_n = int(exec_cov.get("linked_count", 0) or 0)
    decisions_no_exec = int(exec_cov.get("missing_count", 0) or 0)
    decisions_no_out = sum(1 for d in decisions if d.get("decision_id") and d.get("decision_id") not in out_ids)

    exec_missing_id = sum(1 for e in executions if not e.get("decision_id"))
    out_missing_id = sum(1 for o in outcomes if not o.get("decision_id"))

    out_orphan = sum(1 for o in outcomes if o.get("decision_id") and o.get("decision_id") not in decision_ids)

    # strategy attribution from outcomes
    out_with_strategy = 0
    for o in outcomes:
        payload = o.get("payload", {}) if isinstance(o.get("payload"), dict) else {}
        signal_source = payload.get("signal_source") if isinstance(payload.get("signal_source"), dict) else {}
        strat = _get_strategy_from_signal(signal_source)
        if not strat:
            did = o.get("decision_id") or payload.get("origin_decision_id") or payload.get("decision_id")
            d = decision_map.get(str(did)) if did is not None else None
            if isinstance(d, dict):
                strat = _get_strategy_from_signal(d.get("signal_source"))
        if not strat:
            eval_type = str(payload.get("eval_type") or payload.get("outcome_type") or "").strip().lower()
            if eval_type in ("mark_to_market", "mtm", "unrealized"):
                strat = "tri_brain_default"
        if strat:
            out_with_strategy += 1

    # trades file
    trades = _load_jsonl(args.trades, limit=args.limit or None)
    trades = _filter_days(trades, args.days)
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
    decision_event_missing = 1 if (trade_total > 0 and len(decisions) == 0) else 0

    # skill stats
    skill_stats = _load_skill_stats(args.skills_db)
    if skill_stats is None:
        skill_summary = "skills.db not found"
        strategy_count = 0
        reward_count = 0
    else:
        strategy_count = len(skill_stats)
        reward_count = sum(1 for s in skill_stats if (s.get("reward_count") or 0) > 0)
        skill_summary = f"strategies={strategy_count}, reward_count>0={reward_count}"


    # rates & score
    decisions_n = len(decisions)
    executions_n = len(executions)
    outcomes_n = len(outcomes)
    outcomes_linked_n = _count_linked_outcome_decisions(decision_ids, out_ids)
    outcome_attr_rate = (out_with_strategy / outcomes_n) if outcomes_n else 0.0
    sell_attr_rate = (sell_with_strategy / len(sells)) if sells else 0.0
    exec_rate = float(exec_cov.get("execution_rate", 0.0) or 0.0)
    outcome_rate = (outcomes_linked_n / decisions_n) if decisions_n else 0.0

    score = 100.0
    if decisions_actionable_n:
        score -= 40.0 * (decisions_no_exec / decisions_actionable_n)
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
        if len(decisions) == 0:
            score -= 20.0
    score = max(0.0, min(100.0, score))
    if score >= 85:
        status = "OK"
    elif score >= 70:
        status = "WARN"
    else:
        status = "FAIL"

    # bias / overrides
    bias_path = "data/feature_weight_bias.json"
    bias_ts = ""
    if os.path.exists(bias_path):
        try:
            with open(bias_path, "r", encoding="utf-8") as f:
                bias = json.load(f)
            bias_ts = bias.get("updated_at", "") if isinstance(bias, dict) else ""
        except Exception:
            bias_ts = ""

    override_path = "data/threshold_overrides.json"
    override_ts = ""
    if os.path.exists(override_path):
        try:
            with open(override_path, "r", encoding="utf-8") as f:
                ov = json.load(f)
            override_ts = ov.get("updated_at", "") if isinstance(ov, dict) else ""
        except Exception:
            override_ts = ""

    print("Closed-loop health check")
    print(f"Event bus: total={len(events)} decisions={len(decisions)} executions={len(executions)} outcomes={len(outcomes)}")
    print(
        f"Decision actions: order_intent={decisions_actionable_n} advisory_buy_sell={decisions_advisory_actionable_n} "
        f"hold={decisions_hold_n} other={decisions_other_n}"
    )
    print(f"Decision linkage: no_execution={decisions_no_exec} no_outcome={decisions_no_out}")
    print(f"Event anomalies: execution_missing_id={exec_missing_id} outcome_missing_id={out_missing_id} outcome_orphan={out_orphan}")
    print(f"Outcome strategy attribution: {out_with_strategy}/{len(outcomes)}")
    print(f"Trades: total={len(trades)} buys={len(buys)} sells={len(sells)}")
    print(f"Trade linkage: buy_missing_decision_id={buy_missing_id} sell_missing_origin_id={sell_missing_origin}")
    print(f"Sell strategy attribution: {sell_with_strategy}/{len(sells)}")
    print(f"Trade decision rate: {trade_decision_rate:.2%} | Trade missing decision: {trade_missing_decision}")
    if decision_event_missing:
        print("Decision events missing: trades exist but no decision events logged")
    print(f"Skill registry: {skill_summary}")
    print(f"Bias updated_at: {bias_ts or 'n/a'}")
    print(f"Threshold overrides updated_at: {override_ts or 'n/a'}")
    print(f"Health score: {score:.1f} ({status})")
    exec_rate_text = f"{exec_rate:.2%}" if decisions_actionable_n > 0 else "n/a (no order-intent decisions)"
    print(f"Execution rate: {exec_rate_text} | Outcome rate: {outcome_rate:.2%}")
    print(f"Outcome attribution rate: {outcome_attr_rate:.2%} | Sell attribution rate: {sell_attr_rate:.2%}")

    # report payload (compatible with core.metrics.compute_loop_health)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    report = {
        "ts": now,
        "decisions": decisions_n,
        "decisions_actionable": decisions_actionable_n,
        "decisions_advisory_actionable": decisions_advisory_actionable_n,
        "decisions_hold": decisions_hold_n,
        "decisions_other_action": decisions_other_n,
        "executions": executions_n,
        "executions_linked_actionable": executions_linked_actionable_n,
        "outcomes": outcomes_n,
        "outcome_linked_decisions": outcomes_linked_n,
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
        "skill_summary": {"strategies": strategy_count, "rewarded": reward_count},
        "bias_updated_at": bias_ts,
        "threshold_overrides_updated_at": override_ts,
        "health_score": score,
        "health_status": status,
        "execution_rate": exec_rate,
        "execution_coverage_mode": "order_intent_only",
        "execution_coverage_applicable": decisions_actionable_n > 0,
        "outcome_rate": outcome_rate,
        "outcome_strategy_attrib_rate": outcome_attr_rate,
        "sell_strategy_attrib_rate": sell_attr_rate
    }

    if not args.no_write:
        # append to loop health report history
        try:
            os.makedirs(os.path.dirname(args.report_path), exist_ok=True)
            with open(args.report_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(report, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # write latest snapshot
        try:
            os.makedirs(os.path.dirname(args.latest_path), exist_ok=True)
            with open(args.latest_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


if __name__ == "__main__":
    main()
