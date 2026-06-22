import datetime
import json
import os
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List

import yaml

from core.env_loader import load_env
from core.logger import exception, warn
from core.llm_resolver import resolve_preferred_settings
from agentlightning import LitAgent


CONFIG_PATH = "config/agent_lightning.json"
DEFAULT_REPORT_PATH = "data/agent_lightning_report.jsonl"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _default_config():
    return {
        "enabled": False,
        "dev_mode": True,
        "n_workers": 1,
        "max_tasks": 20,
        "task_source": "watchlist",
        "custom_codes": [],
        "mode": "stock",
        "reward_mode": "score_total",
        "risk_level_mode": "risk_assessment",
        "override_action_by_score": False,
        "buy_threshold": 62.0,
        "sell_threshold": 50.0,
        "disable_news": True,
        "paper_execute": False,
        "report_path": DEFAULT_REPORT_PATH
    }


def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        return _default_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_config()
        merged = _default_config()
        merged.update(data)
        return merged
    except Exception as exc:
        exception("agent_lightning.config_load_failed", exc, {"path": path})
        return _default_config()


def save_config(cfg, path=CONFIG_PATH):
    cfg = cfg if isinstance(cfg, dict) else _default_config()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        exception("agent_lightning.config_save_failed", exc, {"path": path})
        return False


def _load_llm_config():
    path = "config/llm_config.yaml"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_llm_settings():
    load_env()
    conf = _load_llm_config()
    setting = resolve_preferred_settings(
        preferred=("blue", "general"),
        conf=conf,
        load_environment=False,
    )
    return {
        "api_key": setting.get("api_key", ""),
        "base_url": setting.get("base_url", ""),
        "model": setting.get("model", ""),
    }


def _normalize_codes(entries):
    out = []
    seen = set()
    for item in entries or []:
        code = None
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
        elif isinstance(item, str):
            code = item
        if not code:
            continue
        code = str(code).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _select_codes(cfg):
    source = str(cfg.get("task_source") or "watchlist").strip().lower()
    max_tasks = int(cfg.get("max_tasks", 20) or 20)
    if source == "custom":
        codes = _normalize_codes(cfg.get("custom_codes", []))
        return codes[:max_tasks]
    from skills.scanner import MarketScanner
    scanner = MarketScanner()
    pool = scanner.get_candidate_pool(mode="watchlist", limit=max_tasks)
    codes = _normalize_codes(pool)
    return codes[:max_tasks]


def _append_report(record, path=None):
    path = path or DEFAULT_REPORT_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _summarize_report(run_id, path=None):
    path = path or DEFAULT_REPORT_PATH
    if not os.path.exists(path):
        return {}
    total = 0
    reward_sum = 0.0
    reward_min = None
    reward_max = None
    score_sum = 0.0
    score_count = 0
    actions = {}
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
                if run_id and str(rec.get("run_id")) != str(run_id):
                    continue
                total += 1
                reward = rec.get("reward")
                try:
                    reward = float(reward)
                except Exception:
                    reward = None
                if reward is not None:
                    reward_sum += reward
                    reward_min = reward if reward_min is None else min(reward_min, reward)
                    reward_max = reward if reward_max is None else max(reward_max, reward)
                score = rec.get("score_total")
                try:
                    score = float(score)
                    score_sum += score
                    score_count += 1
                except Exception:
                    pass
                action = str(rec.get("action") or "HOLD").upper()
                actions[action] = actions.get(action, 0) + 1
    except Exception:
        return {}
    avg_reward = reward_sum / total if total else 0.0
    avg_score = score_sum / score_count if score_count else 0.0
    return {
        "tasks": total,
        "avg_reward": avg_reward,
        "min_reward": reward_min,
        "max_reward": reward_max,
        "avg_score_total": avg_score,
        "actions": actions
    }


def _iter_report_records(path=None, run_id=None):
    path = path or DEFAULT_REPORT_PATH
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
                if run_id and str(rec.get("run_id")) != str(run_id):
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception:
        return []
    return out


