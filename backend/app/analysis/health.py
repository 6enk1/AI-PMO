"""Project health score and the "today's focus" queue for the Command Center."""
from __future__ import annotations

from dataclasses import dataclass

from .findings import RawFinding, severity_rank
from .snapshot import ProjectSnapshot

HIGH_SEVERITIES = ("high", "critical")


@dataclass
class Penalty:
    key: str
    label: str
    penalty: float
    detail: str


@dataclass
class Focus:
    kind: str
    ref_id: int | None
    title: str
    detail: str
    severity: str
    score: float
    link: str | None = None


def compute_health(snapshot: ProjectSnapshot, hidden: list[RawFinding]) -> tuple[float, str, list[Penalty]]:
    active = snapshot.active_views()
    penalties: list[Penalty] = []

    if active:
        overdue = snapshot.overdue_views()
        if overdue:
            ratio = len(overdue) / len(active)
            penalties.append(
                Penalty(
                    "overdue",
                    "期限超過Task",
                    round(min(40.0, ratio * 100 * 0.8), 1),
                    f"未完了 {len(active)} 件中 {len(overdue)} 件が期限超過（{ratio * 100:.0f}%）",
                )
            )
        high_risk = [v for v in active if v.risk_score >= 60 and not v.is_overdue]
        if high_risk:
            ratio = len(high_risk) / len(active)
            penalties.append(
                Penalty(
                    "high_risk",
                    "高リスクTask",
                    round(min(20.0, ratio * 100 * 0.5), 1),
                    f"Risk Score 60以上が {len(high_risk)} 件（期限超過を除く）",
                )
            )
        gaps = [v.progress_gap for v in active if v.progress_gap > 0]
        if gaps:
            avg_gap = sum(gaps) / len(active)
            penalties.append(
                Penalty(
                    "progress_gap",
                    "進捗遅れ",
                    round(min(12.0, avg_gap * 0.25), 1),
                    f"未完了Task平均で想定進捗より {avg_gap:.0f}pt 遅れ",
                )
            )
        unassigned = [v for v in active if v.owner_id is None and v.is_leaf]
        if unassigned:
            penalties.append(
                Penalty(
                    "unassigned",
                    "Owner未設定",
                    round(min(10.0, len(unassigned) / len(active) * 100 * 0.3), 1),
                    f"Owner未設定のTaskが {len(unassigned)} 件",
                )
            )

    severe_issues = [i for i in snapshot.open_issues() if i.severity in HIGH_SEVERITIES]
    if severe_issues:
        penalties.append(
            Penalty(
                "issues",
                "高Severity Issue",
                round(min(15.0, 3.0 * len(severe_issues)), 1),
                f"未解決の高Severity Issueが {len(severe_issues)} 件",
            )
        )

    critical_hidden = [f for f in hidden if f.severity == "critical"]
    high_hidden = [f for f in hidden if f.severity == "high"]
    if critical_hidden or high_hidden:
        penalties.append(
            Penalty(
                "hidden",
                "Hidden Issue",
                round(min(15.0, 5.0 * len(critical_hidden) + 2.0 * len(high_hidden)), 1),
                f"重大なHidden Issue {len(critical_hidden)} 件 / 高 {len(high_hidden)} 件",
            )
        )

    score = round(max(0.0, 100.0 - sum(p.penalty for p in penalties)), 1)
    if score >= 80:
        label = "良好"
    elif score >= 60:
        label = "注意"
    elif score >= 40:
        label = "要対応"
    else:
        label = "危険"
    return score, label, penalties


def build_focus_items(
    snapshot: ProjectSnapshot, hidden: list[RawFinding], limit: int = 8
) -> list[Focus]:
    """The 5-10 things the PM should actually look at today."""
    items: list[Focus] = []

    for v in sorted(snapshot.overdue_views(), key=lambda v: v.risk_score, reverse=True)[:5]:
        items.append(
            Focus(
                kind="overdue_task",
                ref_id=v.id,
                title=f"期限超過 {v.days_overdue} 日: {v.label()}",
                detail=(
                    f"担当 {snapshot.owner_name(v.owner_id) or '未設定'} / 進捗 {v.progress:.0f}% / "
                    f"Risk {v.risk_score:.0f}"
                ),
                severity="critical" if v.days_overdue >= 7 else "high",
                score=90 + v.risk_score / 10 + v.days_overdue,
                link="/tasks",
            )
        )

    for v in snapshot.high_risk_views(threshold=60)[:5]:
        if v.is_overdue:
            continue
        items.append(
            Focus(
                kind="high_risk_task",
                ref_id=v.id,
                title=f"高リスク（{v.risk_score:.0f}）: {v.label()}",
                detail=(
                    f"残り {v.days_to_due} 日 / 進捗 {v.progress:.0f}%（想定 {v.expected_progress:.0f}%）"
                    if v.days_to_due is not None
                    else f"進捗 {v.progress:.0f}%"
                ),
                severity=v.risk_level if v.risk_level in ("critical", "high") else "medium",
                score=60 + v.risk_score / 5,
                link="/ai-pmo",
            )
        )

    for f in hidden[:5]:
        if severity_rank(f.severity) < 2:
            continue
        items.append(
            Focus(
                kind="hidden_issue",
                ref_id=f.task_id or f.person_id,
                title=f"Hidden Issue: {f.title}",
                detail=f.evidence[0].detail if f.evidence else f.impact,
                severity=f.severity,
                score=70 + severity_rank(f.severity) * 8,
                link="/ai-pmo",
            )
        )

    for issue in snapshot.open_issues():
        overdue = bool(issue.due_date and issue.due_date < snapshot.today)
        if issue.severity not in HIGH_SEVERITIES and not overdue:
            continue
        items.append(
            Focus(
                kind="issue",
                ref_id=issue.id,
                title=f"{'期限超過Issue' if overdue else '重要Issue'}: {issue.title}",
                detail=(
                    f"Severity {issue.severity} / 担当 {snapshot.owner_name(issue.owner_id) or '未設定'}"
                    + (f" / 期限 {issue.due_date}" if issue.due_date else "")
                ),
                severity="critical" if (overdue and issue.severity == "critical") else issue.severity,
                score=65 + severity_rank(issue.severity) * 6 + (10 if overdue else 0),
                link="/issues",
            )
        )

    milestone = snapshot.next_milestone()
    if milestone and milestone.due_date:
        days_left = (milestone.due_date - snapshot.today).days
        if days_left <= 21:
            blockers = [
                v for v in snapshot.active_views() if v.planned_end and v.planned_end <= milestone.due_date
            ]
            items.append(
                Focus(
                    kind="milestone",
                    ref_id=milestone.id,
                    title=f"マイルストーン「{milestone.title}」まで {days_left} 日",
                    detail=f"期日までに完了すべき未完了Task {len(blockers)} 件",
                    severity="critical" if days_left <= 3 and blockers else "high" if blockers else "medium",
                    score=75 + max(0, 21 - days_left),
                    link="/schedule",
                )
            )

    items.sort(key=lambda i: (severity_rank(i.severity), i.score), reverse=True)
    deduped: list[Focus] = []
    seen: set[tuple[str, int | None]] = set()
    for item in items:
        key = (item.kind, item.ref_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:limit]
