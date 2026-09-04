"""Risk scoring: every score must be explainable and ordered sensibly."""
from __future__ import annotations

from app.analysis.snapshot import build_snapshot, risk_level_for

from .conftest import TODAY, day


def snapshot(db, project):
    return build_snapshot(db, project.id, today=TODAY)


def test_completed_tasks_have_no_risk(db, project, factory):
    task = factory.task("完了済み", planned_end=day(-10), status="done", progress=100)
    view = snapshot(db, project).views[task.id]
    assert view.risk_score == 0
    assert view.risk_level == "low"


def test_healthy_future_task_is_low_risk(db, project, factory):
    person = factory.person("Alice", capacity_tasks=8)
    task = factory.task(
        "順調タスク", owner_id=person.id, planned_start=day(10), planned_end=day(30),
        status="not_started", progress=0,
    )
    view = snapshot(db, project).views[task.id]
    assert view.risk_score < 35
    assert view.risk_level == "low"


def test_overdue_task_scores_higher_the_longer_it_slips(db, project, factory):
    slight = factory.task("1日遅れ", planned_start=day(-10), planned_end=day(-1), status="in_progress", progress=50)
    severe = factory.task("15日遅れ", planned_start=day(-30), planned_end=day(-15), status="in_progress", progress=50)
    snap = snapshot(db, project)
    assert snap.views[severe.id].risk_score > snap.views[slight.id].risk_score
    assert snap.views[severe.id].is_overdue is True
    assert snap.views[severe.id].days_overdue == 15


def test_risk_factors_are_evidence_backed(db, project, factory):
    person = factory.person("Bob", capacity_tasks=1)
    predecessor = factory.task("前工程", planned_end=day(-5), status="in_progress", progress=30)
    task = factory.task(
        "後続タスク", owner_id=person.id, planned_start=day(-6), planned_end=day(-2),
        status="in_progress", progress=10, priority="critical",
    )
    factory.task("負荷用タスク", owner_id=person.id, planned_end=day(20), status="not_started")
    factory.dependency(predecessor, task)
    factory.issue("未解決の課題", task_id=task.id, severity="high", status="open")

    snap = snapshot(db, project)
    view = snap.views[task.id]
    factors = {f.key for f in snap.risk_details[task.id]}

    assert {"overdue", "progress_gap", "predecessor_delay", "owner_load", "open_issues", "priority"} <= factors
    assert view.risk_score >= 70
    assert view.risk_level in ("high", "critical")
    # Every factor carries a human readable detail - no bare verdicts allowed.
    assert all(f.detail for f in snap.risk_details[task.id])


def test_unassigned_task_is_flagged(db, project, factory):
    task = factory.task("担当未定", planned_start=day(-1), planned_end=day(10), status="not_started")
    snap = snapshot(db, project)
    assert "owner_missing" in {f.key for f in snap.risk_details[task.id]}


def test_due_soon_with_low_progress_is_risky(db, project, factory):
    task = factory.task(
        "期限逼迫", planned_start=day(-10), planned_end=day(2), status="in_progress", progress=15
    )
    snap = snapshot(db, project)
    keys = {f.key for f in snap.risk_details[task.id]}
    assert "due_soon" in keys and "progress_gap" in keys
    assert snap.views[task.id].risk_score >= 35


def test_risk_score_is_capped_and_levels_are_monotonic():
    assert risk_level_for(0) == "low"
    assert risk_level_for(45) == "medium"
    assert risk_level_for(65) == "high"
    assert risk_level_for(95) == "critical"


def test_expected_progress_and_gap(db, project, factory):
    task = factory.task(
        "半分経過", planned_start=day(-5), planned_end=day(5), status="in_progress", progress=10
    )
    view = snapshot(db, project).views[task.id]
    assert 45 <= view.expected_progress <= 55
    assert view.progress_gap > 30


def test_critical_path_and_float(db, project, factory):
    first = factory.task("A", planned_start=day(0), planned_end=day(4))
    second = factory.task("B", planned_start=day(5), planned_end=day(9))
    parallel = factory.task("C", planned_start=day(0), planned_end=day(1))
    factory.dependency(first, second)

    snap = snapshot(db, project)
    assert snap.views[first.id].is_critical_path is True
    assert snap.views[second.id].is_critical_path is True
    # The short parallel task has slack, so it is not on the critical path.
    assert snap.views[parallel.id].total_float > 0
    assert snap.views[parallel.id].is_critical_path is False


def test_dependency_cycle_is_detected_without_crashing(db, project, factory):
    a = factory.task("A", planned_start=day(0), planned_end=day(2))
    b = factory.task("B", planned_start=day(3), planned_end=day(5))
    factory.dependency(a, b)
    factory.dependency(b, a)

    snap = snapshot(db, project)
    assert snap.dependency_cycles
    assert {a.id, b.id} <= set(snap.dependency_cycles[0])
