"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TaskStatus = Literal["not_started", "in_progress", "blocked", "done", "cancelled"]
TaskPriority = Literal["low", "medium", "high", "critical"]
IssueStatus = Literal["open", "in_progress", "resolved", "closed"]
Severity = Literal["low", "medium", "high", "critical"]
MilestoneStatus = Literal["pending", "achieved", "missed"]
DependencyType = Literal["FS", "SS", "FF", "SF"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- Project
class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectRead(ORMModel, ProjectBase):
    id: int
    created_at: datetime
    updated_at: datetime


class ProjectSummary(ProjectRead):
    task_count: int = 0
    open_task_count: int = 0
    overdue_task_count: int = 0
    open_issue_count: int = 0


# --------------------------------------------------------------------------- Person
class PersonBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str | None = None
    email: str | None = None
    capacity_tasks: int = 8


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = None
    email: str | None = None
    capacity_tasks: int | None = None


class PersonRead(ORMModel, PersonBase):
    id: int
    project_id: int


class PersonWorkload(PersonRead):
    """Person plus the derived load figures the PM actually looks at."""

    assigned_task_count: int = 0
    open_task_count: int = 0
    overdue_task_count: int = 0
    high_risk_task_count: int = 0
    critical_task_count: int = 0
    due_this_week_count: int = 0
    open_issue_count: int = 0
    average_progress: float = 0.0
    load_ratio: float = 0.0
    load_level: str = "normal"
    task_ids: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- Task
class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    code: str | None = None
    description: str | None = None
    parent_task_id: int | None = None
    owner_id: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    progress: float = 0.0
    status: TaskStatus = "not_started"
    priority: TaskPriority = "medium"
    estimated_hours: float | None = None
    notes: str | None = None

    @field_validator("progress")
    @classmethod
    def _clamp_progress(cls, v: float) -> float:
        return max(0.0, min(100.0, float(v)))


class TaskCreate(TaskBase):
    predecessor_task_ids: list[int] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    code: str | None = None
    description: str | None = None
    parent_task_id: int | None = None
    owner_id: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    progress: float | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    estimated_hours: float | None = None
    notes: str | None = None
    predecessor_task_ids: list[int] | None = None

    @field_validator("progress")
    @classmethod
    def _clamp_progress(cls, v: float | None) -> float | None:
        return None if v is None else max(0.0, min(100.0, float(v)))


class DependencyRead(ORMModel):
    id: int
    predecessor_task_id: int
    successor_task_id: int
    dependency_type: DependencyType
    lag_days: int = 0


class DependencyCreate(BaseModel):
    predecessor_task_id: int
    successor_task_id: int
    dependency_type: DependencyType = "FS"
    lag_days: int = 0


class TaskRead(ORMModel, TaskBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
    owner_name: str | None = None
    parent_task_title: str | None = None
    category: str | None = None  # 最上位の親タスク = 大カテゴリ
    path_titles: list[str] = Field(default_factory=list)  # ルート → 直近の親
    depth: int = 0
    child_count: int = 0
    predecessor_task_ids: list[int] = Field(default_factory=list)
    successor_task_ids: list[int] = Field(default_factory=list)
    child_task_ids: list[int] = Field(default_factory=list)
    issue_ids: list[int] = Field(default_factory=list)
    open_issue_count: int = 0
    is_overdue: bool = False
    days_overdue: int = 0
    days_to_due: int | None = None
    expected_progress: float = 0.0
    progress_gap: float = 0.0
    risk_score: float = 0.0
    risk_level: str = "low"
    total_float: int | None = None
    is_critical_path: bool = False


# --------------------------------------------------------------------------- Issue
class IssueBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    code: str | None = None
    description: str | None = None
    task_id: int | None = None
    severity: Severity = "medium"
    owner_id: int | None = None
    raised_on: date | None = None
    due_date: date | None = None
    status: IssueStatus = "open"
    action_plan: str | None = None
    resolution: str | None = None


class IssueCreate(IssueBase):
    pass


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    code: str | None = None
    description: str | None = None
    task_id: int | None = None
    severity: Severity | None = None
    owner_id: int | None = None
    raised_on: date | None = None
    due_date: date | None = None
    status: IssueStatus | None = None
    action_plan: str | None = None
    resolution: str | None = None


class IssueRead(ORMModel, IssueBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
    owner_name: str | None = None
    task_title: str | None = None
    task_category: str | None = None
    is_overdue: bool = False


# --------------------------------------------------------------------------- Milestone
class MilestoneBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    due_date: date | None = None
    status: MilestoneStatus = "pending"


class MilestoneCreate(MilestoneBase):
    pass


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    due_date: date | None = None
    status: MilestoneStatus | None = None


class MilestoneRead(ORMModel, MilestoneBase):
    id: int
    project_id: int
    days_remaining: int | None = None
    at_risk: bool = False


# --------------------------------------------------------------------------- AI / analysis
class EvidenceItem(BaseModel):
    label: str
    detail: str


class RecommendedAction(BaseModel):
    action: str
    why: str
    effort: str = "medium"
    owner_hint: str | None = None


class Finding(BaseModel):
    """The common envelope every AI PMO output uses.

    Every finding must carry evidence - a bare "this is dangerous" verdict is
    explicitly not allowed by the product spec.
    """

    id: str
    category: Literal["hidden_issue", "delay_risk", "delay_action"]
    finding_type: str
    title: str
    severity: Severity
    confidence: float = 0.6
    risk_score: float | None = None
    task_id: int | None = None
    task_title: str | None = None
    task_category: str | None = None
    person_id: int | None = None
    person_name: str | None = None
    explanation: str
    reasoning_summary: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    impact: str
    cause_hypothesis: str | None = None
    cause_category: str | None = None
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    recommended_action: str | None = None
    recommended_action_why: str | None = None
    source: str = "rules"


class RiskFactor(BaseModel):
    key: str
    label: str
    points: float
    detail: str


class TaskRisk(BaseModel):
    task_id: int
    task_code: str | None = None
    task_title: str
    task_category: str | None = None
    owner_name: str | None = None
    planned_end: date | None = None
    progress: float
    status: str
    priority: str
    risk_score: float
    risk_level: str
    days_overdue: int = 0
    days_to_due: int | None = None
    factors: list[RiskFactor] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    impact: str = ""
    recommended_action: str | None = None


class FocusItem(BaseModel):
    kind: str
    ref_id: int | None = None
    title: str
    detail: str
    severity: Severity
    score: float
    link: str | None = None


class HealthBreakdown(BaseModel):
    key: str
    label: str
    penalty: float
    detail: str


class DashboardResponse(BaseModel):
    project: ProjectRead
    as_of: date
    health_score: float
    health_label: str
    health_breakdown: list[HealthBreakdown] = Field(default_factory=list)
    total_tasks: int
    open_tasks: int
    done_tasks: int
    overdue_tasks: int
    high_risk_tasks: int
    hidden_issue_count: int
    open_issue_count: int
    critical_issue_count: int
    unassigned_tasks: int
    average_progress: float
    schedule_variance_days: float
    next_milestone: MilestoneRead | None = None
    milestones: list[MilestoneRead] = Field(default_factory=list)
    focus_items: list[FocusItem] = Field(default_factory=list)


class AIPMOResponse(BaseModel):
    project_id: int
    as_of: date
    generated_at: datetime
    llm_used: bool
    llm_note: str | None = None
    hidden_issues: list[Finding] = Field(default_factory=list)
    delay_risks: list[TaskRisk] = Field(default_factory=list)
    delay_actions: list[Finding] = Field(default_factory=list)
    recommended_actions: list[Finding] = Field(default_factory=list)


# --------------------------------------------------------------------------- Import
class ImportColumnCandidate(BaseModel):
    field: str
    column: str | None
    confidence: float
    reason: str | None = None


class ImportSheetInfo(BaseModel):
    name: str
    row_count: int
    header_row: int
    columns: list[str]


class ImportAnalyzeResponse(BaseModel):
    token: str
    filename: str
    sheets: list[ImportSheetInfo]
    selected_sheet: str
    header_row: int
    columns: list[str]
    mapping: dict[str, str | None]
    mapping_candidates: list[ImportColumnCandidate]
    unmapped_columns: list[str]
    preview: list[dict[str, Any]]
    raw_preview: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    known_fields: list[dict[str, str]] = Field(default_factory=list)


class ImportCommitRequest(BaseModel):
    token: str
    sheet: str | None = None
    header_row: int | None = None
    mapping: dict[str, str | None] = Field(default_factory=dict)
    project_id: int | None = None
    new_project_name: str | None = None
    create_missing_people: bool = True
    create_issues: bool = True


class ImportCommitResponse(BaseModel):
    project_id: int
    project_name: str
    created_tasks: int
    created_people: int
    created_issues: int
    created_dependencies: int
    created_milestones: int
    skipped_rows: int
    warnings: list[str] = Field(default_factory=list)
