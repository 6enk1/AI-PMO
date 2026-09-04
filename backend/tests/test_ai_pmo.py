"""Command Center dashboard and the AI PMO endpoints."""
from __future__ import annotations

from app.analysis.delay_actions import build_delay_actions
from app.analysis.snapshot import build_snapshot

from .conftest import TODAY, day


def build_delayed_project(factory):
    """A small but realistic project with several distinct problems."""
    sato = factory.person("佐藤", role="PM", capacity_tasks=6)
    tanaka = factory.person("田中", role="開発リード", capacity_tasks=2)

    done = factory.task("要件定義", owner_id=sato.id, planned_start=day(-40), planned_end=day(-30),
                        actual_start=day(-40), actual_end=day(-29), status="done", progress=100)
    spec = factory.task("API仕様確定", owner_id=sato.id, planned_start=day(-20), planned_end=day(-4),
                        actual_start=day(-20), status="in_progress", progress=60, priority="critical",
                        notes="顧客からの回答待ち")
    backend = factory.task("バックエンド実装", owner_id=tanaka.id, planned_start=day(-1), planned_end=day(12),
                           status="not_started", progress=0, priority="high")
    frontend = factory.task("フロントエンド実装", owner_id=tanaka.id, planned_start=day(0), planned_end=day(14),
                            status="in_progress", progress=10, priority="high")
    factory.task("テスト計画", planned_start=day(2), planned_end=day(9), status="not_started")
    factory.dependency(done, spec)
    factory.dependency(spec, backend)
    factory.dependency(spec, frontend)
    factory.issue("顧客からのAPI仕様回答待ち", task_id=spec.id, severity="high", status="open",
                  owner_id=sato.id, due_date=day(-2))
    factory.issue("性能要件が未確定", task_id=frontend.id, severity="medium", status="open")
    factory.milestone("内部リリース判定", due_date=day(10), status="pending")
    return {"spec": spec, "backend": backend, "frontend": frontend}


def test_dashboard_returns_command_center_metrics(client, project, factory):
    build_delayed_project(factory)
    body = client.get(f"/api/projects/{project.id}/dashboard", params={"as_of": str(TODAY)}).json()

    assert 0 <= body["health_score"] <= 100
    assert body["health_label"] in ("良好", "注意", "要対応", "危険")
    assert body["health_breakdown"]  # the score is always explained
    assert body["total_tasks"] == 5
    assert body["overdue_tasks"] == 1
    assert body["open_tasks"] == 4
    assert body["done_tasks"] == 1
    assert body["open_issue_count"] == 2
    assert body["critical_issue_count"] == 1
    assert body["unassigned_tasks"] == 1
    assert body["hidden_issue_count"] > 0
    assert body["next_milestone"]["title"] == "内部リリース判定"
    assert body["next_milestone"]["days_remaining"] == 10

    focus = body["focus_items"]
    assert 1 <= len(focus) <= 10
    assert all(item["title"] and item["detail"] for item in focus)
    assert any("API仕様確定" in item["title"] for item in focus)


def test_healthy_project_scores_high(client, project, factory):
    person = factory.person("Alice", capacity_tasks=8)
    factory.task("順調1", owner_id=person.id, planned_start=day(1), planned_end=day(20), status="not_started")
    factory.task("順調2", owner_id=person.id, planned_start=day(2), planned_end=day(25), status="not_started")
    body = client.get(f"/api/projects/{project.id}/dashboard").json()
    assert body["health_score"] >= 80
    assert body["health_label"] == "良好"


def test_ai_pmo_endpoint_returns_three_sections(client, project, factory):
    build_delayed_project(factory)
    body = client.get(f"/api/projects/{project.id}/ai-pmo", params={"as_of": str(TODAY)}).json()

    assert body["llm_used"] is False  # no API key in tests -> rule based fallback
    assert body["llm_note"]
    assert body["hidden_issues"] and body["delay_risks"] and body["delay_actions"]
    assert body["recommended_actions"]

    for finding in body["hidden_issues"] + body["delay_actions"]:
        assert finding["evidence"], f"{finding['finding_type']} must cite evidence"
        assert finding["explanation"]
        assert finding["reasoning_summary"]
        assert finding["impact"]
        assert finding["recommended_actions"]
        assert finding["recommended_action"]
        assert finding["recommended_action_why"]
        assert 0 <= finding["confidence"] <= 1

    for risk in body["delay_risks"]:
        assert risk["factors"], "risk score must be decomposed into factors"
        assert risk["reasons"]
        assert risk["impact"]
        assert 0 <= risk["risk_score"] <= 100


