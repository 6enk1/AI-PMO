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
    is_summary: bool = False
    effective_progress: float = 0.0
    effective_start: date | None = None
    effective_end: date | None = None
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


# --------------------------------------------------------------------------- Issue triage
TriageLabel = Literal["issue", "uncertain", "not_issue"]
SeverityEstimate = Literal["高", "中", "低", "不明"]


class TriageTaskCandidate(BaseModel):
    task_id: int | None = None
    title: str
    score: float


class IssueAnalyzeRow(BaseModel):
    """分析対象の1行。Excel以外の入力でも使えるよう、テキストだけを要求する。"""

    row_index: int | None = None
    text: str
    task_hint: str | None = None
    severity_hint: str | None = None  # 記入者が重要度を書いていれば推定より優先する
    due_date: date | None = None


class IssueAnalyzeRequest(BaseModel):
    rows: list[IssueAnalyzeRow]
    project_id: int | None = None  # 関連タスク候補の照合に使う
    use_llm: bool = True


class IssueTriageItem(BaseModel):
    id: str
    row_index: int | None = None
    part_index: int = 0
    source_text: str
    statement: str
    label: TriageLabel
    confidence: float
    title: str = ""
    description: str = ""
    severity_estimate: SeverityEstimate = "不明"
    severity: Severity = "medium"
    due_date: date | None = None
    reasons: list[str] = Field(default_factory=list)
    related_task_candidates: list[TriageTaskCandidate] = Field(default_factory=list)
    split: bool = False
    source: str = "rules"


class IssueAnalyzeResponse(BaseModel):
    llm_used: bool = False
    llm_note: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[IssueTriageItem] = Field(default_factory=list)


class IssueBulkCreateItem(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    severity: Severity = "medium"
    task_id: int | None = None
    owner_id: int | None = None
    due_date: date | None = None
    status: IssueStatus = "open"


class IssueBulkCreateRequest(BaseModel):
    project_id: int
    items: list[IssueBulkCreateItem]


class IssueBulkCreateResponse(BaseModel):
    created: int = 0
    issue_ids: list[int] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class ImportIssueRowsRequest(BaseModel):
    token: str
    sheet: str | None = None
    header_row: int | None = None
    mapping: dict[str, str | None] = Field(default_factory=dict)
    text_column: str | None = None  # 未指定なら mapping の課題列を使う


class ImportIssueRowsResponse(BaseModel):
    text_column: str | None = None
    rows: list[IssueAnalyzeRow] = Field(default_factory=list)
    available_columns: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- Categorize
class CategorySuggestion(BaseModel):
    task_id: int
    task_code: str | None = None
    task_title: str
    current_category: str | None = None
    suggested_category: str
    existing_category_id: int | None = None
    confidence: float
    reason: str
    source: str = "rules"


class CategorySuggestResponse(BaseModel):
    project_id: int
    llm_used: bool
    llm_note: str | None = None
    existing_categories: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[CategorySuggestion] = Field(default_factory=list)
    unmatched_task_ids: list[int] = Field(default_factory=list)


class CategoryAssignment(BaseModel):
    task_id: int
    category_name: str = Field(min_length=1, max_length=200)


class CategoryApplyRequest(BaseModel):
    assignments: list[CategoryAssignment]


class CategoryApplyResponse(BaseModel):
    updated_tasks: int
    created_categories: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


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


ContentKind = Literal["wbs", "issues", "mixed", "unknown"]


class ImportAnalyzeResponse(BaseModel):
    # アップロードされた中身の判定（画面の出し分けに使う）
    content_kind: ContentKind = "unknown"
    content_confidence: float = 0.0
    content_evidence: list[str] = Field(default_factory=list)
    has_task_data: bool = False
    has_issue_text: bool = False
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


MatchBy = Literal["auto", "code", "title", "none"]


class ImportCommitRequest(BaseModel):
    token: str
    sheet: str | None = None
    header_row: int | None = None
    mapping: dict[str, str | None] = Field(default_factory=dict)
    project_id: int | None = None
    new_project_name: str | None = None
    create_missing_people: bool = True
    create_issues: bool = True
    create_tasks: bool = True
    """課題リストだけのファイルでは False にして、Taskを作らずプロジェクトだけ用意する。"""
    match_by: MatchBy = "auto"
    """既存Taskとの突き合わせ方法。auto=Task ID→タスク名の順、none=常に追加。"""


class ImportCommitResponse(BaseModel):
    project_id: int
    project_name: str
    match_by: str = "none"
    created_tasks: int
    updated_tasks: int = 0
    unchanged_tasks: int = 0
    created_people: int
    created_issues: int
    created_dependencies: int
    created_milestones: int
    skipped_rows: int
    warnings: list[str] = Field(default_factory=list)


class ImportRowChange(BaseModel):
    field: str
    label: str
    before: str | None = None
    after: str | None = None


class ImportRowPlan(BaseModel):
    row_index: int
    title: str
    code: str | None = None
    action: Literal["create", "update", "unchanged", "skip"]
    matched_task_id: int | None = None
    matched_task_title: str | None = None
    matched_by: str | None = None
    changes: list[ImportRowChange] = Field(default_factory=list)


class ImportPlanResponse(BaseModel):
    match_by: str
    create_count: int
    update_count: int
    unchanged_count: int
    skipped_rows: int
    rows: list[ImportRowPlan] = Field(default_factory=list)
    missing_in_file: list[dict[str, Any]] = Field(default_factory=list)
