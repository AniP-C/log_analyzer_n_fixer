from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DecisionType = Literal["retry_workflow", "remove_and_reprocess", "isolate_and_rerun_batch", "escalate", "no_action"]
ExecutionModeType = Literal["auto", "warning", "manual"]
SeverityType = Literal["low", "medium", "high"]
DecisionSourceType = Literal["rule_based", "rag_enhanced"]


class AnalyzeRequest(BaseModel):
    input: str = Field(..., min_length=5, description="Operational issue description or log excerpt.")


class HealthResponse(BaseModel):
    status: str
    service: str


class Impact(BaseModel):
    orders_affected: int = 0
    scope: Literal["single", "batch"] = "single"
    notes: str | None = None


class ExecutionStepLog(BaseModel):
    step: str
    status: Literal["success", "failed", "skipped"] = "success"
    detail: str | None = None


class ReasoningResult(BaseModel):
    decision: DecisionType
    confidence: float
    recovery_plan: list[str] = Field(default_factory=list)
    why: list[str] = Field(default_factory=list)
    severity: SeverityType
    impact: Impact
    root_cause: str
    correlated_incidents: bool = False


class AnalyzeResponse(BaseModel):
    issue_type: str
    decision: DecisionType
    confidence: float
    execution_mode: ExecutionModeType
    decision_source: DecisionSourceType
    severity: SeverityType
    impact: Impact
    why: list[str]
    recovery_plan: list[str]
    execution_log: list[ExecutionStepLog]
    timeline: list[str]
    notification: str
    correlated_incidents: bool


class CaseResult(BaseModel):
    input: str
    expected_issue_type: str
    expected_action: str
    actual_issue_type: str
    actual_action: str
    confidence: float
    response_time_ms: float
    passed_issue_type: bool
    passed_action: bool
    execution_status: str


class BenchmarkSummary(BaseModel):
    total_cases: int
    detection_accuracy: float
    action_accuracy: float
    resolution_success: float
    response_time_score: float
    overall_score: int


class BenchmarkResponse(BaseModel):
    summary: BenchmarkSummary
    results: list[CaseResult]