def compare_agent_lightning_runs(path=None, limit=20):
    records = _iter_report_records(path=path)
    if not records:
        return {"runs": []}
    grouped = {}
    for rec in records:
        rid = str(rec.get("run_id") or "unknown")
        g = grouped.setdefault(
            rid,
            {
                "run_id": rid,
                "tasks": 0,
                "reward_sum": 0.0,
                "reward_count": 0,
                "score_sum": 0.0,
                "score_count": 0,
                "actions": {},
                "errors": 0,
                "ts_first": None,
                "ts_last": None,
            },
        )
        g["tasks"] += 1
        ts = rec.get("ts")
        if ts:
            if not g["ts_first"] or str(ts) < str(g["ts_first"]):
                g["ts_first"] = ts
            if not g["ts_last"] or str(ts) > str(g["ts_last"]):
                g["ts_last"] = ts
        reward = rec.get("reward")
        try:
            g["reward_sum"] += float(reward)
            g["reward_count"] += 1
        except Exception:
            pass
        score = rec.get("score_total")
        try:
            g["score_sum"] += float(score)
            g["score_count"] += 1
        except Exception:
            pass
        action = str(rec.get("action") or "HOLD").upper()
        g["actions"][action] = g["actions"].get(action, 0) + 1
        if rec.get("error"):
            g["errors"] += 1

    rows = []
    for _, g in grouped.items():
        avg_reward = g["reward_sum"] / g["reward_count"] if g["reward_count"] else 0.0
        avg_score = g["score_sum"] / g["score_count"] if g["score_count"] else 0.0
        rows.append(
            {
                "run_id": g["run_id"],
                "tasks": g["tasks"],
                "avg_reward": avg_reward,
                "avg_score_total": avg_score,
                "actions": g["actions"],
                "errors": g["errors"],
                "ts_first": g["ts_first"],
                "ts_last": g["ts_last"],
            }
        )
    rows.sort(key=lambda x: (x["avg_reward"], x["tasks"]), reverse=True)
    return {"runs": rows[: max(1, int(limit))]}


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except Exception:
        return float(default)


def _risk_level(val):
    if not isinstance(val, str):
        return ""
    text = val.strip()
    if not text:
        return ""
    return text.split()[0].upper()


def _risk_level_from_score(score):
    try:
        score = float(score)
    except Exception:
        return ""
    if score >= 50:
        return "HIGH"
    if score >= 15:
        return "MEDIUM"
    return "LOW"


def _compute_reward(score_total, risk_level, mode="score_total"):
    base = _safe_float(score_total, 0.0) / 100.0
    if mode == "score_risk_adjusted":
        penalty = 0.0
        if risk_level == "HIGH":
            penalty = -0.3
        elif risk_level == "MEDIUM":
            penalty = -0.1
        reward = base + penalty
    else:
        reward = base
    return max(-1.0, min(1.0, reward))


def _override_action(score_total, risk_level, buy_threshold, sell_threshold):
    try:
        score = float(score_total)
    except Exception:
        score = 0.0
    try:
        buy_thr = float(buy_threshold)
    except Exception:
        buy_thr = 62.0
    try:
        sell_thr = float(sell_threshold)
    except Exception:
        sell_thr = 50.0
    if score >= buy_thr and risk_level != "HIGH":
        return "BUY"
    if score <= sell_thr:
        return "SELL"
    return "HOLD"


def _compute_style_penalty(
    actions,
    total_count,
    target_trade_ratio=0.35,
    trade_ratio_weight=0.25,
    max_hold_ratio=0.80,
    hold_excess_weight=0.35,
    min_buy_ratio=0.10,
    buy_shortfall_weight=0.25,
):
    total_count = max(1, int(total_count or 0))
    buy_count = int(actions.get("BUY", 0) or 0)
    sell_count = int(actions.get("SELL", 0) or 0)
    hold_count = int(actions.get("HOLD", 0) or 0)

    buy_ratio = buy_count / total_count
    sell_ratio = sell_count / total_count
    hold_ratio = hold_count / total_count
    trade_ratio = max(0.0, min(1.0, 1.0 - hold_ratio))

    target_trade_ratio = max(0.0, min(1.0, _safe_float(target_trade_ratio, 0.35)))
    trade_ratio_weight = max(0.0, _safe_float(trade_ratio_weight, 0.25))
    max_hold_ratio = max(0.0, min(1.0, _safe_float(max_hold_ratio, 0.80)))
    hold_excess_weight = max(0.0, _safe_float(hold_excess_weight, 0.35))
    min_buy_ratio = max(0.0, min(1.0, _safe_float(min_buy_ratio, 0.10)))
    buy_shortfall_weight = max(0.0, _safe_float(buy_shortfall_weight, 0.25))

    penalty = abs(trade_ratio - target_trade_ratio) * trade_ratio_weight
    if hold_ratio > max_hold_ratio:
        penalty += (hold_ratio - max_hold_ratio) * hold_excess_weight
    if buy_ratio < min_buy_ratio:
        penalty += (min_buy_ratio - buy_ratio) * buy_shortfall_weight

    return {
        "penalty": penalty,
        "buy_ratio": buy_ratio,
        "sell_ratio": sell_ratio,
        "hold_ratio": hold_ratio,
        "trade_ratio": trade_ratio,
    }


