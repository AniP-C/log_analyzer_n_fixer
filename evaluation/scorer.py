from __future__ import annotations

from app.schemas import BenchmarkSummary, CaseResult


def score_benchmark(results: list[CaseResult], target_response_ms: float) -> BenchmarkSummary:
    total_cases = len(results)
    if total_cases == 0:
        return BenchmarkSummary(
            total_cases=0,
            detection_accuracy=0.0,
            action_accuracy=0.0,
            resolution_success=0.0,
            response_time_score=0.0,
            overall_score=0,
        )

    detection_accuracy = round(sum(result.passed_issue_type for result in results) / total_cases * 100, 2)
    action_accuracy = round(sum(result.passed_action for result in results) / total_cases * 100, 2)
    resolution_success = round(
        sum(result.execution_status in {"success", "partial", "skipped"} for result in results) / total_cases * 100,
        2,
    )
    average_response = sum(result.response_time_ms for result in results) / total_cases
    response_time_score = round(max(0.0, min(100.0, (target_response_ms / max(average_response, 1.0)) * 100)), 2)
    overall_score = round((detection_accuracy + action_accuracy + resolution_success + response_time_score) / 4)

    return BenchmarkSummary(
        total_cases=total_cases,
        detection_accuracy=detection_accuracy,
        action_accuracy=action_accuracy,
        resolution_success=resolution_success,
        response_time_score=response_time_score,
        overall_score=overall_score,
    )
