"""Serialisation helpers that glue the analysis engine to the API schemas."""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import schemas
from .analysis.delay_actions import build_delay_actions
from .analysis.findings import RawFinding
from .analysis.health import build_focus_items, compute_health
from .analysis.hidden_issues import detect_hidden_issues
from .analysis.risk import impact_statement, risk_reasons
from .analysis.snapshot import ProjectSnapshot, TaskView
from .models import AIRiskFinding, Issue, Milestone, utcnow


def task_to_read(view: TaskView, snapshot: ProjectSnapshot) -> schemas.TaskRead:
    task = view.task
    return schemas.TaskRead(
        id=task.id,
        project_id=task.project_id,
        code=task.code,
        title=task.title,
        description=task.description,
        parent_task_id=task.parent_task_id,
        owner_id=task.owner_id,
        planned_start=task.planned_start,
        planned_end=task.planned_end,
        actual_start=task.actual_start,
        actual_end=task.actual_end,
        progress=task.progress,
        status=task.status,
        priority=task.priority,
        estimated_hours=task.estimated_hours,
        notes=task.notes,
        created_at=task.created_at,
        updated_at=task.updated_at,
        owner_name=snapshot.owner_name(task.owner_id),
        predecessor_task_ids=view.predecessor_ids,
        successor_task_ids=view.successor_ids,
        child_task_ids=view.child_ids,
        issue_ids=view.issue_ids,
        open_issue_count=len(view.open_issue_ids),
        is_overdue=view.is_overdue,
        days_overdue=view.days_overdue,
        days_to_due=view.days_to_due,
        expected_progress=view.expected_progress,
        progress_gap=view.progress_gap,
        risk_score=view.risk_score,
        risk_level=view.risk_level,
        total_float=view.total_float,
        is_critical_path=view.is_critical_path,
    )


def issue_to_read(issue: Issue, snapshot: ProjectSnapshot | None = None) -> schemas.IssueRead:
    today = snapshot.today if snapshot else date.today()
    task_title = None
    if snapshot and issue.task_id in snapshot.views:
        task_title = snapshot.views[issue.task_id].label()
    elif issue.task is not None:
        task_title = issue.task.title
    return schemas.IssueRead(
        id=issue.id,
        project_id=issue.project_id,
        code=issue.code,
        task_id=issue.task_id,
        title=issue.title,
        description=issue.description,
        severity=issue.severity,
        owner_id=issue.owner_id,
        raised_on=issue.raised_on,
        due_date=issue.due_date,
        status=issue.status,
        action_plan=issue.action_plan,
        resolution=issue.resolution,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        owner_name=snapshot.owner_name(issue.owner_id) if snapshot else (issue.owner.name if issue.owner else None),
        task_title=task_title,
        is_overdue=bool(issue.due_date and issue.due_date < today and issue.status not in ("resolved", "closed")),
    )


def milestone_to_read(milestone: Milestone, snapshot: ProjectSnapshot | None = None) -> schemas.MilestoneRead:
    today = snapshot.today if snapshot else date.today()
    days_remaining = (milestone.due_date - today).days if milestone.due_date else None
    at_risk = False
    if snapshot and milestone.due_date and milestone.status == "pending":
        blockers = [
            v for v in snapshot.active_views() if v.planned_end and v.planned_end <= milestone.due_date
        ]
        at_risk = any(v.is_overdue or v.risk_score >= 60 for v in blockers)
    return schemas.MilestoneRead(
        id=milestone.id,
        project_id=milestone.project_id,
        title=milestone.title,
        description=milestone.description,
        due_date=milestone.due_date,
        status=milestone.status,
        days_remaining=days_remaining,
        at_risk=at_risk,
    )


def person_workload(person_id: int, snapshot: ProjectSnapshot) -> schemas.PersonWorkload:
    load = snapshot.loads[person_id]
    person = load.person
    return schemas.PersonWorkload(
        id=person.id,
        project_id=person.project_id,
        name=person.name,
        role=person.role,
        email=person.email,
        capacity_tasks=person.capacity_tasks,
        assigned_task_count=len(load.assigned_task_ids),
        open_task_count=len(load.open_task_ids),
        overdue_task_count=len(load.overdue_task_ids),
        high_risk_task_count=len(load.high_risk_task_ids),
        critical_task_count=len(load.critical_task_ids),
        due_this_week_count=len(load.due_this_week_ids),
        open_issue_count=len(load.open_issue_ids),
        average_progress=load.average_progress,
        load_ratio=load.load_ratio,
        load_level=load.load_level,
        task_ids=load.assigned_task_ids,
    )


