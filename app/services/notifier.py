from __future__ import annotations


class Notifier:
    def send(self, *, severity: str, confidence: float) -> dict:
        escalated = confidence < 0.5

        if severity == "high":
            channel = "slack+email"
            reason = "High severity incident requires broad visibility."
        elif severity == "medium":
            channel = "email"
            reason = "Medium severity incident should be shared by email."
        else:
            channel = "none"
            reason = "Low severity incident does not require notification."

        if escalated:
            reason = f"{reason} Confidence is low, so the case is escalated for human review."

        return {
            "channel": channel,
            "reason": reason,
            "escalated": escalated,
        }
