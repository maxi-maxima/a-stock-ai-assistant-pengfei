import argparse
import json
import math
import os
from collections import Counter


DEFAULT_CONFIG_PATH = "config/agent_lightning.json"


def _safe_float(val):
    try:
        return float(val)
    except Exception:
        return None


def _percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = int(math.ceil(p / 100.0 * len(values))) - 1
    k = max(0, min(k, len(values) - 1))
    return values[k]


def _load_config(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_records(path):
    if not os.path.exists(path):
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    records.append(rec)
    except Exception:
        return records
    return records


def _pick_latest_run_id(records):
    for rec in reversed(records):
        run_id = rec.get("run_id")
        if run_id:
            return run_id
    return None


def _summarize(records):
    actions = Counter()
    raw_actions = Counter()
    risk_levels = Counter()
    scores = []
    rewards = []
    critic_scores = []
    overrides = 0
    errors = []

    for r in records:
        action = str(r.get("action") or "HOLD").upper()
        raw_action = str(r.get("action_raw") or "HOLD").upper()
        actions[action] += 1
        raw_actions[raw_action] += 1
        if action != raw_action:
            overrides += 1

        risk = str(r.get("risk_level") or "").upper()
        if risk:
            risk_levels[risk] += 1

        score = _safe_float(r.get("score_total"))
        if score is not None:
            scores.append(score)

        reward = _safe_float(r.get("reward"))
        if reward is not None:
            rewards.append(reward)

        cscore = _safe_float(r.get("critic_score"))
        if cscore is not None:
            critic_scores.append(cscore)

        err = r.get("error")
        if err:
            errors.append(err)

    summary = {
        "tasks": len(records),
        "actions": actions,
        "raw_actions": raw_actions,
        "risk_levels": risk_levels,
        "override_count": overrides,
        "scores": scores,
        "rewards": rewards,
        "critic_scores": critic_scores,
        "errors": errors
    }
    return summary


def _fmt_counter(counter):
    if not counter:
        return "-"
    return ", ".join([f"{k}:{v}" for k, v in counter.items()])


def main():
    parser = argparse.ArgumentParser(description="Summarize Agent Lightning report")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path")
    parser.add_argument("--report-path", default="", help="override report path")
    parser.add_argument("--run-id", default="", help="summarize a specific run_id")
    args = parser.parse_args()

    cfg = _load_config(args.config)
    report_path = args.report_path or cfg.get("report_path") or "data/agent_lightning_report.jsonl"
    records = _load_records(report_path)
    if not records:
        print(f"No records found: {report_path}")
        return

    run_id = args.run_id or _pick_latest_run_id(records)
    if run_id:
        records = [r for r in records if str(r.get("run_id")) == str(run_id)]

    if not records:
        print("No records matched the selected run_id.")
        return

    summary = _summarize(records)
    scores = summary["scores"]
    rewards = summary["rewards"]
    critic_scores = summary["critic_scores"]

    print("Agent Lightning Summary")
    print(f"report_path: {report_path}")
    if run_id:
        print(f"run_id: {run_id}")
    print(f"tasks: {summary['tasks']}")
    print(f"actions: {_fmt_counter(summary['actions'])}")
    print(f"raw_actions: {_fmt_counter(summary['raw_actions'])}")
    print(f"risk_levels: {_fmt_counter(summary['risk_levels'])}")
    print(f"override_count: {summary['override_count']}")

    if scores:
        print(
            "score_total: "
            f"min={min(scores):.2f}, max={max(scores):.2f}, "
            f"avg={sum(scores)/len(scores):.2f}"
        )
    else:
        print("score_total: -")

    if rewards:
        print(
            "reward: "
            f"min={min(rewards):.3f}, max={max(rewards):.3f}, "
            f"avg={sum(rewards)/len(rewards):.3f}"
        )
    else:
        print("reward: -")

    if critic_scores:
        nonzero = sum(1 for c in critic_scores if c)
        p50 = _percentile(critic_scores, 50)
        p90 = _percentile(critic_scores, 90)
        print(
            "critic_score: "
            f"min={min(critic_scores):.2f}, max={max(critic_scores):.2f}, "
            f"p50={p50:.2f}, p90={p90:.2f}, "
            f"nonzero={nonzero}"
        )
    else:
        print("critic_score: -")

    if summary["errors"]:
        print(f"errors: {len(summary['errors'])}")
        print(f"sample_error: {summary['errors'][0]}")
    else:
        print("errors: 0")


if __name__ == "__main__":
    main()
