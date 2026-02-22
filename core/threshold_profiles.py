import copy
import json
import os

PROFILE_PATH = "config/threshold_profiles.json"
SETTINGS_PATH = "data/threshold_settings.json"
OVERRIDE_PATH = "data/threshold_overrides.json"

DEFAULT_PROFILE_NAME = "平衡"
DEFAULT_ORDER = ["保守", "平衡", "激进"]

PROFILE_DESC = {
    "保守": "高门槛 + 强风控，回撤与仓位限制更严格，优先稳健。",
    "平衡": "系统默认中枢，兼顾胜率与机会。",
    "激进": "门槛降低、机会更多，但波动与回撤风险更高。"
}

DEFAULT_PROFILES = {
    "保守": {
        "rules": {
            "constraints": {
                "max_single_position": 0.20,
                "max_industry_concentration": 0.25,
                "max_drawdown": 0.12,
                "max_daily_trades": 3,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
                "allow_chase": False
            }
        },
        "tactics": {
            "fin_threshold": 80,
            "grid_period": 20,
            "grid_multiplier": 1.5,
            "deep_risk": True,
            "enable_morning": True,
            "enable_kb": True,
            "enable_sentiment": True,
            "enable_news": True,
            "enable_fin": True,
            "save_history": True
        },
        "patrol": {
            "take_profit": 8.0,
            "stop_loss": 4.0,
            "flow_th": -5000.0,
            "max_scan_global": 1000,
            "max_scan_pool": 600,
            "top_k": 60,
            "min_score": 60.0,
            "enable_fin_score": True,
            "fin_threshold": 80,
            "fin_weight": 12.0,
            "fin_filter": True
        },
        "radar": {
            "deep_risk": True,
            "fin_threshold": 80
        }
    },
    "平衡": {
        "rules": {
            "constraints": {
                "max_single_position": 0.30,
                "max_industry_concentration": 0.35,
                "max_drawdown": 0.20,
                "max_daily_trades": 6,
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.15,
                "allow_chase": False
            }
        },
        "tactics": {
            "fin_threshold": 70,
            "grid_period": 14,
            "grid_multiplier": 1.0,
            "deep_risk": False,
            "enable_morning": True,
            "enable_kb": True,
            "enable_sentiment": True,
            "enable_news": True,
            "enable_fin": True,
            "save_history": True
        },
        "patrol": {
            "take_profit": 10.0,
            "stop_loss": 5.0,
            "flow_th": -10000.0,
            "max_scan_global": 1500,
            "max_scan_pool": 800,
            "top_k": 80,
            "min_score": 40.0,
            "enable_fin_score": True,
            "fin_threshold": 70,
            "fin_weight": 10.0,
            "fin_filter": False
        },
        "radar": {
            "deep_risk": False,
            "fin_threshold": 70
        }
    },
    "激进": {
        "rules": {
            "constraints": {
                "max_single_position": 0.45,
                "max_industry_concentration": 0.50,
                "max_drawdown": 0.30,
                "max_daily_trades": 10,
                "stop_loss_pct": 0.08,
                "take_profit_pct": 0.25,
                "allow_chase": True
            }
        },
        "tactics": {
            "fin_threshold": 60,
            "grid_period": 10,
            "grid_multiplier": 0.8,
            "deep_risk": False,
            "enable_morning": True,
            "enable_kb": True,
            "enable_sentiment": True,
            "enable_news": True,
            "enable_fin": True,
            "save_history": True
        },
        "patrol": {
            "take_profit": 15.0,
            "stop_loss": 8.0,
            "flow_th": -15000.0,
            "max_scan_global": 3000,
            "max_scan_pool": 1200,
            "top_k": 120,
            "min_score": 20.0,
            "enable_fin_score": True,
            "fin_threshold": 60,
            "fin_weight": 6.0,
            "fin_filter": False
        },
        "radar": {
            "deep_risk": False,
            "fin_threshold": 60
        }
    }
}


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return copy.deepcopy(override)
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out.get(k), v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_profiles():
    profiles = copy.deepcopy(DEFAULT_PROFILES)
    data = _read_json(PROFILE_PATH, {})
    if "profiles" in data and isinstance(data.get("profiles"), dict):
        data = data.get("profiles", {})
    if isinstance(data, dict):
        for name, profile in data.items():
            if not isinstance(profile, dict):
                continue
            if name in profiles:
                profiles[name] = _deep_merge(profiles[name], profile)
            else:
                profiles[name] = copy.deepcopy(profile)
    # dynamic overrides (non-destructive)
    override = _read_json(OVERRIDE_PATH, {})
    if isinstance(override, dict):
        o_profiles = override.get("profiles", {}) if isinstance(override.get("profiles", {}), dict) else {}
        for name, profile in o_profiles.items():
            if not isinstance(profile, dict):
                continue
            if name in profiles:
                profiles[name] = _deep_merge(profiles[name], profile)
            else:
                profiles[name] = copy.deepcopy(profile)
    return profiles


def list_profile_names(profiles=None):
    profiles = profiles or load_profiles()
    names = []
    for name in DEFAULT_ORDER:
        if name in profiles:
            names.append(name)
    for name in profiles.keys():
        if name not in names:
            names.append(name)
    return names


def get_profile(name, profiles=None):
    profiles = profiles or load_profiles()
    if name in profiles:
        return profiles[name]
    if DEFAULT_PROFILE_NAME in profiles:
        return profiles[DEFAULT_PROFILE_NAME]
    return next(iter(profiles.values()))


def load_user_settings():
    return _read_json(SETTINGS_PATH, {})


def save_user_settings(settings):
    _write_json(SETTINGS_PATH, settings)


def get_active_profile_name(profiles=None):
    profiles = profiles or load_profiles()
    settings = load_user_settings()
    name = settings.get("profile") or DEFAULT_PROFILE_NAME
    if name not in profiles:
        if DEFAULT_PROFILE_NAME in profiles:
            name = DEFAULT_PROFILE_NAME
        else:
            name = next(iter(profiles.keys()))
    return name


def set_active_profile_name(name):
    settings = load_user_settings()
    settings["profile"] = name
    save_user_settings(settings)
