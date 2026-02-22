import datetime
import json
import os

from core.experience_store import ExperienceStore


BIAS_PATH = "data/feature_weight_bias.json"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _load_bias():
    if not os.path.exists(BIAS_PATH):
        return {}
    try:
        with open(BIAS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_bias(data):
    os.makedirs(os.path.dirname(BIAS_PATH), exist_ok=True)
    try:
        with open(BIAS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def update_bias(lookback_days=30, min_samples=5):
    store = ExperienceStore()
    events = store.load_events(limit=5000)
    decisions = {}
    outcomes = []
    cutoff = None
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=int(lookback_days))
    except Exception:
        cutoff = None

    for ev in events:
        if not isinstance(ev, dict):
            continue
        ev_type = ev.get("event")
        payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
        ts = ev.get("ts")
        if cutoff and isinstance(ts, str):
            try:
                if datetime.datetime.fromisoformat(ts) < cutoff:
                    continue
            except Exception:
                pass
        if ev_type == "decision":
            did = payload.get("decision_id")
            if did:
                decisions[did] = payload
        elif ev_type == "outcome":
            outcomes.append(payload)

    if not outcomes:
        return {}

    feature_keys = set()
    for d in decisions.values():
        fw = d.get("feature_weights", {}) if isinstance(d.get("feature_weights"), dict) else {}
        feature_keys.update(fw.keys())

    if not feature_keys:
        return {}

    acc = {k: 0.0 for k in feature_keys}
    count = 0

    for oc in outcomes:
        if not isinstance(oc, dict):
            continue
        did = oc.get("decision_id") or oc.get("origin_decision_id")
        if not did:
            continue
        dec = decisions.get(did)
        if not dec:
            continue
        fw = dec.get("feature_weights", {}) if isinstance(dec.get("feature_weights"), dict) else {}
        if not fw:
            continue
        pnl_pct = oc.get("pnl_pct")
        if pnl_pct is None:
            try:
                pnl_pct = float(oc.get("pnl", 0) or 0)
            except Exception:
                pnl_pct = 0.0
        try:
            pnl_pct = float(pnl_pct)
        except Exception:
            pnl_pct = 0.0
        delta = _clamp(pnl_pct, -0.2, 0.2)
        if delta == 0:
            continue
        count += 1
        for k in feature_keys:
            try:
                w = float(fw.get(k, 0) or 0) / 100.0
            except Exception:
                w = 0.0
            acc[k] += delta * w

    if count < int(min_samples):
        return {}

    bias = {}
    for k, v in acc.items():
        # scale to weight points, clamp to +/-5
        b = (v / max(1, count)) * 100.0
        bias[k] = round(_clamp(b, -5.0, 5.0), 2)

    payload = {
        "updated_at": _now(),
        "samples": count,
        "lookback_days": lookback_days,
        "bias": bias
    }
    _save_bias(payload)
    return payload


def load_bias(max_age_hours=12, auto_update=True):
    data = _load_bias()
    if not data:
        if auto_update:
            return update_bias()
        return {}
    ts = data.get("updated_at")
    if auto_update and ts:
        try:
            updated_at = datetime.datetime.fromisoformat(ts)
            age_hours = (datetime.datetime.now() - updated_at).total_seconds() / 3600.0
            if age_hours >= float(max_age_hours):
                return update_bias()
        except Exception:
            pass
    return data
