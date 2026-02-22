import os
import json
import yaml
from openai import OpenAI
from core.llm_guard import parse_json_safe, validate_debate, log_llm
from core.env_loader import load_env, is_placeholder_value


class TriBrainCouncil:
    def __init__(self):
        self._load_config()

    def _clean_key(self, val):
        if val is None:
            return None
        try:
            v = str(val).strip()
        except Exception:
            return None
        if not v:
            return None
        if is_placeholder_value(v):
            return None
        return v

    def _load_secure_settings(self):
        path = "data/secure_settings.json"
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_config(self):
        load_env()
        self.config = {}
        self.brains = {}
        self.client = None
        self.model = None
        self.secure = self._load_secure_settings()
        try:
            with open("config/llm_config.yaml", "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
        except Exception:
            return

        self._init_brain("blue", self.config.get("blue_brain"), env_prefix="BLUE_BRAIN")
        self._init_brain("red", self.config.get("red_brain"), env_prefix="RED_BRAIN")
        self._init_brain("green", self.config.get("green_brain"), env_prefix="GREEN_BRAIN")

        if not self.brains:
            self._init_brain("default", self.config.get("llm", {}), env_prefix="LLM")

        if self.brains:
            primary = self.brains.get("blue") or self.brains.get("default") or next(iter(self.brains.values()))
            self.client = primary.get("client")
            self.model = primary.get("model")

    def _init_brain(self, key, conf, env_prefix="LLM"):
        if not isinstance(conf, dict):
            return
        secure_key = f"{key}_brain_api_key"
        api_key = (
            self._clean_key(os.getenv(f"{env_prefix}_API_KEY"))
            or self._clean_key(os.getenv("LLM_API_KEY"))
            or self._clean_key(self.secure.get(secure_key) if isinstance(self.secure, dict) else None)
            or self._clean_key(self.secure.get("llm_api_key") if isinstance(self.secure, dict) else None)
            or self._clean_key(conf.get("api_key"))
        )
        base_url = os.getenv(f"{env_prefix}_BASE_URL") or os.getenv("LLM_BASE_URL") or conf.get("base_url")
        model = os.getenv(f"{env_prefix}_MODEL") or os.getenv("LLM_MODEL") or conf.get("model")
        if not api_key or not model:
            return
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
        except Exception:
            return
        self.brains[key] = {
            "client": client,
            "model": model,
            "name": conf.get("name", key),
            "base_url": base_url
        }

    def _get_morning_prompt(self):
        return '''
You are a macro strategy committee.
Task:
1) Analyze global market indices and macro news.
2) Predict A-share opening sentiment and recommend overall position size.
Input keys:
- global_indices
- macro_news
- user_fund_detail
Output JSON ONLY (no markdown):
{
  "core_view": "one-sentence market view",
  "action": "BUY/SELL/HOLD",
  "risk_warning": "...",
  "blue_view": "...",
  "red_view": "...",
  "final_verdict": "...",
  "bull_bear_power": {"bull": 60, "bear": 40}
}
'''

    def _get_stock_prompt(self):
        return '''
You are a six-factor weighted decision engine.
Task:
1) Score the target across six factors.
2) Compute a disciplined grid strategy based on ATR/BOLL/EMA and position state.
Input keys include (not limited to):
- morning_briefing_guidance
- tech_factors, market_data
- user_position_detail, user_fund_detail
- capital, chip, news, macro_env, macro_news, memory, knowledge_base
- sector_flow, global_index
- dealer_hunter, chip_analyst, liquidity_guard, cycle_compass, sentiment_weather
- reference_pack, feature_pack, macro_pack, factor_snapshot, calculated_grid
Output JSON ONLY (no markdown):
{
  "scores": {
    "capital": 80, "technical": 60, "macro": 40, "news": 50, "memory": 70, "knowledge": 60,
    "total": 61, "reason": "..."
  },
  "action": "BUY/SELL/HOLD",
  "core_view": "...",
  "risk_warning": "...",
  "grid_strategy": {
    "note": "...",
    "buy1_price": "...", "buy1_action": "...",
    "buy2_price": "...", "buy2_action": "...",
    "sell1_price": "...", "sell1_action": "...",
    "sell2_price": "...", "sell2_action": "..."
  },
  "scenarios": [
    {"name": "attack", "prob": "...", "condition": "...", "action": "..."},
    {"name": "range", "prob": "...", "condition": "...", "action": "..."},
    {"name": "pullback", "prob": "...", "condition": "...", "action": "..."},
    {"name": "stress", "prob": "...", "condition": "...", "action": "..."}
  ],
  "feature_weights": {
    "capital": 20, "technical": 20, "macro": 15, "news": 10, "memory": 10, "knowledge": 10, "reference": 10, "features": 5
  },
  "blue_view": "...",
  "red_view": "...",
  "final_verdict": "..."
}
Rules:
- If user_position_detail is empty, sell grid must be empty.
'''

    def _get_role_prompt(self, role, base_prompt):
        role = (role or "").lower()
        role_hint = ""
        if role == "blue":
            role_hint = "You are the BLUE brain (bullish/constructive). Provide optimistic but justified reasoning."
        elif role == "red":
            role_hint = "You are the RED brain (bearish/defensive). Focus on risks and downside."
        elif role == "green":
            role_hint = "You are the GREEN brain (judge). Weigh blue vs red and produce the final verdict."
        if role_hint:
            return role_hint + " " + base_prompt
        return base_prompt

    def _format_rules(self, rules):
        if not isinstance(rules, dict):
            return ""
        general = str(rules.get("general", "")).strip()
        blue = str(rules.get("blue", "")).strip()
        red = str(rules.get("red", "")).strip()
        green = str(rules.get("green", "")).strip()
        constraints = rules.get("constraints", {}) if isinstance(rules.get("constraints"), dict) else {}
        if constraints:
            cons_txt = []
            for k, v in constraints.items():
                cons_txt.append(f"{k}={v}")
            cons_line = " | ".join(cons_txt)
        else:
            cons_line = ""
        parts = []
        if general:
            parts.append(f"[GENERAL]{general}")
        if blue:
            parts.append(f"[BLUE]{blue}")
        if red:
            parts.append(f"[RED]{red}")
        if green:
            parts.append(f"[GREEN]{green}")
        if cons_line:
            parts.append(f"[CONSTRAINTS]{cons_line}")
        return " | ".join(parts).strip()

    def _extract_view(self, data, fallback_key=None):
        if not isinstance(data, dict):
            return ""
        if fallback_key and data.get(fallback_key):
            return str(data.get(fallback_key))
        for k in ["blue_view", "red_view", "view", "core_view", "analysis", "opinion"]:
            if data.get(k):
                return str(data.get(k))
        return ""

    def _call_brain(self, brain_key, sys_prompt, user_prompt, mode):
        brain = self.brains.get(brain_key)
        if not brain:
            return None, None
        try:
            res = brain["client"].chat.completions.create(
                model=brain["model"],
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.2
            )
            raw_content = res.choices[0].message.content
            data, cleaned = parse_json_safe(raw_content)
            log_llm(f"{mode}_{brain_key}", brain.get("model", ""), raw_content, cleaned, ok=bool(data))
            return data, raw_content
        except Exception as exc:
            try:
                log_llm(f"{mode}_{brain_key}", brain.get("model", ""), f"ERROR: {exc}", "", ok=False)
            except Exception:
                pass
            return None, None

    def _fallback_result(self, mode, msg="LLM not configured"):
        if mode == "morning":
            return {
                "core_view": msg,
                "action": "HOLD",
                "risk_warning": "system error",
                "blue_view": "",
                "red_view": "",
                "final_verdict": msg,
                "bull_bear_power": {"bull": 50, "bear": 50}
            }
        return {
            "action": "HOLD",
            "core_view": msg,
            "risk_warning": "system error",
            "scores": {
                "capital": 50, "technical": 50, "macro": 50, "news": 50,
                "memory": 50, "knowledge": 50, "total": 50, "reason": msg
            },
            "grid_strategy": {},
            "scenarios": [],
            "blue_view": "",
            "red_view": "",
            "final_verdict": msg
        }

    def _normalize_action(self, result):
        try:
            action = str(result.get("action", "HOLD")).upper()
        except Exception:
            action = "HOLD"
        if action not in ["BUY", "SELL", "HOLD"]:
            action = "HOLD"
        result["action"] = action
        return result

    def debate(self, context_data, custom_rules=None, mode="stock"):
        if os.getenv("LLM_OFFLINE", "0") == "1" or os.getenv("DISABLE_LLM", "0") == "1":
            return self._fallback_result(mode, "LLM disabled by env")
        if not self.brains:
            return self._fallback_result(mode, "LLM not configured")

        if mode == "morning":
            sys_prompt = self._get_morning_prompt()
        else:
            sys_prompt = self._get_stock_prompt()

        rules_block = self._format_rules(custom_rules)
        rule_prefix = ("[RULES] " + rules_block + " ") if rules_block else ""
        payload = context_data if isinstance(context_data, dict) else {"context": context_data}
        user_prompt = f"{rule_prefix}[CONTEXT]{json.dumps(payload, ensure_ascii=False, default=str)}"

        # three-brain real execution if available
        if all(k in self.brains for k in ["blue", "red", "green"]):
            blue_data, _ = self._call_brain("blue", self._get_role_prompt("blue", sys_prompt), user_prompt, mode)
            red_data, _ = self._call_brain("red", self._get_role_prompt("red", sys_prompt), user_prompt, mode)

            judge_ctx = dict(payload)
            if blue_data:
                judge_ctx["blue_brain"] = blue_data
            if red_data:
                judge_ctx["red_brain"] = red_data

            judge_prompt = f"{rule_prefix}[CONTEXT]{json.dumps(judge_ctx, ensure_ascii=False, default=str)}"
            green_data, _ = self._call_brain("green", self._get_role_prompt("green", sys_prompt), judge_prompt, mode)

            if green_data is None:
                fallback = blue_data or red_data
                if not fallback:
                    return self._fallback_result(mode, "LLM error")
                result = validate_debate(fallback, mode=mode)
            else:
                result = validate_debate(green_data, mode=mode)

            if blue_data:
                result["blue_view"] = self._extract_view(blue_data, "blue_view")
            if red_data:
                result["red_view"] = self._extract_view(red_data, "red_view")

            return self._normalize_action(result)

        # fallback to single brain
        primary = "blue" if "blue" in self.brains else ("red" if "red" in self.brains else ("green" if "green" in self.brains else "default"))
        data, _ = self._call_brain(primary, sys_prompt, user_prompt, mode)
        if data is None:
            return self._fallback_result(mode, "LLM error")
        result = validate_debate(data, mode=mode)
        return self._normalize_action(result)