def test_delay_action_identifies_customer_wait(db, project, factory):
    tasks = build_delayed_project(factory)
    snapshot = build_snapshot(db, project.id, today=TODAY)
    findings = {f.task_id: f for f in build_delay_actions(snapshot)}

    spec = findings[tasks["spec"].id]
    assert spec.cause_category == "顧客回答待ち"
    assert spec.recommended_action
    assert spec.recommended_action_why
    assert any("後続" in e.detail or "後続" in e.label for e in spec.evidence)
    assert len(spec.actions) >= 2


def test_delay_action_identifies_dependency_delay(db, project, factory):
    tasks = build_delayed_project(factory)
    snapshot = build_snapshot(db, project.id, today=TODAY)
    findings = {f.task_id: f for f in build_delay_actions(snapshot, risk_threshold=0)}

    backend = findings[tasks["backend"].id]
    assert backend.cause_category in ("依存Task遅延", "人員不足")
    assert backend.evidence
    assert backend.actions


def test_risks_endpoint_is_sorted_and_filtered(client, project, factory):
    build_delayed_project(factory)
    risks = client.get(
        f"/api/projects/{project.id}/risks", params={"threshold": 30, "as_of": str(TODAY)}
    ).json()
    assert risks
    scores = [r["risk_score"] for r in risks]
    assert scores == sorted(scores, reverse=True)
    assert all(score >= 30 for score in scores)

    strict = client.get(f"/api/projects/{project.id}/risks", params={"threshold": 95}).json()
    assert len(strict) <= len(risks)


def test_hidden_issue_endpoint(client, project, factory):
    build_delayed_project(factory)
    findings = client.get(
        f"/api/projects/{project.id}/hidden-issues", params={"as_of": str(TODAY)}
    ).json()
    assert findings
    assert all(f["category"] == "hidden_issue" and f["evidence"] for f in findings)


def test_findings_are_persisted_for_later_review(client, db, project, factory):
    from app.models import AIRiskFinding

    build_delayed_project(factory)
    client.get(f"/api/projects/{project.id}/ai-pmo", params={"as_of": str(TODAY)})
    stored = db.query(AIRiskFinding).filter(AIRiskFinding.project_id == project.id).all()
    assert stored
    assert all(row.evidence and row.title for row in stored)

    # Re-running replaces the previous run rather than duplicating it.
    before = len(stored)
    client.get(f"/api/projects/{project.id}/ai-pmo", params={"as_of": str(TODAY)})
    after = db.query(AIRiskFinding).filter(AIRiskFinding.project_id == project.id).count()
    assert after == before


def test_llm_status_reports_fallback_mode(client, project):
    body = client.get(f"/api/projects/{project.id}/llm-status").json()
    assert body["llm_available"] is False
    assert "ルールベース" in body["note"]


def test_empty_project_does_not_break_analysis(client, project):
    dashboard = client.get(f"/api/projects/{project.id}/dashboard").json()
    assert dashboard["total_tasks"] == 0
    assert dashboard["health_score"] == 100
    ai = client.get(f"/api/projects/{project.id}/ai-pmo").json()
    assert ai["hidden_issues"] == [] and ai["delay_risks"] == []


def test_findings_and_risks_carry_the_task_category(client, project, factory):
    tasks = build_delayed_project(factory)
    phase = factory.task("フェーズ1: 要件・設計")
    client.patch(f"/api/tasks/{tasks['spec'].id}", json={"parent_task_id": phase.id})

    body = client.get(f"/api/projects/{project.id}/ai-pmo", params={"as_of": str(TODAY)}).json()
    spec_findings = [
        f for f in body["hidden_issues"] + body["delay_actions"] if f["task_id"] == tasks["spec"].id
    ]
    assert spec_findings
    assert all(f["task_category"] == "フェーズ1: 要件・設計" for f in spec_findings)

    spec_risk = [r for r in body["delay_risks"] if r["task_id"] == tasks["spec"].id]
    assert spec_risk and spec_risk[0]["task_category"] == "フェーズ1: 要件・設計"


def test_issue_read_carries_the_related_task_category(client, project, factory):
    phase = factory.task("フェーズ2: 開発")
    task = factory.task("バックエンド実装", parent_task_id=phase.id)
    factory.issue("性能要件が未確定", task_id=task.id, severity="high", status="open")

    issue = client.get(f"/api/projects/{project.id}/issues").json()[0]
    assert issue["task_title"] == "バックエンド実装"
    assert issue["task_category"] == "フェーズ2: 開発"