def tune_thresholds_from_report(
    path=None,
    run_id=None,
    reward_mode="score_risk_adjusted",
    buy_min=55,
    buy_max=75,
    sell_min=40,
    sell_max=60,
    min_gap=5,
    trade_penalty=0.02,
    high_risk_buy_penalty=0.08,
    balance_mode="balanced",
    target_trade_ratio=0.35,
    trade_ratio_weight=0.25,
    max_hold_ratio=0.80,
    hold_excess_weight=0.35,
    min_buy_ratio=0.10,
    buy_shortfall_weight=0.25,
):
    records = _iter_report_records(path=path, run_id=run_id)
    sample = []
    for rec in records:
        score = rec.get("score_total")
        try:
            score = float(score)
        except Exception:
            continue
        risk = _risk_level(rec.get("risk_level"))
        sample.append({"score_total": score, "risk_level": risk})
    if not sample:
        return {"ok": False, "error": "no_valid_samples"}

    try:
        buy_min = int(buy_min)
        buy_max = int(buy_max)
        sell_min = int(sell_min)
        sell_max = int(sell_max)
        min_gap = int(min_gap)
    except Exception:
        return {"ok": False, "error": "invalid_threshold_range"}

    trade_penalty = _safe_float(trade_penalty, 0.02)
    high_risk_buy_penalty = _safe_float(high_risk_buy_penalty, 0.08)
    balance_mode = str(balance_mode or "balanced").strip().lower()

    top = []
    for buy_thr in range(buy_min, buy_max + 1):
        for sell_thr in range(sell_min, sell_max + 1):
            if buy_thr - sell_thr < min_gap:
                continue
            utility_sum = 0.0
            actions = {"BUY": 0, "SELL": 0, "HOLD": 0}
            for rec in sample:
                score = rec["score_total"]
                risk = rec["risk_level"]
                action = _override_action(score, risk, buy_thr, sell_thr)
                actions[action] = actions.get(action, 0) + 1
                utility = _compute_reward(score, risk, mode=reward_mode)
                if action != "HOLD":
                    utility -= trade_penalty
                if action == "BUY" and risk == "HIGH":
                    utility -= high_risk_buy_penalty
                utility_sum += utility
            avg_utility = utility_sum / len(sample)
            style = _compute_style_penalty(
                actions,
                len(sample),
                target_trade_ratio=target_trade_ratio,
                trade_ratio_weight=trade_ratio_weight,
                max_hold_ratio=max_hold_ratio,
                hold_excess_weight=hold_excess_weight,
                min_buy_ratio=min_buy_ratio,
                buy_shortfall_weight=buy_shortfall_weight,
            )
            style_penalty = style["penalty"] if balance_mode == "balanced" else 0.0
            objective = avg_utility - style_penalty
            item = {
                "buy_threshold": float(buy_thr),
                "sell_threshold": float(sell_thr),
                "avg_utility": avg_utility,
                "style_penalty": style_penalty,
                "objective": objective,
                "ratios": {
                    "buy": style["buy_ratio"],
                    "sell": style["sell_ratio"],
                    "hold": style["hold_ratio"],
                    "trade": style["trade_ratio"],
                },
                "actions": actions,
            }
            top.append(item)

    if not top:
        return {"ok": False, "error": "no_threshold_candidates"}
    top.sort(key=lambda x: x["objective"], reverse=True)
    return {
        "ok": True,
        "sample_size": len(sample),
        "reward_mode": reward_mode,
        "trade_penalty": trade_penalty,
        "high_risk_buy_penalty": high_risk_buy_penalty,
        "balance_mode": balance_mode,
        "balance_config": {
            "target_trade_ratio": target_trade_ratio,
            "trade_ratio_weight": trade_ratio_weight,
            "max_hold_ratio": max_hold_ratio,
            "hold_excess_weight": hold_excess_weight,
            "min_buy_ratio": min_buy_ratio,
            "buy_shortfall_weight": buy_shortfall_weight,
        },
        "best": top[0],
        "top_candidates": top[:10],
    }


