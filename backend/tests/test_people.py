"""Person management and the derived workload figures."""
from __future__ import annotations

from .conftest import day


def test_person_crud_and_workload(client, project, factory):
    created = client.post(
        f"/api/projects/{project.id}/people",
        json={"name": "田中 美咲", "role": "開発リード", "capacity_tasks": 3},
    )
    assert created.status_code == 201
    person = created.json()

    duplicate = client.post(
        f"/api/projects/{project.id}/people", json={"name": "田中 美咲"}
    )
    assert duplicate.status_code == 409

    factory.task("遅延1", owner_id=person["id"], planned_end=day(-4), status="in_progress", progress=20, priority="critical")
    factory.task("遅延2", owner_id=person["id"], planned_end=day(-1), status="in_progress", progress=50, priority="high")
    factory.task("今週期限", owner_id=person["id"], planned_end=day(3), status="not_started", priority="high")
    factory.task("完了", owner_id=person["id"], planned_end=day(-10), status="done", progress=100)
    factory.issue("担当課題", owner_id=person["id"], severity="high", status="open")

    workload = client.get(f"/api/projects/{project.id}/people").json()
    assert len(workload) == 1
    row = workload[0]
    assert row["assigned_task_count"] == 4
    assert row["open_task_count"] == 3
    assert row["overdue_task_count"] == 2
    assert row["critical_task_count"] == 3
    assert row["due_this_week_count"] == 1
    assert row["open_issue_count"] == 1
    assert row["load_ratio"] == 1.0
    assert row["load_level"] == "overloaded"

    updated = client.patch(f"/api/people/{person['id']}", json={"role": "PM"}).json()
    assert updated["role"] == "PM"

    assert client.delete(f"/api/people/{person['id']}").status_code == 204
    assert client.get(f"/api/projects/{project.id}/people").json() == []
