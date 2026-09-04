"""Builds the structured snapshot of a project.

This module does all of the deterministic maths: schedule roll-up, CPM float,
overdue detection, dependency graph consistency, workload per person and issue
aggregation. Nothing here talks to an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Issue, Milestone, Person, Project, Task, TaskDependency

ACTIVE_STATUSES = ("not_started", "in_progress", "blocked")
CLOSED_ISSUE_STATUSES = ("resolved", "closed")


def _days(a: date, b: date) -> int:
    return (a - b).days


@dataclass
class TaskView:
    """A task plus every derived number the rest of the engine needs."""

    task: Task
    today: date

    predecessor_ids: list[int] = field(default_factory=list)
    successor_ids: list[int] = field(default_factory=list)
    child_ids: list[int] = field(default_factory=list)
    open_issue_ids: list[int] = field(default_factory=list)
    issue_ids: list[int] = field(default_factory=list)

    duration_days: int = 1
    early_start: int | None = None
    early_finish: int | None = None
    late_start: int | None = None
    late_finish: int | None = None
    total_float: int | None = None
    is_critical_path: bool = False

    risk_score: float = 0.0
    risk_level: str = "low"

    # 子を持つTask（カテゴリ/サマリ）は、子の集計値を表示に使う
    rollup_progress: float | None = None
    rollup_start: date | None = None
    rollup_end: date | None = None

    # -- basic identity -----------------------------------------------------
    @property
    def id(self) -> int:
        return self.task.id

    @property
    def title(self) -> str:
        return self.task.title

    @property
    def code(self) -> str | None:
        return self.task.code

    @property
    def status(self) -> str:
        return self.task.status

    @property
    def priority(self) -> str:
        return self.task.priority

    @property
    def progress(self) -> float:
        return float(self.task.progress or 0.0)

    @property
    def owner_id(self) -> int | None:
        return self.task.owner_id

    @property
    def planned_start(self) -> date | None:
        return self.task.planned_start

    @property
    def planned_end(self) -> date | None:
        return self.task.planned_end

    # -- derived state ------------------------------------------------------
    @property
    def is_done(self) -> bool:
        return self.task.status == "done"

    @property
    def is_cancelled(self) -> bool:
        return self.task.status == "cancelled"

    @property
    def is_active(self) -> bool:
        return self.task.status in ACTIVE_STATUSES

    @property
    def is_leaf(self) -> bool:
        return not self.child_ids

    @property
    def is_summary(self) -> bool:
        return bool(self.child_ids)

    @property
    def effective_progress(self) -> float:
        """表示用の進捗。サマリTaskは子の加重平均を使う。"""
        if self.is_summary and self.rollup_progress is not None and self.progress == 0:
            return self.rollup_progress
        return self.progress

    @property
    def effective_start(self) -> date | None:
        return self.planned_start or (self.rollup_start if self.is_summary else None)

    @property
    def effective_end(self) -> date | None:
        return self.planned_end or (self.rollup_end if self.is_summary else None)

    @property
    def is_overdue(self) -> bool:
        return bool(self.is_active and self.planned_end and self.planned_end < self.today)

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue or self.planned_end is None:
            return 0
        return _days(self.today, self.planned_end)

    @property
    def days_to_due(self) -> int | None:
        if self.planned_end is None:
            return None
        return _days(self.planned_end, self.today)

    @property
    def expected_progress(self) -> float:
        """Where the task *should* be if it burned down linearly over its plan."""
        start, end = self.planned_start, self.planned_end
        if end is None:
            return 0.0
        if start is None or start >= end:
            return 100.0 if self.today >= end else 0.0
        if self.today <= start:
            return 0.0
        if self.today >= end:
            return 100.0
        span = _days(end, start)
        return round(_days(self.today, start) / span * 100, 1)

    @property
    def progress_gap(self) -> float:
        """Positive means the task is behind the linear plan."""
        if not self.is_active:
            return 0.0
        return round(self.expected_progress - self.progress, 1)

    @property
    def schedule_variance_days(self) -> int | None:
        """Actual finish vs planned finish (positive = late)."""
        if self.task.actual_end and self.planned_end:
            return _days(self.task.actual_end, self.planned_end)
        if self.is_overdue:
            return self.days_overdue
        return None

    @property
    def days_since_update(self) -> int:
        return max(0, _days(self.today, self.task.updated_at.date()))

    def label(self) -> str:
        return f"{self.code} {self.title}".strip() if self.code else self.title


@dataclass
class PersonLoad:
    person: Person
    assigned_task_ids: list[int] = field(default_factory=list)
    open_task_ids: list[int] = field(default_factory=list)
    overdue_task_ids: list[int] = field(default_factory=list)
    high_risk_task_ids: list[int] = field(default_factory=list)
    critical_task_ids: list[int] = field(default_factory=list)
    due_this_week_ids: list[int] = field(default_factory=list)
    open_issue_ids: list[int] = field(default_factory=list)
    average_progress: float = 0.0

    @property
    def capacity(self) -> int:
        return max(1, int(self.person.capacity_tasks or 8))

    @property
    def load_ratio(self) -> float:
        return round(len(self.open_task_ids) / self.capacity, 2)

    @property
    def load_level(self) -> str:
        ratio = self.load_ratio
        if ratio >= 1.0:
            return "overloaded"
        if ratio >= 0.75:
            return "high"
        if ratio >= 0.4:
            return "normal"
        return "light"


@dataclass
class DependencyEdge:
    predecessor_id: int
    successor_id: int
    dependency_type: str
    lag_days: int


class ProjectSnapshot:
    """Everything the analysis and AI layers need, computed once."""

    def __init__(
        self,
        project: Project,
        tasks: list[Task],
        dependencies: list[TaskDependency],
        people: list[Person],
        issues: list[Issue],
        milestones: list[Milestone],
        today: date | None = None,
    ) -> None:
        self.project = project
        self.today = today or date.today()
        self.raw_tasks = tasks
        self.people = people
        self.issues = issues
        self.milestones = milestones

        self.views: dict[int, TaskView] = {t.id: TaskView(task=t, today=self.today) for t in tasks}
        self.edges: list[DependencyEdge] = [
            DependencyEdge(
                predecessor_id=d.predecessor_task_id,
                successor_id=d.successor_task_id,
                dependency_type=d.dependency_type or "FS",
                lag_days=int(d.lag_days or 0),
            )
            for d in dependencies
            if d.predecessor_task_id in self.views and d.successor_task_id in self.views
        ]
        self.dependency_cycles: list[list[int]] = []
        self.people_by_id: dict[int, Person] = {p.id: p for p in people}
        self.loads: dict[int, PersonLoad] = {p.id: PersonLoad(person=p) for p in people}

        self._link_graph()
        self._link_issues()
        self._compute_schedule()
        self._compute_rollups()
        self._compute_loads()
        self._compute_risks()
        self._finalise_loads()

    # ------------------------------------------------------------------ graph
    def _link_graph(self) -> None:
        for edge in self.edges:
            self.views[edge.successor_id].predecessor_ids.append(edge.predecessor_id)
            self.views[edge.predecessor_id].successor_ids.append(edge.successor_id)
        for view in self.views.values():
            parent_id = view.task.parent_task_id
            if parent_id and parent_id in self.views:
                self.views[parent_id].child_ids.append(view.id)

    def _compute_rollups(self) -> None:
        """Roll dates and progress up from the leaves to the summary tasks."""

        def walk(view: TaskView, depth: int = 0) -> None:
            if depth > 20 or not view.child_ids:  # depth guard for broken links
                return
            children = [self.views[c] for c in view.child_ids]
            for child in children:
                walk(child, depth + 1)
            starts = [c.effective_start for c in children if c.effective_start]
            ends = [c.effective_end for c in children if c.effective_end]
            view.rollup_start = min(starts) if starts else None
            view.rollup_end = max(ends) if ends else None
            weights = [max(1, c.duration_days) for c in children]
            total = sum(weights)
            if total:
                view.rollup_progress = round(
                    sum(c.effective_progress * w for c, w in zip(children, weights)) / total, 1
                )

        roots = [v for v in self.views.values() if not v.task.parent_task_id]
        for root in roots:
            walk(root)

    def _link_issues(self) -> None:
        for issue in self.issues:
            if issue.task_id and issue.task_id in self.views:
                view = self.views[issue.task_id]
                view.issue_ids.append(issue.id)
                if issue.status not in CLOSED_ISSUE_STATUSES:
                    view.open_issue_ids.append(issue.id)

    # --------------------------------------------------------------- schedule
    def _topological_order(self) -> list[int]:
        """Kahn's algorithm; nodes left over are part of a dependency cycle."""
        indegree = {tid: 0 for tid in self.views}
        for edge in self.edges:
            indegree[edge.successor_id] += 1
        queue = [tid for tid, deg in indegree.items() if deg == 0]
        order: list[int] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for succ in self.views[node].successor_ids:
                indegree[succ] -= 1
                if indegree[succ] == 0:
                    queue.append(succ)
        if len(order) != len(self.views):
            remaining = [tid for tid in self.views if tid not in set(order)]
            self.dependency_cycles.append(remaining)
            order.extend(remaining)
        return order

    def _compute_schedule(self) -> None:
        """Critical Path Method over calendar days.

        Durations come from the planned dates (inclusive). Tasks without dates
        get a one day placeholder so the graph still yields float values.
        """
        anchor = self.project.start_date or min(
            (t.planned_start for t in self.raw_tasks if t.planned_start), default=self.today
        )
        for view in self.views.values():
            if view.planned_start and view.planned_end:
                view.duration_days = max(1, _days(view.planned_end, view.planned_start) + 1)
            else:
                view.duration_days = 1

        order = self._topological_order()
        in_cycle = {tid for cycle in self.dependency_cycles for tid in cycle}

        # Forward pass -> earliest start / finish (day offsets from anchor).
        for tid in order:
            view = self.views[tid]
            base = _days(view.planned_start, anchor) if view.planned_start else 0
            earliest = base
            for pid in view.predecessor_ids:
                if pid in in_cycle and tid in in_cycle:
                    continue
                pred = self.views[pid]
                if pred.early_finish is None:
                    continue
                edge = self._edge(pid, tid)
                lag = edge.lag_days if edge else 0
                dep_type = edge.dependency_type if edge else "FS"
                if dep_type == "SS":
                    candidate = (pred.early_start or 0) + lag
                elif dep_type == "FF":
                    candidate = pred.early_finish + lag - view.duration_days + 1
                else:  # FS / SF fall back to finish-to-start
                    candidate = pred.early_finish + 1 + lag
                earliest = max(earliest, candidate)
            view.early_start = earliest
            view.early_finish = earliest + view.duration_days - 1

        # The backward pass anchors on the earliest possible project finish (the
        # longest chain), not on the contractual end date: that is what makes the
        # critical path show up as float == 0.
        project_finish = max((v.early_finish or 0) for v in self.views.values()) if self.views else 0

        # Backward pass -> latest start / finish and total float.
        for tid in reversed(order):
            view = self.views[tid]
            latest = project_finish
            for sid in view.successor_ids:
                if sid in in_cycle and tid in in_cycle:
                    continue
                succ = self.views[sid]
                if succ.late_start is None:
                    continue
                edge = self._edge(tid, sid)
                lag = edge.lag_days if edge else 0
                dep_type = edge.dependency_type if edge else "FS"
                if dep_type == "SS":
                    candidate = succ.late_start - lag + view.duration_days - 1
                elif dep_type == "FF":
                    candidate = (succ.late_finish or project_finish) - lag
                else:
                    candidate = succ.late_start - 1 - lag
                latest = min(latest, candidate)
            view.late_finish = latest
            view.late_start = latest - view.duration_days + 1
            if view.early_start is not None:
                view.total_float = view.late_start - view.early_start
                view.is_critical_path = view.total_float <= 0

    def _edge(self, pred_id: int, succ_id: int) -> DependencyEdge | None:
        for edge in self.edges:
            if edge.predecessor_id == pred_id and edge.successor_id == succ_id:
                return edge
        return None

    # ------------------------------------------------------------------ loads
    def _compute_loads(self) -> None:
        week_ahead = self.today + timedelta(days=7)
        for view in self.views.values():
            load = self.loads.get(view.owner_id) if view.owner_id else None
            if load is None:
                continue
            load.assigned_task_ids.append(view.id)
            if view.is_active:
                load.open_task_ids.append(view.id)
                if view.is_overdue:
                    load.overdue_task_ids.append(view.id)
                if view.priority in ("high", "critical"):
                    load.critical_task_ids.append(view.id)
                if view.planned_end and self.today <= view.planned_end <= week_ahead:
                    load.due_this_week_ids.append(view.id)
        for issue in self.issues:
            if issue.owner_id in self.loads and issue.status not in CLOSED_ISSUE_STATUSES:
                self.loads[issue.owner_id].open_issue_ids.append(issue.id)
        for load in self.loads.values():
            open_views = [self.views[i] for i in load.open_task_ids]
            load.average_progress = (
                round(sum(v.progress for v in open_views) / len(open_views), 1) if open_views else 0.0
            )

    def _finalise_loads(self) -> None:
        for load in self.loads.values():
            load.high_risk_task_ids = [
                tid for tid in load.open_task_ids if self.views[tid].risk_score >= 70
            ]

    # ------------------------------------------------------------------- risk
    def _compute_risks(self) -> None:
        from .risk import score_task  # imported late to avoid a circular import

        self.risk_details: dict[int, list] = {}
        for view in self.views.values():
            score, factors = score_task(self, view)
            view.risk_score = score
            view.risk_level = risk_level_for(score)
            self.risk_details[view.id] = factors

    # -------------------------------------------------------------- accessors
    def task_views(self) -> list[TaskView]:
        return list(self.views.values())

    def active_views(self) -> list[TaskView]:
        return [v for v in self.views.values() if v.is_active]

    def leaf_views(self) -> list[TaskView]:
        return [v for v in self.views.values() if v.is_leaf]

    def overdue_views(self) -> list[TaskView]:
        return [v for v in self.views.values() if v.is_overdue]

    def high_risk_views(self, threshold: float = 60.0) -> list[TaskView]:
        return sorted(
            [v for v in self.active_views() if v.risk_score >= threshold],
            key=lambda v: v.risk_score,
            reverse=True,
        )

    def open_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.status not in CLOSED_ISSUE_STATUSES]

    def issues_for_task(self, task_id: int) -> list[Issue]:
        return [i for i in self.issues if i.task_id == task_id]

    def open_issues_for_task(self, task_id: int) -> list[Issue]:
        return [i for i in self.issues_for_task(task_id) if i.status not in CLOSED_ISSUE_STATUSES]

    def ancestors(self, view: TaskView) -> list[TaskView]:
        """Parent chain from the root down to the direct parent."""
        chain: list[TaskView] = []
        seen: set[int] = {view.id}
        current = view.task.parent_task_id
        while current and current in self.views and current not in seen:
            seen.add(current)
            chain.append(self.views[current])
            current = self.views[current].task.parent_task_id
        chain.reverse()
        return chain

    def category_of(self, task_id: int | None) -> str | None:
        """The top level parent - what a PM reads as the task's category."""
        if task_id is None or task_id not in self.views:
            return None
        chain = self.ancestors(self.views[task_id])
        return chain[0].title if chain else None

    def is_descendant_of(self, view: TaskView, ancestor_id: int) -> bool:
        return any(a.id == ancestor_id for a in self.ancestors(view))

    def owner_name(self, owner_id: int | None) -> str | None:
        person = self.people_by_id.get(owner_id) if owner_id else None
        return person.name if person else None

    def child_progress_rollup(self, view: TaskView) -> float | None:
        """Duration weighted progress of the children of a summary task."""
        return view.rollup_progress

    def average_progress(self) -> float:
        leaves = [v for v in self.leaf_views() if not v.is_cancelled]
        if not leaves:
            return 0.0
        return round(sum(v.progress for v in leaves) / len(leaves), 1)

    def schedule_variance_days(self) -> float:
        variances = [v.schedule_variance_days for v in self.views.values()]
        values = [v for v in variances if v is not None]
        if not values:
            return 0.0
        return round(sum(values) / len(values), 1)

    def next_milestone(self) -> Milestone | None:
        upcoming = [
            m
            for m in self.milestones
            if m.due_date and m.status == "pending" and m.due_date >= self.today
        ]
        if upcoming:
            return sorted(upcoming, key=lambda m: m.due_date)[0]
        pending = [m for m in self.milestones if m.status == "pending" and m.due_date]
        return sorted(pending, key=lambda m: m.due_date)[0] if pending else None


def risk_level_for(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def build_snapshot(db: Session, project_id: int, today: date | None = None) -> ProjectSnapshot:
    project = db.get(Project, project_id)
    if project is None:
        raise LookupError(f"project {project_id} not found")
    tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)))
    task_ids = [t.id for t in tasks]
    dependencies = (
        list(
            db.scalars(
                select(TaskDependency).where(TaskDependency.successor_task_id.in_(task_ids))
            )
        )
        if task_ids
        else []
    )
    people = list(db.scalars(select(Person).where(Person.project_id == project_id)))
    issues = list(db.scalars(select(Issue).where(Issue.project_id == project_id)))
    milestones = list(db.scalars(select(Milestone).where(Milestone.project_id == project_id)))
    return ProjectSnapshot(project, tasks, dependencies, people, issues, milestones, today=today)


__all__ = [
    "ProjectSnapshot",
    "TaskView",
    "PersonLoad",
    "build_snapshot",
    "risk_level_for",
]
