import os
import json
import yaml
import hashlib
from collections import Counter
from openai import OpenAI
from core.llm_guard import parse_json_safe, validate_debate, log_llm
from core.env_loader import load_env, is_placeholder_value
from core.llm_resolver import resolve_brain_settings


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
        self.debate_cfg = {}
        self.secure = self._load_secure_settings()
        try:
            with open("config/llm_config.yaml", "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
        except Exception:
            return
        self.debate_cfg = self._load_debate_config(self.config.get("debate", {}))

        self._init_brain("blue", self.config.get("blue_brain"), env_prefix="BLUE_BRAIN")
        self._init_brain("red", self.config.get("red_brain"), env_prefix="RED_BRAIN")
        self._init_brain("green", self.config.get("green_brain"), env_prefix="GREEN_BRAIN")

        if not self.brains:
            self._init_brain("default", self.config.get("llm", {}), env_prefix="LLM")

        if self.brains:
            primary = self.brains.get("blue") or self.brains.get("default") or next(iter(self.brains.values()))
            self.client = primary.get("client")
            self.model = primary.get("model")

    def _load_debate_config(self, raw):
        raw = raw if isinstance(raw, dict) else {}
        role_rotation = raw.get("role_rotation", {}) if isinstance(raw.get("role_rotation"), dict) else {}
        multi_judge = raw.get("multi_judge", {}) if isinstance(raw.get("multi_judge"), dict) else {}

        try:
            rounds = int(raw.get("rounds", 3) or 3)
        except Exception:
            rounds = 3
        rounds = max(1, min(3, rounds))

        try:
            temperature = float(raw.get("temperature", 0.2) or 0.2)
        except Exception:
            temperature = 0.2
        temperature = max(0.0, min(1.0, temperature))

        judges = multi_judge.get("judges", ["green"])
        if isinstance(judges, str):
            judges = [judges]
        if not isinstance(judges, list):
            judges = ["green"]

        return {
            "enabled": bool(raw.get("enabled", True)),
            "rounds": rounds,
            "temperature": temperature,
            "role_rotation_enabled": bool(role_rotation.get("enabled", False)),
            "role_rotation_mode": str(role_rotation.get("mode", "by_symbol")).strip().lower(),
            "multi_judge_enabled": bool(multi_judge.get("enabled", False)),
            "judge_candidates": [str(x).strip().lower() for x in judges if str(x).strip()],
            "consensus_rule": str(multi_judge.get("consensus", "majority")).strip().lower(),
        }

    def _init_brain(self, key, conf, env_prefix="LLM"):
        if not isinstance(conf, dict):
            return
        setting = resolve_brain_settings(
            key,
            secure=self.secure if isinstance(self.secure, dict) else {},
            conf=self.config if isinstance(self.config, dict) else {},
            load_environment=False,
        )
        api_key = self._clean_key(setting.get("api_key"))
        base_url = setting.get("base_url")
        model = setting.get("model")
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
            "base_url": base_url,
            "sources": {
                "api_key": setting.get("api_key_source", "missing"),
                "base_url": setting.get("base_url_source", "missing"),
                "model": setting.get("model_source", "missing"),
            },
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

    def _recover_side_output(self, mode, side, raw_content, error_msg=""):
        side = "blue" if str(side).lower() == "blue" else "red"
        side_key = f"{side}_view"
        raw_text = str(raw_content or "").strip()
        err = str(error_msg or "").strip()

        # Prefer extracting any usable JSON fragment first.
        parsed = None
        if raw_text and not raw_text.startswith("ERROR:"):
            parsed, _ = parse_json_safe(raw_text)
        if isinstance(parsed, dict):
            out = dict(parsed)
        else:
            fallback_view = ""
            if raw_text:
                fallback_view = raw_text.replace("\r", " ").replace("\n", " ").strip()
            if not fallback_view:
                fallback_view = err or "模型未返回可解析内容"
            if len(fallback_view) > 300:
                fallback_view = fallback_view[:300] + "..."

            if mode == "morning":
                out = {
                    "core_view": fallback_view,
                    "action": "HOLD",
                    "risk_warning": "该轮输出异常，已降级处理",
                    "blue_view": "",
                    "red_view": "",
                    "final_verdict": fallback_view,
                    "bull_bear_power": {"bull": 50, "bear": 50},
                }
            else:
                out = {
                    "scores": {
                        "capital": 50, "technical": 50, "macro": 50, "news": 50,
                        "memory": 50, "knowledge": 50, "total": 50,
                        "reason": "该轮输出异常，已降级处理"
                    },
                    "action": "HOLD",
                    "core_view": fallback_view,
                    "risk_warning": "该轮输出异常，已降级处理",
                    "grid_strategy": {},
                    "scenarios": [],
                    "feature_weights": {},
                    "blue_view": "",
                    "red_view": "",
                    "final_verdict": fallback_view,
                }

        if not str(out.get(side_key, "")).strip():
            fill = self._extract_view(out, "core_view")
            if not fill:
                fill = err or "模型输出异常"
            out[side_key] = fill
        if err:
            warn = str(out.get("risk_warning", "") or "").strip()
            out["risk_warning"] = (warn + " | " if warn else "") + f"{side}脑异常: {err}"
        return out

    def _call_brain(self, brain_key, sys_prompt, user_prompt, mode, temperature=0.2):
        brain = self.brains.get(brain_key)
        if not brain:
            return None, None
        try:
            temperature = float(temperature)
        except Exception:
            temperature = 0.2
        def _invoke(temp):
            res = brain["client"].chat.completions.create(
                model=brain["model"],
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
                temperature=temp
            )
            raw_content = res.choices[0].message.content
            data, cleaned = parse_json_safe(raw_content)
            log_llm(f"{mode}_{brain_key}", brain.get("model", ""), raw_content, cleaned, ok=bool(data))
            return data, raw_content

        try:
            return _invoke(temperature)
        except Exception as exc:
            msg = str(exc)
            # Some providers only accept temperature=1; retry once automatically.
            if "invalid temperature" in msg.lower() and "only 1 is allowed" in msg.lower() and abs(float(temperature) - 1.0) > 1e-9:
                try:
                    return _invoke(1.0)
                except Exception as exc_retry:
                    msg = str(exc_retry)
            try:
                log_llm(f"{mode}_{brain_key}", brain.get("model", ""), f"ERROR: {msg}", "", ok=False)
            except Exception:
                pass
            return None, f"ERROR: {msg}"

    def _debate_runtime_config(self, mode="stock"):
        cfg = dict(self.debate_cfg or {})
        if mode == "morning":
            # morning session can be faster while still keeping multi-round capability
            cfg["rounds"] = max(1, min(2, int(cfg.get("rounds", 2) or 2)))
        return cfg

    def _resolve_role_map(self, payload, cfg):
        role_map = {
            "pro": "blue",
            "con": "red",
            "judge": "green",
            "swapped": False,
            "rotation_basis": "",
        }
        if not cfg.get("role_rotation_enabled"):
            return role_map
        if not all(k in self.brains for k in ["blue", "red"]):
            return role_map

        stock_code = ""
        for k in ["stock_code", "code", "ts_code", "symbol"]:
            v = payload.get(k) if isinstance(payload, dict) else ""
            if v:
                stock_code = str(v).strip().upper()
                break
        if not stock_code:
            stock_code = json.dumps(payload, ensure_ascii=False, default=str)[:120]
        role_map["rotation_basis"] = stock_code
        hashed = hashlib.md5(stock_code.encode("utf-8")).hexdigest()
        swapped = int(hashed[-1], 16) % 2 == 1
        if swapped:
            role_map["pro"] = "red"
            role_map["con"] = "blue"
            role_map["swapped"] = True
        return role_map

    def _phase_instruction(self, phase, mode, semantic_role):
        if mode == "morning":
            if phase == 1:
                return (
                    "Round1 Initial Position. Output JSON with keys: "
                    "core_view, action, risk_warning, thesis, assumptions, key_evidence, risk_scenarios."
                )
            if phase == 2:
                return (
                    "Round2 Cross-Examination. Respond to opponent claims point-by-point. "
                    "Output JSON with keys: core_view, action, rebuttals, admitted_uncertainties, added_evidence."
                )
            return (
                "Round3 Final Statement. Provide revised final stance after debate. "
                "Output JSON with keys: core_view, action, final_thesis, trigger_conditions, risk_warning."
            )

        if phase == 1:
            return (
                f"Round1 Initial Position ({semantic_role}). "
                "Build complete argument with thesis, assumptions, valuation view, scenario forecast, "
                "risk checklist and action hint. Output valid JSON."
            )
        if phase == 2:
            return (
                f"Round2 Cross-Examination ({semantic_role}). "
                "Address every opponent challenge: rebut, accept uncertainty, or revise thesis. "
                "Add new evidence when possible. Output valid JSON."
            )
        return (
            f"Round3 Final Statement ({semantic_role}). "
            "Produce best revised version after debate, clearly listing changed assumptions and final conditions. "
            "Output valid JSON."
        )

    def _build_round_prompt(self, payload, phase, mode, semantic_role, own_prev=None, opp_prev=None, rule_prefix=""):
        instruction = self._phase_instruction(phase, mode, semantic_role)
        body = [f"{rule_prefix}[CONTEXT]{json.dumps(payload, ensure_ascii=False, default=str)}"]
        if own_prev:
            body.append(f"[YOUR_PREVIOUS]{json.dumps(own_prev, ensure_ascii=False, default=str)}")
        if opp_prev:
            body.append(f"[OPPONENT_PREVIOUS]{json.dumps(opp_prev, ensure_ascii=False, default=str)}")
        body.append(f"[TASK]{instruction}")
        return "\n".join(body)

    def _select_judges(self, cfg, role_map):
        if cfg.get("multi_judge_enabled"):
            order = cfg.get("judge_candidates", []) or ["green"]
        else:
            order = [role_map.get("judge", "green")]

        selected = []
        for key in order:
            k = str(key).strip().lower()
            if not k or k in selected:
                continue
            if k in self.brains:
                selected.append(k)
        if not selected:
            fallback = role_map.get("judge", "green")
            if fallback in self.brains:
                selected = [fallback]
            else:
                selected = [next(iter(self.brains.keys()))]
        return selected

    def _aggregate_judge_results(self, results, mode, judge_keys):
        valid = []
        for item in results:
            if not isinstance(item, dict):
                continue
            valid.append(validate_debate(item, mode=mode))
        if not valid:
            return None, {}

        if len(valid) == 1:
            out = dict(valid[0])
            out["consensus"] = {
                "judge_count": 1,
                "judge_keys": judge_keys[:1],
                "action_votes": {str(out.get("action", "HOLD")).upper(): 1},
                "consensus_action": str(out.get("action", "HOLD")).upper(),
                "disagreement": False,
            }
            return out, out["consensus"]

        votes = Counter([str(v.get("action", "HOLD")).upper() for v in valid])
        consensus_action, vote_count = votes.most_common(1)[0]
        disagreement = len(votes) > 1

        candidates = [v for v in valid if str(v.get("action", "HOLD")).upper() == consensus_action]
        if not candidates:
            candidates = valid
        out = dict(candidates[0])
        out["action"] = consensus_action

        if mode == "stock":
            score_keys = ["capital", "technical", "macro", "news", "memory", "knowledge", "total"]
            merged = {}
            for key in score_keys:
                vals = []
                for c in valid:
                    s = c.get("scores", {})
                    if isinstance(s, dict):
                        try:
                            vals.append(float(s.get(key)))
                        except Exception:
                            pass
                if vals:
                    merged[key] = round(sum(vals) / len(vals), 2)
            reason_pool = []
            for c in valid:
                s = c.get("scores", {})
                if isinstance(s, dict) and s.get("reason"):
                    reason_pool.append(str(s.get("reason")))
            merged["reason"] = " | ".join(reason_pool[:2]) if reason_pool else out.get("scores", {}).get("reason", "")
            if isinstance(out.get("scores"), dict):
                out_scores = dict(out.get("scores"))
                out_scores.update(merged)
                out["scores"] = out_scores

        verdicts = []
        for c in valid:
            text = str(c.get("final_verdict", "")).strip()
            if text and text not in verdicts:
                verdicts.append(text)
        if verdicts:
            out["final_verdict"] = " | ".join(verdicts[:3])

        consensus = {
            "judge_count": len(valid),
            "judge_keys": judge_keys[: len(valid)],
            "action_votes": dict(votes),
            "consensus_action": consensus_action,
            "vote_count": vote_count,
            "disagreement": disagreement,
        }
        out["consensus"] = consensus
        return out, consensus

    def _run_multi_round_debate(self, payload, mode, sys_prompt, rule_prefix, cfg, role_map):
        pro_key = role_map.get("pro", "blue")
        con_key = role_map.get("con", "red")
        rounds = int(cfg.get("rounds", 3) or 3)
        temperature = float(cfg.get("temperature", 0.2) or 0.2)

        pro_rounds = []
        con_rounds = []
        trace = []

        for phase in range(1, rounds + 1):
            pro_prompt = self._build_round_prompt(
                payload,
                phase,
                mode,
                semantic_role="bullish/constructive",
                own_prev=pro_rounds[-1] if pro_rounds else None,
                opp_prev=con_rounds[-1] if con_rounds else None,
                rule_prefix=rule_prefix,
            )
            con_prompt = self._build_round_prompt(
                payload,
                phase,
                mode,
                semantic_role="bearish/defensive",
                own_prev=con_rounds[-1] if con_rounds else None,
                opp_prev=pro_rounds[-1] if pro_rounds else None,
                rule_prefix=rule_prefix,
            )
            pro_data, pro_raw = self._call_brain(
                pro_key,
                self._get_role_prompt("blue", sys_prompt),
                pro_prompt,
                mode,
                temperature=temperature,
            )
            if pro_data is None:
                pro_data = self._recover_side_output(mode, "blue", pro_raw)

            con_data, con_raw = self._call_brain(
                con_key,
                self._get_role_prompt("red", sys_prompt),
                con_prompt,
                mode,
                temperature=temperature,
            )
            if con_data is None:
                con_data = self._recover_side_output(mode, "red", con_raw)

            pro_rounds.append(pro_data or {})
            con_rounds.append(con_data or {})
            trace.append(
                {
                    "round": phase,
                    "pro_model": pro_key,
                    "con_model": con_key,
                    "pro": pro_data or {},
                    "con": con_data or {},
                }
            )

        judge_ctx = dict(payload)
        judge_ctx["debate_rounds"] = trace
        judge_ctx["pro_final"] = pro_rounds[-1] if pro_rounds else {}
        judge_ctx["con_final"] = con_rounds[-1] if con_rounds else {}
        judge_prompt = (
            f"{rule_prefix}[CONTEXT]{json.dumps(judge_ctx, ensure_ascii=False, default=str)}\n"
            "[TASK]You are the final judge. Use all rounds and output JSON only with final decision schema."
        )

        judge_keys = self._select_judges(cfg, role_map)
        judge_out = []
        for key in judge_keys:
            data, _ = self._call_brain(
                key,
                self._get_role_prompt("green", sys_prompt),
                judge_prompt,
                mode,
                temperature=temperature,
            )
            if data is not None:
                judge_out.append(data)

        merged, consensus = self._aggregate_judge_results(judge_out, mode, judge_keys)
        if merged is None:
            fallback = pro_rounds[-1] if pro_rounds and pro_rounds[-1] else (con_rounds[-1] if con_rounds else {})
            merged = validate_debate(fallback, mode=mode) if fallback else self._fallback_result(mode, "LLM error")
            consensus = {"judge_count": 0, "judge_keys": judge_keys, "action_votes": {}, "consensus_action": "HOLD", "disagreement": False}

        merged["blue_view"] = self._extract_view(pro_rounds[-1] if pro_rounds else {}, "blue_view")
        merged["red_view"] = self._extract_view(con_rounds[-1] if con_rounds else {}, "red_view")
        merged["debate_meta"] = {
            "rounds": rounds,
            "role_assignment": {
                "pro_model": pro_key,
                "con_model": con_key,
                "judge_models": judge_keys,
                "rotation_enabled": bool(cfg.get("role_rotation_enabled")),
                "swapped": bool(role_map.get("swapped", False)),
                "rotation_basis": role_map.get("rotation_basis", ""),
            },
            "consensus": consensus,
        }
        merged["debate_trace"] = trace
        return merged

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

        # iterative multi-round debate (requires at least blue/red)
        runtime_cfg = self._debate_runtime_config(mode=mode)
        if runtime_cfg.get("enabled", True) and all(k in self.brains for k in ["blue", "red"]):
            role_map = self._resolve_role_map(payload, runtime_cfg)
            result = self._run_multi_round_debate(
                payload=payload,
                mode=mode,
                sys_prompt=sys_prompt,
                rule_prefix=rule_prefix,
                cfg=runtime_cfg,
                role_map=role_map,
            )
            if isinstance(result, dict):
                return self._normalize_action(result)

        # fallback to single brain
        primary = "blue" if "blue" in self.brains else ("red" if "red" in self.brains else ("green" if "green" in self.brains else "default"))
        data, _ = self._call_brain(
            primary,
            sys_prompt,
            user_prompt,
            mode,
            temperature=float(runtime_cfg.get("temperature", 0.2) or 0.2),
        )
        if data is None:
            return self._fallback_result(mode, "LLM error")
        result = validate_debate(data, mode=mode)
        return self._normalize_action(result)
