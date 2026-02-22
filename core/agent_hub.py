import time

from core.agent_protocol import build_agent_report, emit_agent_report, new_run_id
from core.event_bus import EventBus
from core.metrics import compute_loop_health
from core.strategy_governor import build_governor_report, update_strategy_rewards
from core.experience_feedback import update_bias
from core.threshold_adaptor import maybe_update_overrides
from core.world_model import WorldModel
from core.event_index import update_index


class BaseAgent:
    agent_id = "base"
    agent_type = "base"
    version = "1.0"

    def run(self, context):
        raise NotImplementedError

    def _report(self, status, summary="", details=None, metrics=None, recommendations=None, tags=None, run_id=None):
        return build_agent_report(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=status,
            summary=summary,
            details=details,
            metrics=metrics,
            recommendations=recommendations,
            tags=tags,
            run_id=run_id,
            version=self.version
        )


class DataHealthAgent(BaseAgent):
    agent_id = "data_health"
    agent_type = "data_health"

    def run(self, context):
        try:
            wm = WorldModel()
            health = wm.check_health()
            details = health.get("details", {}) if isinstance(health, dict) else {}
            healthy = bool(health.get("healthy")) if isinstance(health, dict) else False
            status = "ok" if healthy else "fail"
            metrics = {
                "network": 1 if details.get("network") else 0,
                "market_open": 1 if details.get("market_open") else 0,
                "api_connectivity": 1 if details.get("api_connectivity") else 0
            }
            summary = f"network={metrics['network']}, market_open={metrics['market_open']}, api={metrics['api_connectivity']}"
            recs = []
            if not healthy:
                recs.append("Check network/API tokens and market calendar.")
            return self._report(status, summary, details=health, metrics=metrics, recommendations=recs, run_id=context.get("run_id"))
        except Exception as exc:
            return self._report("fail", f"exception: {exc}", details={"error": str(exc)}, run_id=context.get("run_id"))


class StrategyReviewAgent(BaseAgent):
    agent_id = "strategy_review"
    agent_type = "strategy_review"

    def run(self, context):
        try:
            days = context.get("days", 60)
            gov = build_governor_report(days=days)
            strategies = gov.get("strategies", {}) if isinstance(gov, dict) else {}
            counts = {"active": 0, "watch": 0, "disabled": 0, "seed": 0}
            for s in strategies.values():
                status = str(s.get("status") or "seed").lower()
                if status in counts:
                    counts[status] += 1
                else:
                    counts["seed"] += 1
            total = sum(counts.values())
            status = "idle" if total == 0 else ("warn" if counts.get("disabled", 0) > 0 else "ok")
            summary = f"strategies={total}, active={counts['active']}, watch={counts['watch']}, disabled={counts['disabled']}, seed={counts['seed']}"
            details = {
                "updated_at": gov.get("updated_at") if isinstance(gov, dict) else "",
                "policy": gov.get("policy") if isinstance(gov, dict) else {},
                "report_path": "data/strategy_governor.json"
            }
            metrics = {"total": total, **counts}
            recs = []
            if counts.get("disabled", 0) > 0:
                recs.append("Review disabled strategies and verify their sample quality.")
            return self._report(status, summary, details=details, metrics=metrics, recommendations=recs, run_id=context.get("run_id"))
        except Exception as exc:
            return self._report("fail", f"exception: {exc}", details={"error": str(exc)}, run_id=context.get("run_id"))


class ExecutionRiskAgent(BaseAgent):
    agent_id = "execution_risk"
    agent_type = "execution_risk"

    def run(self, context):
        try:
            report = context.get("loop_health")
            if not isinstance(report, dict):
                report = compute_loop_health(days=context.get("days", 60))
            status_map = {"OK": "ok", "WARN": "warn", "FAIL": "fail"}
            status = status_map.get(str(report.get("health_status") or "").upper(), "idle")
            summary = f"health_score={report.get('health_score')}, decisions={report.get('decisions')}, outcomes={report.get('outcomes')}"
            metrics = {
                "health_score": report.get("health_score"),
                "decisions": report.get("decisions"),
                "executions": report.get("executions"),
                "outcomes": report.get("outcomes"),
                "execution_rate": report.get("execution_rate"),
                "outcome_rate": report.get("outcome_rate")
            }
            recs = []
            if report.get("health_score", 100) < 70:
                recs.append("Increase outcome attribution and ensure every trade links to a decision_id.")
            return self._report(status, summary, details=report, metrics=metrics, recommendations=recs, run_id=context.get("run_id"))
        except Exception as exc:
            return self._report("fail", f"exception: {exc}", details={"error": str(exc)}, run_id=context.get("run_id"))


class PostmortemLearningAgent(BaseAgent):
    agent_id = "postmortem_learning"
    agent_type = "postmortem_learning"

    def run(self, context):
        try:
            rewards = update_strategy_rewards()
            bias = update_bias()
            overrides = maybe_update_overrides()
            indexed = update_index()

            updated_rewards = int(rewards.get("updated", 0) or 0) if isinstance(rewards, dict) else 0
            bias_samples = int(bias.get("samples", 0) or 0) if isinstance(bias, dict) else 0
            status = "ok" if (updated_rewards > 0 or bias_samples > 0 or overrides) else "idle"
            summary = f"strategy_updates={updated_rewards}, bias_samples={bias_samples}, overrides={'yes' if overrides else 'no'}, index_added={indexed}"
            details = {
                "strategy_rewards": rewards if isinstance(rewards, dict) else {},
                "feature_bias": bias if isinstance(bias, dict) else {},
                "threshold_overrides": overrides if isinstance(overrides, dict) else {},
                "event_index_added": indexed
            }
            metrics = {
                "strategy_updates": updated_rewards,
                "bias_samples": bias_samples,
                "event_index_added": indexed
            }
            recs = []
            if bias_samples == 0:
                recs.append("Collect more outcome-linked decisions to update feature bias.")
            return self._report(status, summary, details=details, metrics=metrics, recommendations=recs, run_id=context.get("run_id"))
        except Exception as exc:
            return self._report("fail", f"exception: {exc}", details={"error": str(exc)}, run_id=context.get("run_id"))


def run_daily_agents(days=60, context=None):
    """
    Four-role agent hub:
    - data_health
    - strategy_review
    - execution_risk
    - postmortem_learning
    All reports follow a unified agent_report protocol and are logged to event_bus.
    """
    bus = EventBus()
    run_id = new_run_id()
    ctx = {"days": days, "run_id": run_id}
    if isinstance(context, dict):
        ctx.update(context)

    agents = [
        DataHealthAgent(),
        PostmortemLearningAgent(),
        StrategyReviewAgent(),
        ExecutionRiskAgent()
    ]

    reports = {}
    for agent in agents:
        start = time.time()
        report = agent.run(ctx)
        report["duration_ms"] = int((time.time() - start) * 1000)
        reports[agent.agent_id] = report
        emit_agent_report(report, bus=bus, source="agent_hub")

    return {"run_id": run_id, "reports": reports}
