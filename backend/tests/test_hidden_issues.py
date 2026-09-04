"""Hidden issue detection - findings must be specific and evidence backed."""
from __future__ import annotations

from app.analysis.hidden_issues import detect_hidden_issues
from app.analysis.snapshot import build_snapshot

from .conftest import TODAY, day


def detect(db, project):
    return detect_hidden_issues(build_snapshot(db, project.id, today=TODAY))


def types_of(findings):
    return {f.finding_type for f in findings}


def test_no_findings_for_a_healthy_project(db, project, factory):
    person = factory.person("Alice", capacity_tasks=8)
    factory.task("順調", owner_id=person.id, planned_start=day(1), planned_end=day(20),
                 status="not_started", progress=0)
    assert detect(db, project) == []


def test_stalled_near_completion(db, project, factory):
    person = factory.person("Bob")
    factory.task("DB設計", owner_id=person.id, planned_start=day(-20), planned_end=day(-6),
                 actual_start=day(-20), status="in_progress", progress=95)
    findings = detect(db, project)
    assert "stalled_near_completion" in types_of(findings)
    finding = next(f for f in findings if f.finding_type == "stalled_near_completion")
    assert finding.evidence and finding.impact
    assert finding.actions
    assert "6" in " ".join(e.detail for e in finding.evidence)  # 6日超過が根拠に出る


def test_due_soon_with_low_progress(db, project, factory):
    person = factory.person("Bob")
    factory.task("移行設計", owner_id=person.id, planned_start=day(-5), planned_end=day(2),
                 actual_start=day(-5), status="in_progress", progress=20)
    assert "due_soon_low_progress" in types_of(detect(db, project))


def test_owner_missing(db, project, factory):
    factory.task("テスト計画", planned_start=day(1), planned_end=day(8), status="not_started")
    findings = [f for f in detect(db, project) if f.finding_type == "owner_missing"]
    assert findings and findings[0].severity in ("medium", "high")


def test_owner_overload_and_critical_concentration(db, project, factory):
    person = factory.person("田中", capacity_tasks=2)
    for i in range(5):
        factory.task(f"タスク{i}", owner_id=person.id, planned_start=day(1), planned_end=day(20),
                     status="not_started", priority="critical")
    found = types_of(detect(db, project))
    assert "owner_overload" in found
    assert "critical_task_concentration" in found


def test_successor_start_blocked(db, project, factory):
    person = factory.person("Alice")
    predecessor = factory.task("前工程", owner_id=person.id, planned_start=day(-10),
                               planned_end=day(-1), status="in_progress", progress=40)
    successor = factory.task("後続", owner_id=person.id, planned_start=day(0),
                             planned_end=day(10), status="not_started", progress=0)
    factory.dependency(predecessor, successor)
    findings = [f for f in detect(db, project) if f.finding_type == "successor_start_blocked"]
    assert findings and findings[0].task_id == successor.id


def test_dependency_date_conflict(db, project, factory):
    first = factory.task("設計", planned_start=day(1), planned_end=day(10))
    second = factory.task("実装", planned_start=day(5), planned_end=day(20))
    factory.dependency(first, second)
    findings = [f for f in detect(db, project) if f.finding_type == "dependency_date_conflict"]
    assert findings
    assert "5" in " ".join(e.detail for e in findings[0].evidence)


def test_dependency_cycle_is_reported_as_critical(db, project, factory):
    a = factory.task("A", planned_start=day(1), planned_end=day(3))
    b = factory.task("B", planned_start=day(4), planned_end=day(6))
    factory.dependency(a, b)
    factory.dependency(b, a)
    findings = [f for f in detect(db, project) if f.finding_type == "dependency_cycle"]
    assert findings and findings[0].severity == "critical"


def test_green_but_issue_heavy(db, project, factory):
    person = factory.person("Alice")
    task = factory.task("画面実装", owner_id=person.id, planned_start=day(-2), planned_end=day(20),
                        status="in_progress", progress=30, actual_start=day(-2))
    factory.issue("性能要件未確定", task_id=task.id, severity="high", status="open", owner_id=person.id, due_date=day(5))
    factory.issue("外部IF仕様未定", task_id=task.id, severity="medium", status="open", owner_id=person.id, due_date=day(5))
    assert "green_but_issue_heavy" in types_of(detect(db, project))