def _build_resources(cfg):
    resources = {}
    prompt_mode = str(cfg.get("mode") or "stock").strip().lower()
    try:
        from core.tri_brain import TriBrainCouncil
        council = TriBrainCouncil()
        if prompt_mode == "morning":
            prompt = council._get_morning_prompt()
        else:
            prompt = council._get_stock_prompt()
        if prompt:
            from agentlightning import PromptTemplate
            resources["system_prompt"] = PromptTemplate(template=prompt, engine="f-string")
    except Exception:
        pass
    try:
        settings = _resolve_llm_settings()
        model = settings.get("model")
        if model:
            from agentlightning import LLM
            endpoint = settings.get("base_url") or "https://api.openai.com/v1"
            kwargs = {
                "endpoint": endpoint,
                "model": model,
                "sampling_parameters": {"temperature": float(cfg.get("temperature", 0.2) or 0.2)},
            }
            if settings.get("api_key"):
                kwargs["api_key"] = settings.get("api_key")
            resources["main_llm"] = LLM(**kwargs)
    except Exception:
        pass
    return resources


class _NullTracer:
    def __init__(self, *args, **kwargs):
        pass

    def init(self, *args, **kwargs):
        return None

    def init_worker(self, worker_id: int, *args, **kwargs):
        return None

    def teardown_worker(self, worker_id: int, *args, **kwargs):
        return None

    def teardown(self, *args, **kwargs):
        return None

    @contextmanager
    def trace_context(self, name=None):
        yield None

    def get_last_trace(self):
        return []


class LightningEvalAgent(LitAgent):
    def __init__(self, cfg, run_id):
        super().__init__()
        self.cfg = cfg
        self.run_id = run_id
        from core.cognitive_graph import build_cognitive_graph
        self.app = build_cognitive_graph()
        self.report_path = cfg.get("report_path") or DEFAULT_REPORT_PATH
        self.disable_news = bool(cfg.get("disable_news", True))
        self.paper_execute = bool(cfg.get("paper_execute", False))
        self.reward_mode = str(cfg.get("reward_mode") or "score_total").strip().lower()
        self.risk_level_mode = str(cfg.get("risk_level_mode") or "risk_assessment").strip().lower()
        self.override_action = bool(cfg.get("override_action_by_score", False))
        self.buy_threshold = cfg.get("buy_threshold", 62.0)
        self.sell_threshold = cfg.get("sell_threshold", 50.0)
        self.run_cfg = {
            "reward_mode": self.reward_mode,
            "risk_level_mode": self.risk_level_mode,
            "override_action_by_score": self.override_action,
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "disable_news": self.disable_news,
            "paper_execute": self.paper_execute,
        }

    def training_rollout(self, task, rollout_id, resources):
        code = None
        if isinstance(task, dict):
            code = task.get("stock_code") or task.get("code")
        elif isinstance(task, str):
            code = task
        code = str(code or "").strip().upper()
        if not code:
            return 0.0

        state = {
            "stock_code": code,
            "messages": [],
            "paper_execute": self.paper_execute,
            "source_info": {"source": "agent_lightning", "label": "AgentLightning"}
        }
        if self.disable_news:
            state["news_data"] = []
            state["macro_news"] = []
            state["tool_tasks"] = []
        if isinstance(task, dict):
            for k, v in task.items():
                if k not in state:
                    state[k] = v

        error = ""
        score_total = 0.0
        action = "HOLD"
        raw_action = ""
        risk_level = ""
        critic_score = None
        reward = 0.0
        decision_id = ""
        try:
            res = self.app.invoke(state)
            sig = res.get("trading_signal", {}) if isinstance(res, dict) else {}
            raw_action = str(sig.get("action") or "HOLD").upper()
            action = raw_action
            details = sig.get("details", {}) if isinstance(sig.get("details"), dict) else {}
            scores = details.get("scores", {}) if isinstance(details.get("scores"), dict) else {}
            score_total = _safe_float(scores.get("total"), 0.0)
            risk_level = _risk_level(res.get("risk_assessment"))
            if self.risk_level_mode == "critic":
                critic = res.get("critic_report", {}) if isinstance(res, dict) else {}
                if isinstance(critic, dict):
                    critic_score = critic.get("score")
                    derived = _risk_level_from_score(critic_score)
                    # fallback to risk_assessment when critic score is missing or zeroed
                    if derived:
                        risk_level = derived
            if self.override_action:
                action = _override_action(score_total, risk_level, self.buy_threshold, self.sell_threshold)
            reward = _compute_reward(score_total, risk_level, mode=self.reward_mode)
            decision_id = str(sig.get("decision_id") or res.get("decision_id") or "")
        except Exception as exc:
            error = str(exc)
            warn("agent_lightning.rollout_failed", {"error": error, "code": code})
            reward = 0.0

        record = {
            "ts": _now(),
            "run_id": self.run_id,
            "rollout_id": rollout_id,
            "stock_code": code,
            "action": action,
            "action_raw": raw_action,
            "score_total": score_total,
            "risk_level": risk_level,
            "risk_mode": self.risk_level_mode,
            "critic_score": critic_score,
            "reward": reward,
            "decision_id": decision_id,
            "cfg": self.run_cfg,
            "error": error
        }
        _append_report(record, path=self.report_path)
        return reward