def finding_to_schema(raw: RawFinding, index: int) -> schemas.Finding:
    return schemas.Finding(
        id=f"{raw.category}-{index}",
        category=raw.category,  # type: ignore[arg-type]
        finding_type=raw.finding_type,
        title=raw.title,
        severity=raw.severity,  # type: ignore[arg-type]
        confidence=raw.confidence,
        risk_score=raw.risk_score,
        task_id=raw.task_id,
        task_title=raw.task_title,
        person_id=raw.person_id,
        person_name=raw.person_name,
        explanation=raw.explanation or raw.title,
        reasoning_summary=raw.reasoning_summary or "構造化分析で検出したシグナルに基づく判定",
        evidence=[schemas.EvidenceItem(label=e.label, detail=e.detail) for e in raw.evidence],
        impact=raw.impact,
        cause_hypothesis=raw.cause_hypothesis,
        cause_category=raw.cause_category,
        recommended_actions=[
            schemas.RecommendedAction(action=a.action, why=a.why, effort=a.effort, owner_hint=a.owner_hint)
            for a in raw.actions
        ],
        recommended_action=raw.recommended_action or (raw.actions[0].action if raw.actions else None),
        recommended_action_why=raw.recommended_action_why or (raw.actions[0].why if raw.actions else None),
        source=raw.source,
    )


def task_risk(view: TaskView, snapshot: ProjectSnapshot) -> schemas.TaskRisk:
    factors = snapshot.risk_details.get(view.id, [])
    return schemas.TaskRisk(
        task_id=view.id,
        task_code=view.code,
        task_title=view.title,
        owner_name=snapshot.owner_name(view.owner_id),
        planned_end=view.planned_end,
        progress=view.progress,
        status=view.status,
        priority=view.priority,
        risk_score=view.risk_score,
        risk_level=view.risk_level,
        days_overdue=view.days_overdue,
        days_to_due=view.days_to_due,
        factors=[
            schemas.RiskFactor(key=f.key, label=f.label, points=f.points, detail=f.detail) for f in factors
        ],
        reasons=risk_reasons(factors),
        impact=impact_statement(snapshot, view),
    )


def _default_explanations(findings: list[RawFinding]) -> list[RawFinding]:
    """Guarantee the narrative fields are populated even without an LLM."""
    for f in findings:
        if not f.explanation:
            evidence = "、".join(f"{e.label}: {e.detail}" for e in f.evidence[:2])
            f.explanation = f"{f.title}。根拠 - {evidence}"
        if not f.reasoning_summary:
            f.reasoning_summary = (
                f"検出ルール「{f.finding_type}」が {len(f.evidence)} 件の根拠を満たしたため、"
                f"Severity {f.severity} と判定した。"
            )
        if not f.recommended_action and f.actions:
            f.recommended_action = f.actions[0].action
            f.recommended_action_why = f.actions[0].why
    return findings


def build_dashboard(snapshot: ProjectSnapshot) -> schemas.DashboardResponse:
    hidden = _default_explanations(detect_hidden_issues(snapshot))
    score, label, penalties = compute_health(snapshot, hidden)
    focus = build_focus_items(snapshot, hidden, limit=10)
    active = snapshot.active_views()
    milestone = snapshot.next_milestone()
    return schemas.DashboardResponse(
        project=schemas.ProjectRead.model_validate(snapshot.project),
        as_of=snapshot.today,
        health_score=score,
        health_label=label,
        health_breakdown=[
            schemas.HealthBreakdown(key=p.key, label=p.label, penalty=p.penalty, detail=p.detail)
            for p in penalties
        ],
        total_tasks=len(snapshot.views),
        open_tasks=len(active),
        done_tasks=len([v for v in snapshot.task_views() if v.is_done]),
        overdue_tasks=len(snapshot.overdue_views()),
        high_risk_tasks=len([v for v in active if v.risk_score >= 60]),
        hidden_issue_count=len(hidden),
        open_issue_count=len(snapshot.open_issues()),
        critical_issue_count=len([i for i in snapshot.open_issues() if i.severity in ("high", "critical")]),
        unassigned_tasks=len([v for v in active if v.owner_id is None and v.is_leaf]),
        average_progress=snapshot.average_progress(),
        schedule_variance_days=snapshot.schedule_variance_days(),
        next_milestone=milestone_to_read(milestone, snapshot) if milestone else None,
        milestones=[milestone_to_read(m, snapshot) for m in sorted(
            snapshot.milestones, key=lambda m: (m.due_date is None, m.due_date)
        )],
        focus_items=[
            schemas.FocusItem(
                kind=f.kind,
                ref_id=f.ref_id,
                title=f.title,
                detail=f.detail,
                severity=f.severity,  # type: ignore[arg-type]
                score=round(f.score, 1),
                link=f.link,
            )
            for f in focus
        ],
    )