def test_progress_inconsistency(db, project, factory):
    person = factory.person("Alice")
    factory.task("完了処理漏れ", owner_id=person.id, planned_start=day(-5), planned_end=day(10),
                 status="in_progress", progress=100, actual_start=day(-5))
    findings = [f for f in detect(db, project) if f.finding_type == "progress_inconsistency"]
    assert findings
    assert any("100" in e.detail for e in findings[0].evidence)


def test_overdue_status_unchanged(db, project, factory):
    person = factory.person("Alice")
    factory.task("API仕様確定", owner_id=person.id, planned_start=day(-20), planned_end=day(-4),
                 status="in_progress", progress=60, actual_start=day(-20))
    findings = [f for f in detect(db, project) if f.finding_type == "overdue_status_unchanged"]
    assert findings and findings[0].severity in ("high", "critical")


def test_milestone_buffer_insufficient(db, project, factory):
    person = factory.person("Alice")
    factory.milestone("内部リリース判定", due_date=day(7), status="pending")
    factory.task("必須タスク", owner_id=person.id, planned_start=day(-10), planned_end=day(-2),
                 status="in_progress", progress=30, actual_start=day(-10))
    findings = [f for f in detect(db, project) if f.finding_type == "milestone_buffer_insufficient"]
    assert findings and findings[0].severity == "critical"


def test_issue_governance_gap(db, project, factory):
    factory.issue("Owner未設定の課題", severity="medium", status="open", due_date=day(5))
    factory.issue("期限切れ課題", severity="high", status="open", due_date=day(-3))
    findings = [f for f in detect(db, project) if f.finding_type == "issue_governance_gap"]
    assert findings and findings[0].severity == "high"


def test_every_finding_carries_evidence_and_actions(db, project, factory):
    person = factory.person("田中", capacity_tasks=1)
    task = factory.task("遅延タスク", owner_id=person.id, planned_start=day(-15), planned_end=day(-5),
                        status="in_progress", progress=95, actual_start=day(-15))
    factory.issue("未解決課題", task_id=task.id, severity="critical", status="open")
    factory.milestone("リリース", due_date=day(5), status="pending")

    findings = detect(db, project)
    assert findings
    for finding in findings:
        assert finding.evidence, f"{finding.finding_type} has no evidence"
        assert finding.impact, f"{finding.finding_type} has no impact"
        assert finding.actions, f"{finding.finding_type} has no actions"
        assert all(e.detail for e in finding.evidence)


def test_findings_are_deduplicated_and_sorted_by_severity(db, project, factory):
    person = factory.person("Alice", capacity_tasks=1)
    for i in range(4):
        factory.task(f"遅延{i}", owner_id=person.id, planned_start=day(-20), planned_end=day(-12),
                     status="in_progress", progress=10, actual_start=day(-20))
    findings = detect(db, project)
    keys = [f.key() for f in findings]
    assert len(keys) == len(set(keys))
    ranks = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    severities = [ranks[f.severity] for f in findings]
    assert severities == sorted(severities, reverse=True)


def test_missing_actual_start_is_only_flagged_when_the_project_tracks_actuals(db, project, factory):
    """実績日の列が無いWBSでは、全Taskに『実績開始日なし』を出さない。"""
    person = factory.person("Alice")
    factory.task("実績日なしで進行中", owner_id=person.id, planned_start=day(-5), planned_end=day(10),
                 status="in_progress", progress=40)
    assert "progress_inconsistency" not in types_of(detect(db, project))

    # 1件でも実績開始日が入っていれば、入力漏れとして指摘する
    factory.task("実績日あり", owner_id=person.id, planned_start=day(-5), planned_end=day(10),
                 status="in_progress", progress=30, actual_start=day(-5))
    findings = [f for f in detect(db, project) if f.finding_type == "progress_inconsistency"]
    assert findings and any("実績開始日" in e.label for e in findings[0].evidence)
