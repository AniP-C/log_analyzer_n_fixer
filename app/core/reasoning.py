from __future__ import annotations

import re
from typing import Any

from app.schemas import Impact, ReasoningResult


class ReasoningEngine:
    def reason(self, raw_input: str, issue_type: str, similar_cases: list[dict[str, Any]]) -> ReasoningResult:
        normalized = raw_input.lower()

        if _is_delayed_batch(normalized):
            result = ReasoningResult(
                decision="no_action",
                confidence=_confidence_for("high", raw_input, issue_type),
                severity="low",
                impact=Impact(
                    orders_affected=_extract_count(normalized) or 0,
                    scope="batch",
                    notes="Spike aligns with backlog compensation from the previous delayed run.",
                ),
                root_cause="Backlog compensation after a delayed batch run, not an active failure.",
                why=[
                    "Previous run delay detected",
                    "Current spike is backlog compensation",
                ],
                recovery_plan=[],
                correlated_incidents=False,
            )
            return _apply_rag_influence(result, similar_cases)

        if issue_type == "workflow_stuck_bulk":
            result = ReasoningResult(
                decision="retry_workflow",
                confidence=_confidence_for("high", raw_input, issue_type),
                severity="high",
                impact=Impact(
                    orders_affected=_extract_count(normalized) or 25,
                    scope="batch",
                    notes="Many orders are stuck in CREATED, indicating a shared workflow stall.",
                ),
                root_cause="A shared workflow stage is stalled and blocking multiple orders.",
                why=[
                    "Bulk CREATED-state pattern indicates shared orchestration failure",
                    "A retry is appropriate because the symptom is operational, not data corruption",
                ],
                recovery_plan=["validate_state", "check_downstream", "retry_workflow", "confirm_progress"],
                correlated_incidents=True,
            )
            return _apply_rag_influence(result, similar_cases)

        if _is_paypal_validation_blocker(normalized):
            result = ReasoningResult(
                decision="remove_and_reprocess",
                confidence=_confidence_for("high", raw_input, issue_type),
                severity="medium",
                impact=Impact(
                    orders_affected=1,
                    scope="batch",
                    notes="A single bad record is blocking the broader file.",
                ),
                root_cause="A PayPal order is missing billing data and is blocking file progression.",
                why=[
                    "Known PayPal billing-address validation pattern detected",
                    "Removing the bad record is safer than retrying the entire file unchanged",
                ],
                recovery_plan=["identify_faulty_order", "remove_faulty_order", "reprocess_file", "confirm_batch_success"],
                correlated_incidents=True,
            )
            return _apply_rag_influence(result, similar_cases)

        if _is_downstream_failure(normalized):
            impact = Impact(
                orders_affected=_extract_count(normalized) or 1,
                scope=_scope(normalized),
                notes="Transient downstream dependency symptoms detected.",
            )
            result = ReasoningResult(
                decision="retry_workflow",
                confidence=_confidence_for("medium", raw_input, issue_type)
                if impact.scope == "single"
                else _confidence_for("high", raw_input, issue_type),
                severity="medium" if impact.scope == "single" else "high",
                impact=impact,
                root_cause="Downstream dependency timeout or service instability.",
                why=[
                    "Timeout or downstream failure indicators suggest a transient dependency issue",
                    "Retry is appropriate because the data itself does not appear invalid",
                ],
                recovery_plan=["check_downstream", "retry_workflow", "validate_state"],
                correlated_incidents=impact.scope == "batch",
            )
            return _apply_rag_influence(result, similar_cases)

        if _is_upstream_validation_failure(normalized):
            impact = Impact(
                orders_affected=_extract_count(normalized) or 1,
                scope=_scope(normalized),
                notes="Bad data or schema mismatch detected.",
            )
            result = ReasoningResult(
                decision="escalate",
                confidence=_confidence_for("medium", raw_input, issue_type)
                if impact.scope == "single"
                else _confidence_for("high", raw_input, issue_type),
                severity="medium" if impact.scope == "single" else "high",
                impact=impact,
                root_cause="Upstream validation failure caused a deterministic processing error.",
                why=[
                    "Validation or bad-data indicators suggest the next retry will fail in the same way",
                    "Human or upstream-system correction is required before safe remediation",
                ],
                recovery_plan=["collect_diagnostics", "escalate_to_oncall"],
                correlated_incidents=impact.scope == "batch",
            )
            return _apply_rag_influence(result, similar_cases)

        if issue_type == "file_processing_failure":
            result = ReasoningResult(
                decision="isolate_and_rerun_batch",
                confidence=_confidence_for("high", raw_input, issue_type),
                severity="high",
                impact=Impact(
                    orders_affected=_extract_count(normalized) or 10,
                    scope="batch",
                    notes="Batch execution failed and needs isolation before rerun.",
                ),
                root_cause="Batch processing failed during file execution.",
                why=[
                    "File-processing failure points to batch-level operational instability",
                    "Isolation before rerun reduces the blast radius of a repeated failure",
                ],
                recovery_plan=["validate_state", "isolate_failed_segment", "rerun_batch", "confirm_batch_success"],
                correlated_incidents=True,
            )
            return _apply_rag_influence(result, similar_cases)

        if issue_type == "data_issue_invalid_chars":
            result = ReasoningResult(
                decision="escalate",
                confidence=_confidence_for("medium", raw_input, issue_type),
                severity="medium",
                impact=Impact(
                    orders_affected=_extract_count(normalized) or 1,
                    scope=_scope(normalized),
                    notes="Malformed data needs correction before retry.",
                ),
                root_cause="Invalid characters or malformed data are causing deterministic validation failure.",
                why=[
                    "Malformed payload evidence indicates a data-quality issue",
                    "Escalation is safer than retrying the same invalid input",
                ],
                recovery_plan=["collect_diagnostics", "escalate_to_oncall"],
                correlated_incidents=_scope(normalized) == "batch",
            )
            return _apply_rag_influence(result, similar_cases)

        if issue_type == "workflow_stuck":
            result = ReasoningResult(
                decision="retry_workflow",
                confidence=_confidence_for("medium", raw_input, issue_type),
                severity="medium",
                impact=Impact(
                    orders_affected=_extract_count(normalized) or 1,
                    scope=_scope(normalized),
                    notes="Order is stuck without clear evidence of data corruption.",
                ),
                root_cause="Workflow appears stalled at an intermediate processing state.",
                why=[
                    "Stuck-state language points to an operational workflow stall",
                    "A bounded retry is appropriate while confidence remains moderate",
                ],
                recovery_plan=["validate_state", "retry_workflow", "confirm_progress"],
                correlated_incidents=_scope(normalized) == "batch",
            )
            return _apply_rag_influence(result, similar_cases)

        result = ReasoningResult(
            decision="escalate",
            confidence=_confidence_for("low", raw_input, issue_type),
            severity="low",
            impact=Impact(
                orders_affected=_extract_count(normalized) or 0,
                scope=_scope(normalized),
                notes="Insufficient signal for confident autonomous remediation.",
            ),
            root_cause="Incident does not match a trusted remediation pattern.",
            why=[
                "Signal is too weak for autonomous action",
                "Escalation preserves safety when the diagnosis is uncertain",
            ],
            recovery_plan=["collect_diagnostics", "escalate_to_oncall"],
            correlated_incidents=False,
        )
        return _apply_rag_influence(result, similar_cases)