def run_agent_lightning(cfg=None):
    cfg = cfg if isinstance(cfg, dict) else load_config()
    if not cfg.get("enabled"):
        return {"ok": False, "error": "agent_lightning_disabled"}
    try:
        from agentlightning import DevTaskLoader, Trainer, Task
    except Exception as exc:
        return {"ok": False, "error": f"agentlightning_import_failed:{exc}"}

    codes = _select_codes(cfg)
    if not codes:
        return {"ok": False, "error": "no_tasks"}

    run_id = uuid.uuid4().hex
    tasks = [
        Task(rollout_id=f"{code}_{run_id[:6]}", input={"stock_code": code})
        for code in codes
    ]
    resources = _build_resources(cfg)
    loader = DevTaskLoader(tasks=tasks, resources=resources)

    n_workers = int(cfg.get("n_workers", 1) or 1)
    max_tasks = int(cfg.get("max_tasks", len(tasks)) or len(tasks))
    trainer = Trainer(
        dev=bool(cfg.get("dev_mode", True)),
        n_workers=n_workers,
        max_tasks=max_tasks,
        tracer="core.agent_lightning_adapter._NullTracer"
    )
    agent = LightningEvalAgent(cfg, run_id)
    trainer.fit(agent=agent, backend=loader, dev_backend=loader)

    summary = _summarize_report(run_id, path=cfg.get("report_path") or DEFAULT_REPORT_PATH)
    return {"ok": True, "run_id": run_id, "summary": summary}


def agent_lightning_run_tool(args=None):
    args = args if isinstance(args, dict) else {}
    cfg = load_config()
    overrides = args.get("config") if isinstance(args.get("config"), dict) else args
    if isinstance(overrides, dict):
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return run_agent_lightning(cfg)


def agent_lightning_tune_tool(args=None):
    args = args if isinstance(args, dict) else {}
    path = args.get("report_path") or DEFAULT_REPORT_PATH
    return tune_thresholds_from_report(
        path=path,
        run_id=args.get("run_id"),
        reward_mode=args.get("reward_mode", "score_risk_adjusted"),
        buy_min=args.get("buy_min", 55),
        buy_max=args.get("buy_max", 75),
        sell_min=args.get("sell_min", 40),
        sell_max=args.get("sell_max", 60),
        min_gap=args.get("min_gap", 5),
        trade_penalty=args.get("trade_penalty", 0.02),
        high_risk_buy_penalty=args.get("high_risk_buy_penalty", 0.08),
        balance_mode=args.get("balance_mode", "balanced"),
        target_trade_ratio=args.get("target_trade_ratio", 0.35),
        trade_ratio_weight=args.get("trade_ratio_weight", 0.25),
        max_hold_ratio=args.get("max_hold_ratio", 0.80),
        hold_excess_weight=args.get("hold_excess_weight", 0.35),
        min_buy_ratio=args.get("min_buy_ratio", 0.10),
        buy_shortfall_weight=args.get("buy_shortfall_weight", 0.25),
    )


def agent_lightning_compare_tool(args=None):
    args = args if isinstance(args, dict) else {}
    path = args.get("report_path") or DEFAULT_REPORT_PATH
    limit = int(args.get("limit", 20) or 20)
    return compare_agent_lightning_runs(path=path, limit=limit)


def register_agent_lightning_tool(registry=None):
    from core.tool_registry import get_registry
    registry = registry or get_registry()
    registry.register(
        "agent_lightning_run",
        agent_lightning_run_tool,
        meta={
            "kind": "optimizer",
            "description": "Run Agent Lightning evaluation tasks (dev-mode local runner)."
        }
    )
    registry.register(
        "agent_lightning_tune",
        agent_lightning_tune_tool,
        meta={
            "kind": "optimizer",
            "description": "Tune Agent Lightning buy/sell thresholds from historical report data.",
        },
    )
    registry.register(
        "agent_lightning_compare",
        agent_lightning_compare_tool,
        meta={
            "kind": "optimizer",
            "description": "Compare Agent Lightning runs by avg reward / score / actions.",
        },
    )
    return registry
