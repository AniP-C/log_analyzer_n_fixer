from __future__ import annotations

import json
import time
from pathlib import Path

from app.core.classifier import IssueClassifier
from app.core.reasoning import ReasoningEngine
from app.schemas import AnalyzeResponse, BenchmarkResponse, BenchmarkSummary, CaseResult, ExecutionStepLog
from app.services.executor import ActionExecutor
from app.services.notifier import Notifier
from app.services.rag_engine import RAGEngine
from evaluation.scorer import score_benchmark


class FlowFixAgent:
    def __init__(self) -> None:
        self.classifier = IssueClassifier()
        self.rag_engine = RAGEngine()
        self.reasoning_engine = ReasoningEngine()
        self.executor = ActionExecutor()
        self.notifier = Notifier()

    async def analyze_issue(self, raw_input: str) -> AnalyzeResponse:
        classification = self.classifier.classify(raw_input)

        similar_cases = self.rag_engine.retrieve(classification.issue_type, raw_input)
        decision_source = "rag_enhanced" if similar_cases else "rule_based"

        reasoning = self.reasoning_engine.reason(raw_input, classification.issue_type, similar_cases)

        final_decision, execution_mode = self._resolve_action(reasoning.decision, reasoning.confidence)

        execution = self.executor.execute(
            recovery_plan=reasoning.recovery_plan,
            raw_input=raw_input,
            issue_type=classification.issue_type,
            decision=final_decision,
            execution_mode=execution_mode,
        )

        notification = self.notifier.send(severity=reasoning.severity, confidence=reasoning.confidence)

        execution_log = self._build_execution_log(execution_mode, final_decision, execution)
        timeline = [
            "incident received",
            "issue classified",
            "similar cases retrieved",
            "decision reasoning completed",
            f"decision resolved: {final_decision}",
            "execution skipped" if execution["status"] == "skipped" else "execution started",
            "notification dispatched",
        ]

        return AnalyzeResponse(
            issue_type=classification.issue_type,
            decision=final_decision,
            confidence=reasoning.confidence,
            execution_mode=execution_mode,
            decision_source=decision_source,
            severity=reasoning.severity,
            impact=reasoning.impact,
            why=reasoning.why,
            recovery_plan=reasoning.recovery_plan,
            execution_log=execution_log,
            timeline=timeline,
            notification=notification["channel"],
            correlated_incidents=reasoning.correlated_incidents,
        )

    async def run_benchmark(self) -> BenchmarkResponse:
        test_cases_path = Path(__file__).resolve().parents[1] / "data" / "test_cases.json"
        cases = json.loads(test_cases_path.read_text(encoding="utf-8"))
        case_results: list[CaseResult] = []

        for case in cases:
            started_at = time.perf_counter()
            result = await self.analyze_issue(case["input"])
            response_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
            execution_status = "skipped" if result.decision in ("no_action", "escalate") else _execution_summary(result.execution_log)

            case_results.append(
                CaseResult(
                    input=case["input"],
                    expected_issue_type=case["expected_issue_type"],
                    expected_action=case["expected_action"],
                    actual_issue_type=result.issue_type,
                    actual_action=result.decision,
                    confidence=result.confidence,
                    response_time_ms=response_time_ms,
                    passed_issue_type=result.issue_type == case["expected_issue_type"],
                    passed_action=result.decision == case["expected_action"],
                    execution_status=execution_status,
                )
            )

        summary: BenchmarkSummary = score_benchmark(case_results, 1500.0)
        results_dir = Path("evaluation")
        results_dir.mkdir(parents=True, exist_ok=True)
        results_path = results_dir / "results.json"
        payload = {
            "summary": summary.model_dump(),
            "results": [result.model_dump() for result in case_results],
        }
        results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        return BenchmarkResponse(summary=summary, results=case_results)

    def _resolve_action(self, decision: str, confidence: float) -> tuple[str, str]:
        if decision == "no_action":
            return "no_action", "manual"
        if decision == "escalate":
            return "escalate", "manual"
        if confidence < 0.5:
            return "escalate", "manual"
        if confidence < 0.75:
            return decision, "warning"
        return decision, "auto"

    def _build_execution_log(self, execution_mode: str, decision: str, execution: dict) -> list[ExecutionStepLog]:
        execution_log = [ExecutionStepLog(**step) for step in execution.get("steps", [])]

        if decision == "no_action":
            execution_log.insert(
                0,
                ExecutionStepLog(
                    step="no_action",
                    status="skipped",
                    detail="Reasoning selected no_action, so no remediation was executed.",
                ),
            )
        elif decision == "escalate":
            execution_log.insert(
                0,
                ExecutionStepLog(
                    step="escalation",
                    status="skipped",
                    detail="Reasoning selected escalate, so the case was handed to a human operator.",
                ),
            )
        elif execution_mode == "manual":
            execution_log.insert(
                0,
                ExecutionStepLog(
                    step="manual_review",
                    status="skipped",
                    detail="Confidence below 0.50, so the case was escalated instead of auto-remediated.",
                ),
            )
        elif execution_mode == "warning":
            execution_log.insert(
                0,
                ExecutionStepLog(
                    step="warning_gate",
                    status="skipped",
                    detail="Confidence between 0.50 and 0.75, so the plan ran with caution.",
                ),
            )

        return execution_log


def _execution_summary(execution_log: list[ExecutionStepLog]) -> str:
    if not execution_log:
        return "skipped"
    statuses = {step.status for step in execution_log}
    if "success" in statuses and "failed" not in statuses:
        return "success"
    if "failed" in statuses and "success" in statuses:
        return "partial"
    if "failed" in statuses:
        return "failed"
    return "skipped"
