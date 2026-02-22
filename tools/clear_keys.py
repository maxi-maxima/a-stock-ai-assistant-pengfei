import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
SECURE_PATH = ROOT / "data" / "secure_settings.json"
LLM_PATH = ROOT / "config" / "llm_config.yaml"

ENV_KEYS = {
    "LLM_API_KEY",
    "BLUE_BRAIN_API_KEY",
    "RED_BRAIN_API_KEY",
    "GREEN_BRAIN_API_KEY",
    "TUSHARE_TOKEN",
}

SECURE_KEYS = {
    "blue_brain_api_key",
    "red_brain_api_key",
    "green_brain_api_key",
}


def clear_env(path):
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = False
    out_lines = []
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            out_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in ENV_KEYS:
            out_lines.append(f"{key}=")
            updated = True
        else:
            out_lines.append(line)
    if updated:
        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return updated


def clear_secure(path):
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    changed = False
    for key in list(SECURE_KEYS):
        if key in data:
            data.pop(key, None)
            changed = True
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def clear_llm_yaml(path):
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    new_text = []
    changed = False
    for line in text.splitlines():
        new_line = line
        new_line = re.sub(r"^(\s*api_key:\s*).*$", r"\1''", new_line)
        new_line = re.sub(r"^(\s*tushare_token:\s*).*$", r"\1''", new_line)
        if new_line != line:
            changed = True
        new_text.append(new_line)
    if changed:
        path.write_text("\n".join(new_text) + "\n", encoding="utf-8")
    return changed


def main():
    env_changed = clear_env(ENV_PATH)
    sec_changed = clear_secure(SECURE_PATH)
    yaml_changed = clear_llm_yaml(LLM_PATH)

    print("Clear result:")
    print("- .env:", "cleared" if env_changed else ("not found" if not ENV_PATH.exists() else "no change"))
    print("- data/secure_settings.json:", "cleared" if sec_changed else ("not found" if not SECURE_PATH.exists() else "no change"))
    print("- config/llm_config.yaml:", "cleared" if yaml_changed else ("not found" if not LLM_PATH.exists() else "no change"))


if __name__ == "__main__":
    main()
