"""Project CRUD and milestones."""
from __future__ import annotations

from .conftest import day


def test_project_crud(client):
    created = client.post(
        "/api/projects",
        json={"name": "新規PJ", "description": "説明", "start_date": str(day(0)), "end_date": str(day(90))},
    )
    assert created.status_code == 201
    project = created.json()

    listed = client.get("/api/projects").json()
    assert any(p["id"] == project["id"] for p in listed)
    assert listed[0]["task_count"] == 0

    updated = client.patch(f"/api/projects/{project['id']}", json={"name": "改名PJ"}).json()
    assert updated["name"] == "改名PJ"

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_deleting_a_project_removes_its_tasks(client, project, factory):
    factory.task("タスク", planned_end=day(5))
    assert client.delete(f"/api/projects/{project.id}").status_code == 204
    assert client.get(f"/api/projects/{project.id}/tasks").status_code == 404


def test_milestone_crud(client, project, factory):
    created = client.post(
        f"/api/projects/{project.id}/milestones",
        json={"title": "内部リリース", "due_date": str(day(10))},
    )
    assert created.status_code == 201
    milestone = created.json()
    assert milestone["days_remaining"] == 10

    factory.task("遅延タスク", planned_end=day(-2), status="in_progress", progress=10)
    listed = client.get(f"/api/projects/{project.id}/milestones").json()
    assert listed[0]["at_risk"] is True

    updated = client.patch(
        f"/api/projects/{project.id}/milestones/{milestone['id']}", json={"status": "achieved"}
    ).json()
    assert updated["status"] == "achieved"

    assert client.delete(f"/api/projects/{project.id}/milestones/{milestone['id']}").status_code == 204


def test_health_endpoint(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
