"""Rule based delay risk scoring (0-100).

Each rule contributes a weighted number of points *and* a human readable piece
of evidence, so a score can always be explained line by line. The LLM layer
never invents a score - it only narrates the factors produced here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .snapshot import ProjectSnapshot, TaskView

HIGH_SEVERITIES = ("high", "critical")


@dataclass
class Factor:
    key: str
    label: str
    points: float
    detail: str


def _clamp(value: float, ceiling: float) -> float:
    return round(min(value, ceiling), 1)


def score_task(snapshot: "ProjectSnapshot", view: "TaskView") -> tuple[float, list[Factor]]:
    """Return (risk_score, factors) for a single task."""
    if not view.is_active:
        return 0.0, []

    factors: list[Factor] = []

    # 1. Already overdue - the strongest signal there is.
    if view.is_overdue:
        factors.append(
            Factor(
                key="overdue",
                label="期限超過",
                points=_clamp(12 + 3.5 * view.days_overdue, 40),
                detail=f"予定終了日 {view.planned_end} を {view.days_overdue} 日超過（進捗 {view.progress:.0f}%）",
            )
        )

    # 2. Behind the linear burn-down.
    gap = view.progress_gap
    if gap > 5:
        factors.append(
            Factor(
                key="progress_gap",
                label="進捗遅れ",
                points=_clamp(gap * 0.35, 25),
                detail=f"想定進捗 {view.expected_progress:.0f}% に対し実績 {view.progress:.0f}%（差 {gap:.0f}pt）",
            )
        )

    # 3. Due soon but not nearly finished.
    days_to_due = view.days_to_due
    if not view.is_overdue and days_to_due is not None and 0 <= days_to_due <= 7 and view.progress < 80:
        factors.append(
            Factor(
                key="due_soon",
                label="期限逼迫",
                points=_clamp((8 - days_to_due) * 1.8 + (80 - view.progress) * 0.1, 18),
                detail=f"残り {days_to_due} 日で進捗 {view.progress:.0f}%",
            )
        )

    # 4. Upstream work is not finished.
    blocking = [snapshot.views[p] for p in view.predecessor_ids if not snapshot.views[p].is_done]
    if blocking:
        overdue_preds = [p for p in blocking if p.is_overdue]
        names = "、".join(p.label() for p in blocking[:3])
        factors.append(
            Factor(
                key="predecessor_delay",
                label="前工程未完了",
                points=_clamp(6 * len(blocking) + 4 * len(overdue_preds), 20),
                detail=f"前工程 {len(blocking)} 件が未完了（{names}）"
                + (f" / うち期限超過 {len(overdue_preds)} 件" if overdue_preds else ""),
            )
        )

    # 5. Owner availability.
    if view.owner_id is None:
        factors.append(
            Factor(
                key="owner_missing",
                label="Owner未設定",
                points=8,
                detail="担当者が設定されていないため進捗責任者が不在",
            )
        )
    else:
        load = snapshot.loads.get(view.owner_id)
        if load and load.load_level in ("overloaded", "high"):
            points = 10 if load.load_level == "overloaded" else 6
            factors.append(
                Factor(
                    key="owner_load",
                    label="担当者負荷",
                    points=points,
                    detail=(
                        f"{load.person.name} は未完了 {len(load.open_task_ids)} 件 "
                        f"(capacity {load.capacity}、負荷率 {load.load_ratio:.2f})"
                    ),
                )
            )

    # 6. Unresolved issues hanging off the task.
    open_issues = snapshot.open_issues_for_task(view.id)
    if open_issues:
        severe = [i for i in open_issues if i.severity in HIGH_SEVERITIES]
        factors.append(
            Factor(
                key="open_issues",
                label="未解決Issue",
                points=_clamp(4 * len(open_issues) + 4 * len(severe), 15),
                detail=f"未解決Issue {len(open_issues)} 件"
                + (f"（Severity高 {len(severe)} 件: {open_issues[0].title}）" if severe else ""),
            )
        )

    # 7. Schedule slack.
    if view.total_float is not None:
        if view.total_float <= 0:
            factors.append(
                Factor(
                    key="critical_path",
                    label="Float無し",
                    points=10,
                    detail=f"総Float {view.total_float} 日（クリティカルパス上）",
                )
            )
        elif view.total_float <= 3:
            factors.append(
                Factor(
                    key="low_float",
                    label="Float僅少",
                    points=6,
                    detail=f"総Float {view.total_float} 日のみ",
                )
            )

    # 8. How much work sits behind this task.
    if view.successor_ids:
        factors.append(
            Factor(
                key="downstream",
                label="後続影響",
                points=_clamp(3 * len(view.successor_ids), 9),
                detail=f"後続Task {len(view.successor_ids)} 件がこのTaskを待っている",
            )
        )

    # 9. Explicitly blocked.
    if view.status == "blocked":
        factors.append(
            Factor(key="blocked", label="Blocked", points=8, detail="Statusが blocked のまま")
        )

    # 10. Nobody has touched it in a while.
    if view.status == "in_progress" and view.days_since_update >= 14:
        factors.append(
            Factor(
                key="stale",
                label="更新停滞",
                points=6,
                detail=f"{view.days_since_update} 日間更新なしで進行中",
            )
        )

    # 11. Should have started but has not.
    if view.status == "not_started" and view.planned_start and view.planned_start < snapshot.today:
        late = (snapshot.today - view.planned_start).days
        factors.append(
            Factor(
                key="not_started",
                label="未着手",
                points=_clamp(2 * late, 12),
                detail=f"予定開始日 {view.planned_start} から {late} 日未着手",
            )
        )

    # 12. Priority amplifies everything above.
    if factors and view.priority in HIGH_SEVERITIES:
        factors.append(
            Factor(
                key="priority",
                label="高優先度",
                points=6 if view.priority == "critical" else 3,
                detail=f"Priority = {view.priority}",
            )
        )

    score = round(min(100.0, sum(f.points for f in factors)), 1)
    return score, factors


def risk_reasons(factors: list[Factor]) -> list[str]:
    return [f"{f.label}: {f.detail}" for f in sorted(factors, key=lambda f: f.points, reverse=True)]


def impact_statement(snapshot: "ProjectSnapshot", view: "TaskView") -> str:
    """Describe what breaks downstream if this task slips further."""
    parts: list[str] = []
    if view.successor_ids:
        successors = [snapshot.views[s] for s in view.successor_ids]
        parts.append(f"後続Task {len(successors)} 件（{'、'.join(s.label() for s in successors[:3])}）が着手不可")
    if view.is_critical_path:
        parts.append("クリティカルパス上のためプロジェクト完了日が同日数だけ後ろ倒し")
    milestone = snapshot.next_milestone()
    if milestone and milestone.due_date and view.planned_end:
        buffer_days = (milestone.due_date - view.planned_end).days
        if buffer_days <= 10:
            parts.append(f"マイルストーン「{milestone.title}」({milestone.due_date}) まで余裕 {buffer_days} 日")
    if view.priority in HIGH_SEVERITIES:
        parts.append(f"Priority {view.priority} のためスコープまたは品質への影響が大きい")
    if not parts:
        parts.append("直接の後続はないが、担当者の稼働を占有し他Taskの着手を遅らせる")
    return " / ".join(parts)


def top_risks(snapshot: "ProjectSnapshot", threshold: float = 40.0, limit: int = 20) -> list["TaskView"]:
    ranked = sorted(
        [v for v in snapshot.active_views() if v.risk_score >= threshold],
        key=lambda v: (v.risk_score, v.days_overdue),
        reverse=True,
    )
    return ranked[:limit]
