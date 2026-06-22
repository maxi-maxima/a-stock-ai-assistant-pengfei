#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TARGET_FILES = [
    "config/strategy_training.json",
    "config/backtest_params.json",
    "config/strategy_params.json",
    "config/strategy_governor.json",
    "config/agent_lightning.json",
    "config/trading_costs.json",
    "config/ma_periods.json",
]


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _deep_update(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _apply_backtest_patch(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    default_patch = patch.get("__default__", {}) if isinstance(patch.get("__default__"), dict) else {}

    for strategy_name, conf in current.items():
        if not isinstance(conf, dict):
            continue
        if default_patch:
            _deep_update(conf, default_patch)
        special = patch.get(strategy_name)
        if isinstance(special, dict):
            _deep_update(conf, special)
    return current


def _backup_configs() -> Path:
    backup_root = PROJECT_ROOT / "config" / "_backups"
    backup_root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_backup = backup_root / f"apply_tuning_{stamp}"
    run_backup.mkdir(parents=True, exist_ok=True)

    for rel in TARGET_FILES:
        src = PROJECT_ROOT / rel
        if not src.exists():
            continue
        dst = run_backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return run_backup


def apply_profile(profile_name: str) -> dict[str, Any]:
    profile_path = PROJECT_ROOT / "config" / "tuning_profiles" / f"{profile_name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"未找到模板: {profile_path}")

    profile = _read_json(profile_path)
    files_patch = profile.get("files")
    if not isinstance(files_patch, dict):
        raise ValueError("模板格式错误: files 必须是对象")

    backup_dir = _backup_configs()
    changed: list[str] = []

    for rel_path, patch in files_patch.items():
        if rel_path not in TARGET_FILES:
            continue
        if not isinstance(patch, dict):
            continue

        target = PROJECT_ROOT / rel_path
        if not target.exists():
            continue

        current = _read_json(target)
        if not isinstance(current, dict):
            continue

        if rel_path.endswith("backtest_params.json"):
            new_data = _apply_backtest_patch(current, patch)
        else:
            new_data = _deep_update(current, patch)

        _write_json(target, new_data)
        changed.append(rel_path)

    return {
        "ok": True,
        "profile": profile_name,
        "backup_dir": str(backup_dir),
        "changed_files": changed,
    }


def list_profiles() -> list[str]:
    profiles_dir = PROJECT_ROOT / "config" / "tuning_profiles"
    if not profiles_dir.exists():
        return []
    return sorted([p.stem for p in profiles_dir.glob("*.json") if p.is_file()])


def main() -> int:
    parser = argparse.ArgumentParser(description="一键切换参数模板（含自动备份）")
    parser.add_argument("--profile", default="conservative", help="模板名: conservative / aggressive")
    parser.add_argument("--list", action="store_true", help="列出可用模板")
    args = parser.parse_args()

    if args.list:
        print(json.dumps({"profiles": list_profiles()}, ensure_ascii=False, indent=2))
        return 0

    try:
        out = apply_profile(str(args.profile).strip())
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