def build_ai_pmo(
    db: Session,
    snapshot: ProjectSnapshot,
    use_llm: bool = True,
    persist: bool = True,
    risk_threshold: float = 40.0,
) -> schemas.AIPMOResponse:
    """Structured analysis -> LLM reasoning -> recommendations."""
    from .ai.llm import enrich_findings

    hidden = detect_hidden_issues(snapshot)
    actions = build_delay_actions(snapshot, risk_threshold=max(50.0, risk_threshold))
    all_findings = hidden + actions

    llm_used, llm_note = False, None
    if use_llm and all_findings:
        context = {
            "project": snapshot.project.name,
            "as_of": str(snapshot.today),
            "task_count": len(snapshot.views),
            "open_tasks": len(snapshot.active_views()),
            "overdue_tasks": len(snapshot.overdue_views()),
            "open_issues": len(snapshot.open_issues()),
        }
        result = enrich_findings(all_findings, context)
        all_findings = result.findings
        llm_used, llm_note = result.llm_used, result.note
    all_findings = _default_explanations(all_findings)

    hidden_schema = [finding_to_schema(f, i) for i, f in enumerate(f for f in all_findings if f.category == "hidden_issue")]
    action_schema = [finding_to_schema(f, i) for i, f in enumerate(f for f in all_findings if f.category == "delay_action")]
    risks = [task_risk(v, snapshot) for v in snapshot.high_risk_views(threshold=risk_threshold)]
    action_by_task = {f.task_id: f for f in action_schema}
    for risk in risks:
        action = action_by_task.get(risk.task_id)
        if action:
            risk.recommended_action = action.recommended_action

    recommended = sorted(
        hidden_schema + action_schema,
        key=lambda f: ({"critical": 3, "high": 2, "medium": 1, "low": 0}[f.severity], f.risk_score or 0, f.confidence),
        reverse=True,
    )[:10]

    if persist:
        persist_findings(db, snapshot.project.id, all_findings)

    return schemas.AIPMOResponse(
        project_id=snapshot.project.id,
        as_of=snapshot.today,
        generated_at=utcnow(),
        llm_used=llm_used,
        llm_note=llm_note,
        hidden_issues=hidden_schema,
        delay_risks=risks,
        delay_actions=action_schema,
        recommended_actions=recommended,
    )


def persist_findings(db: Session, project_id: int, findings: list[RawFinding]) -> None:
    """Replace the stored findings for the project with this run's output."""
    db.execute(delete(AIRiskFinding).where(AIRiskFinding.project_id == project_id))
    for f in findings:
        db.add(
            AIRiskFinding(
                project_id=project_id,
                task_id=f.task_id,
                person_id=f.person_id,
                category=f.category,
                finding_type=f.finding_type,
                severity=f.severity,
                risk_score=f.risk_score,
                confidence=f.confidence,
                title=f.title,
                explanation=f.explanation,
                reasoning_summary=f.reasoning_summary,
                evidence=json.dumps(
                    [{"label": e.label, "detail": e.detail} for e in f.evidence], ensure_ascii=False
                ),
                impact=f.impact,
                suggested_action=f.recommended_action,
                suggested_actions=json.dumps(
                    [{"action": a.action, "why": a.why, "effort": a.effort} for a in f.actions],
                    ensure_ascii=False,
                ),
                recommended_reason=f.recommended_action_why,
                source=f.source,
            )
        )
    db.commit()
