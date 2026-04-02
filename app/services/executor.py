from __future__ import annotations

import logging
import random
import re


logger = logging.getLogger(__name__)


class ActionExecutor:
    def execute(self, recovery_plan: list[str], raw_input: str, issue_type: str, decision: str, execution_mode: str) -> dict:
        target = self._extract_target(raw_input)
        plan = recovery_plan or []
        steps: list[dict] = []

        if decision in ("no_action", "escalate") or execution_mode == "manual":
            return {
                "decision": decision,
                "target": target,
                "status": "skipped",
                "issue_type": issue_type,
                "steps": steps,
                "fallback_triggered": False,
            }

        any_failed = False
        fallback_triggered = False

        for step in plan:
            outcome = self._simulate_step(step, raw_input)
            steps.append(outcome)
            if outcome["status"] == "failed":
                logger.warning("Execution step failed for %s on target %s: %s", issue_type, target, step)
                any_failed = True
                fallback_triggered = True
                steps.append(
                    {
                        "step": "fallback_continuation",
                        "status": "skipped",
                        "detail": f"{step} failed, continuing with the remaining recovery steps.",
                    }
                )

        if not steps:
            exec_status = "skipped"
        elif any_failed and any(step["status"] == "success" for step in steps):
            exec_status = "partial"
        elif any_failed:
            exec_status = "failed"
        else:
            exec_status = "success"

        return {
            "decision": decision,
            "target": target,
            "status": exec_status,
            "issue_type": issue_type,
            "steps": steps,
            "fallback_triggered": fallback_triggered,
        }

    def _extract_target(self, raw_input: str) -> str:
        match = re.search(r"(order|file|batch)[\s:_-]*(\d+)", raw_input, re.IGNORECASE)
        if match:
            return f"{match.group(1).lower()}_{match.group(2)}"
        return "unknown_target"

    def _simulate_step(self, step: str, raw_input: str) -> dict:
        normalized = raw_input.lower()
        if "simulate_fail" in normalized and step in ("check_downstream", "retry_workflow"):
            return {"step": step, "status": "failed", "detail": "Simulated failure triggered by input."}

        if random.random() < 0.1:
            return {"step": step, "status": "failed", "detail": "Step failed during execution; fallback will continue."}

        return {"step": step, "status": "success", "detail": "Step completed successfully."}
