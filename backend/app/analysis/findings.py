"""Shared finding container used by every detector."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Evidence:
    label: str
    detail: str


@dataclass
class Action:
    action: str
    why: str
    effort: str = "medium"
    owner_hint: str | None = None


@dataclass
class RawFinding:
    """Detector output before the LLM (or the deterministic writer) narrates it."""

    category: str  # hidden_issue | delay_risk | delay_action
    finding_type: str
    title: str
    severity: str = "medium"
    confidence: float = 0.7
    risk_score: float | None = None
    task_id: int | None = None
    task_title: str | None = None
    person_id: int | None = None
    person_name: str | None = None
    explanation: str = ""
    reasoning_summary: str = ""
    impact: str = ""
    cause_hypothesis: str | None = None
    cause_category: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    recommended_action: str | None = None
    recommended_action_why: str | None = None
    source: str = "rules"

    def key(self) -> str:
        target = self.task_id if self.task_id is not None else self.person_id
        return f"{self.category}:{self.finding_type}:{target if target is not None else 'project'}"


SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.get(severity, 1)
