#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill event_bus.jsonl from experience_log.jsonl to repair closed-loop chain.

Default mode is dry-run. Use --apply to write.
"""
import argparse
import datetime
import json
import os
import uuid


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


def _filter_days(records, days):
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


def _make_loose_key(event, decision_id, code):
    if event == "decision":
        return ("decision", str(decision_id))
    return (str(event), str(decision_id), str(code or ""))


def main():
    parser = argparse.ArgumentParser(description="Backfill event bus from experience log.")
    parser.add_argument("--experience", default="data/experience_log.jsonl")
    parser.add_argument("--event-bus", default="data/event_bus.jsonl")
    parser.add_argument("--days", type=int, default=0, help="only include records within N days")
    parser.add_argument("--limit", type=int, default=0, help="tail N lines from experience log")
    parser.add_argument("--apply", action="store_true", help="write backfilled events")
    args = parser.parse_args()

    exp = _load_jsonl(args.experience, limit=args.limit or None)
    exp = _filter_days(exp, args.days)
    existing = _load_jsonl(args.event_bus)

    existing_keys = set()
    for rec in existing:
        if not isinstance(rec, dict):
            continue
        ev = rec.get("event")
        if ev not in ("decision", "execution", "outcome"):
            continue
        did = rec.get("decision_id")
        if not did:
            continue
        key = _make_loose_key(ev, did, rec.get("code", ""))
        existing_keys.add(key)

    to_add = []
    skipped_dup = 0
    skipped_no_id = 0
    added_counts = {"decision": 0, "execution": 0, "outcome": 0}

    for rec in exp:
        if not isinstance(rec, dict):
            continue
        ev = rec.get("event")
        if ev not in ("decision", "execution", "outcome"):
            continue
        payload = rec.get("payload", {}) if isinstance(rec.get("payload"), dict) else {}
        decision_id = payload.get("decision_id") or rec.get("decision_id")
        if not decision_id:
            skipped_no_id += 1
            continue
        code = payload.get("code") or rec.get("code") or ""
        key = _make_loose_key(ev, decision_id, code)
        if key in existing_keys:
            skipped_dup += 1
            continue

        event_payload = dict(payload)
        if ev == "decision" and "action" in event_payload and "suggested_action" not in event_payload:
            event_payload["suggested_action"] = event_payload.get("action")

        out = {
            "event_id": uuid.uuid4().hex,
            "ts": rec.get("ts") or datetime.datetime.now().isoformat(timespec="seconds"),
            "event": ev,
            "code": str(code),
            "decision_id": decision_id,
            "source": "experience_backfill",
            "payload": event_payload
        }
        to_add.append(out)
        existing_keys.add(key)
        added_counts[ev] = added_counts.get(ev, 0) + 1

    print("Backfill preview")
    print(f"Experience records scanned: {len(exp)}")
    print(f"Will add: decisions={added_counts['decision']} executions={added_counts['execution']} outcomes={added_counts['outcome']}")
    print(f"Skipped duplicates: {skipped_dup}")
    print(f"Skipped missing decision_id: {skipped_no_id}")

    if not args.apply:
        print("Dry-run: no changes written. Use --apply to write.")
        return

    if not to_add:
        print("No events to add.")
        return

    os.makedirs(os.path.dirname(args.event_bus), exist_ok=True)
    try:
        with open(args.event_bus, "a", encoding="utf-8") as f:
            for rec in to_add:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"Appended {len(to_add)} events to {args.event_bus}")
    except Exception as exc:
        print(f"Write failed: {exc}")


if __name__ == "__main__":
    main()