def _confidence_for(band: str, raw_input: str, issue_type: str) -> float:
    ranges = {
        "low": (0.4, 0.5),
        "medium": (0.55, 0.7),
        "high": (0.75, 0.9),
    }
    lower, upper = ranges[band]
    spread = int(round((upper - lower) * 100))
    seed = sum(ord(char) for char in f"{band}:{issue_type}:{raw_input.lower()}")
    offset = seed % (spread + 1)
    return round(lower + (offset / 100), 2)


def _extract_count(normalized: str) -> int | None:
    match = re.search(r"(\d+)\s+(orders|order)", normalized)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _scope(normalized: str) -> str:
    if any(k in normalized for k in ("many", "bulk", "batch", "file", "spike")):
        return "batch"
    return "single"


def _is_delayed_batch(normalized: str) -> bool:
    return any(k in normalized for k in ("delayed", "delay", "late")) and any(
        k in normalized for k in ("next run", "combined", "two batches", "double batch", "spike")
    )


def _is_downstream_failure(normalized: str) -> bool:
    return any(
        k in normalized for k in ("timeout", "timed out", "downstream", "dependency failure", "service unavailable", "502", "503", "504")
    )


def _is_upstream_validation_failure(normalized: str) -> bool:
    return any(k in normalized for k in ("validation", "invalid", "bad data", "schema", "missing required", "cannot parse"))


def _is_paypal_validation_blocker(normalized: str) -> bool:
    return ("paypal" in normalized) and any(
        k in normalized for k in ("missing billing address", "billing address missing", "no billing address")
    )


def _apply_rag_influence(result: ReasoningResult, similar_cases: list[dict[str, Any]]) -> ReasoningResult:
    if not similar_cases:
        return result

    top_case = similar_cases[0]
    success_rate = top_case.get("success_rate")
    fix = top_case.get("fix")
    updated = result.model_copy(deep=True)

    if isinstance(success_rate, (int, float)) and fix:
        bonus = min(0.05, max(0.02, float(success_rate) * 0.05))
        updated.confidence = round(min(_confidence_cap(updated.confidence), updated.confidence + bonus), 2)
        updated.why.append(
            f"Similar past cases resolved with {fix} (success rate {round(float(success_rate) * 100)}%)"
        )
    else:
        updated.why.append("Similar past incidents support the selected remediation path")

    return updated


def _confidence_cap(confidence: float) -> float:
    if confidence < 0.55:
        return 0.5
    if confidence < 0.75:
        return 0.7
    return 0.9
