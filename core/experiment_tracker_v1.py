import datetime
import importlib
import json
import os


SAMPLES_PATH = "data/learning_samples.jsonl"
PROFILES_PATH = "data/strategy_profiles.json"
TRACKING_PATH = "data/experiment_tracking.jsonl"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except Exception:
        return float(default)


def _safe_int(val, default=0):
    try:
        return int(val)
    except Exception:
        return int(default)


def _load_json(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {} if default is None else default


def _load_jsonl(path):
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
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception:
        return []
    return out


def _append_jsonl(path, row):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _build_snapshot(samples_count, profiles_payload):
    summary = profiles_payload.get("summary", {}) if isinstance(profiles_payload.get("summary", {}), dict) else {}
    profiles = profiles_payload.get("profiles", {}) if isinstance(profiles_payload.get("profiles", {}), dict) else {}

    champion = str(summary.get("champion_strategy") or "").strip()
    champion_profile = profiles.get(champion, {}) if champion else {}
    if not isinstance(champion_profile, dict):
        champion_profile = {}

    out = {
        "ts": _now(),
        "profiles_updated_at": summary.get("updated_at") or "",
        "sample_count": _safe_int(summary.get("sample_count"), default=samples_count),
        "valid_rate": _safe_float(summary.get("valid_rate"), default=0.0),
        "labeled_rate": _safe_float(summary.get("labeled_rate"), default=0.0),
        "profile_count": _safe_int(summary.get("profile_count"), default=len(profiles)),
        "champion_strategy": champion,
        "champion_decayed_pnl_pct": _safe_float(summary.get("champion_decayed_pnl_pct"), default=0.0),
        "champion_drift_7_vs_30": _safe_float(champion_profile.get("drift_7_vs_30"), default=0.0),
        "drift_warning_count": _safe_int(summary.get("drift_warning_count"), default=0),
    }
    return out


def load_experiment_history(path=TRACKING_PATH, limit=120):
    rows = _load_jsonl(path)
    if limit and len(rows) > int(limit):
        rows = rows[-int(limit):]
    return rows


def _log_mlflow(snapshot, experiment_name, tracking_uri=None):
    try:
        mlflow = importlib.import_module("mlflow")
    except Exception as exc:
        return False, f"mlflow import failed: {exc}"

    try:
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(str(experiment_name or "KIMIstock-Learning"))
        run_name = f"learning_v2_{snapshot.get('ts', '')}"
        with mlflow.start_run(run_name=run_name):
            mlflow.log_param("champion_strategy", snapshot.get("champion_strategy") or "")
            mlflow.log_metric("sample_count", _safe_int(snapshot.get("sample_count"), default=0))
            mlflow.log_metric("valid_rate", _safe_float(snapshot.get("valid_rate"), default=0.0))
            mlflow.log_metric("labeled_rate", _safe_float(snapshot.get("labeled_rate"), default=0.0))
            mlflow.log_metric("profile_count", _safe_int(snapshot.get("profile_count"), default=0))
            mlflow.log_metric("champion_decayed_pnl_pct", _safe_float(snapshot.get("champion_decayed_pnl_pct"), default=0.0))
            mlflow.log_metric("champion_drift_7_vs_30", _safe_float(snapshot.get("champion_drift_7_vs_30"), default=0.0))
            mlflow.log_metric("drift_warning_count", _safe_int(snapshot.get("drift_warning_count"), default=0))
        return True, ""
    except Exception as exc:
        return False, f"mlflow log failed: {exc}"


def refresh_experiment_tracking(
    apply=True,
    samples_path=SAMPLES_PATH,
    profiles_path=PROFILES_PATH,
    tracking_path=TRACKING_PATH,
    mlflow_enabled=None,
    mlflow_tracking_uri=None,
    mlflow_experiment_name="KIMIstock-Learning",
):
    samples = _load_jsonl(samples_path)
    profiles_payload = _load_json(profiles_path, default={})
    snapshot = _build_snapshot(len(samples), profiles_payload)

    if apply:
        _append_jsonl(tracking_path, snapshot)

    if mlflow_enabled is None:
        mlflow_enabled = str(os.getenv("ENABLE_MLFLOW_TRACKING", "0")).strip() == "1"

    mlflow_logged = False
    mlflow_error = ""
    if mlflow_enabled:
        mlflow_logged, mlflow_error = _log_mlflow(
            snapshot,
            experiment_name=mlflow_experiment_name,
            tracking_uri=mlflow_tracking_uri or os.getenv("MLFLOW_TRACKING_URI", "").strip() or None,
        )

    return {
        "ok": True,
        "tracking_path": tracking_path,
        "sample_count": snapshot.get("sample_count", 0),
        "valid_rate": snapshot.get("valid_rate", 0.0),
        "labeled_rate": snapshot.get("labeled_rate", 0.0),
        "profile_count": snapshot.get("profile_count", 0),
        "champion_strategy": snapshot.get("champion_strategy", ""),
        "champion_decayed_pnl_pct": snapshot.get("champion_decayed_pnl_pct", 0.0),
        "champion_drift_7_vs_30": snapshot.get("champion_drift_7_vs_30", 0.0),
        "drift_warning_count": snapshot.get("drift_warning_count", 0),
        "mlflow_enabled": bool(mlflow_enabled),
        "mlflow_logged": bool(mlflow_logged),
        "mlflow_error": mlflow_error,
    }
