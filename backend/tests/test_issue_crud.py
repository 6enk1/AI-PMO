"""Issue CRUD - Issues are a first class object, separate from Tasks."""
from __future__ import annotations

from .conftest import day


def test_issue_lifecycle(client, project, factory):
    owner = factory.person("佐藤")
    task = factory.task("API仕様確定", planned_end=day(-3), status="in_progress", progress=50)

    created = client.post(
        f"/api/projects/{project.id}/issues",
        json={
            "title": "顧客からの回答待ち",
            "description": "認証方式の確認",
            "severity": "high",
            "owner_id": owner.id,
            "task_id": task.id,
            "raised_on": str(day(-5)),
            "due_date": str(day(-1)),
            "status": "open",
        },
    )
    assert created.status_code == 201, created.text
    issue = created.json()
    assert issue["code"] == "I-001"
    assert issue["owner_name"] == "佐藤"
    assert issue["task_title"] == "API仕様確定"
    assert issue["is_overdue"] is True

    updated = client.patch(
        f"/api/issues/{issue['id']}",
        json={"status": "resolved", "resolution": "顧客回答受領"},
    ).json()
    assert updated["status"] == "resolved"
    assert updated["is_overdue"] is False  # resolved issues are no longer overdue

    assert client.delete(f"/api/issues/{issue['id']}").status_code == 204
    assert client.get(f"/api/issues/{issue['id']}").status_code == 404


def test_issue_filters(client, project, factory):
    owner = factory.person("田中")
    task = factory.task("移行設計")
    factory.issue("重大課題", severity="critical", status="open", owner_id=owner.id, task_id=task.id)
    factory.issue("軽微課題", severity="low", status="open")
    factory.issue("解決済み課題", severity="high", status="resolved")

    open_only = client.get(f"/api/projects/{project.id}/issues", params={"open_only": True}).json()
    assert {i["title"] for i in open_only} == {"重大課題", "軽微課題"}

    critical = client.get(
        f"/api/projects/{project.id}/issues", params={"severity": ["critical"]}
    ).json()
    assert [i["title"] for i in critical] == ["重大課題"]

    by_owner = client.get(f"/api/projects/{project.id}/issues", params={"owner_id": owner.id}).json()
    assert [i["title"] for i in by_owner] == ["重大課題"]

    by_task = client.get(f"/api/projects/{project.id}/issues", params={"task_id": task.id}).json()
    assert [i["title"] for i in by_task] == ["重大課題"]

    ordered = client.get(
        f"/api/projects/{project.id}/issues", params={"sort": "severity", "order": "desc"}
    ).json()
    assert ordered[0]["title"] == "重大課題"


def test_issues_are_independent_from_tasks(client, project, factory):
    """Deleting a Task must not delete the Issue that referenced it."""
    task = factory.task("設計")
    issue = client.post(
        f"/api/projects/{project.id}/issues",
        json={"title": "設計上の懸念", "task_id": task.id, "severity": "medium"},
    ).json()

    assert client.delete(f"/api/tasks/{task.id}").status_code == 204
    remaining = client.get(f"/api/issues/{issue['id']}").json()
    assert remaining["task_id"] is None
    assert remaining["title"] == "設計上の懸念"


def test_project_level_issue_without_task(client, project):
    issue = client.post(
        f"/api/projects/{project.id}/issues",
        json={"title": "体制上の課題", "severity": "medium"},
    ).json()
    assert issue["task_id"] is None
    assert issue["status"] == "open"
