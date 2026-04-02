from __future__ import annotations

import json
from pathlib import Path


class RAGEngine:
    def __init__(self) -> None:
        data_path = Path(__file__).resolve().parents[1] / "data" / "incidents.json"
        self.incidents = json.loads(data_path.read_text(encoding="utf-8"))

    def retrieve(self, issue_type: str, raw_input: str, top_k: int = 3) -> list[dict]:
        normalized = raw_input.lower()
        scored_cases: list[tuple[int, dict]] = []

        for incident in self.incidents:
            if incident.get("issue") != issue_type:
                continue

            score = 0
            pattern = str(incident.get("pattern", "")).lower()
            if pattern and pattern in normalized:
                score += 3

            for keyword in incident.get("keywords", []):
                if str(keyword).lower() in normalized:
                    score += 1

            if score > 0:
                scored_cases.append((score, incident))

        ranked = [case for _, case in sorted(scored_cases, key=lambda item: item[0], reverse=True)]
        return ranked[:top_k]
