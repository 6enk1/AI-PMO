"""Task CRUD, filtering and sorting through the API."""
from __future__ import annotations

from .conftest import day


def test_create_read_update_delete_task(client, project):
    created = client.post(
        f"/api/projects/{project.id}/tasks",
        json={
            "title": "要件定義",
            "planned_start": str(day(-10)),
            "planned_end": str(day(-1)),
            "progress": 40,
            "status": "in_progress",
            "priority": "high",
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["code"] == "T-001"
    assert task["title"] == "要件定義"

    fetched = client.get(f"/api/tasks/{task['id']}").json()
    assert fetched["id"] == task["id"]
    assert fetched["risk_score"] > 0  # overdue task must carry risk

    updated = client.patch(
        f"/api/tasks/{task['id']}", json={"title": "要件定義（改訂）", "progress": 70}
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "要件定義（改訂）"
    assert updated.json()["progress"] == 70

    # Closing a task normalises progress and stamps the actual end date.
    done = client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}).json()
    assert done["progress"] == 100
    assert done["actual_end"] is not None
    assert done["is_overdue"] is False

    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404


def test_task_validation_and_owner_check(client, project):
    bad = client.post(f"/api/projects/{project.id}/tasks", json={"title": ""})
    assert bad.status_code == 422

    missing_owner = client.post(
        f"/api/projects/{project.id}/tasks", json={"title": "X", "owner_id": 9999}
    )
    assert missing_owner.status_code == 400

    # progress is clamped into 0-100
    task = client.post(
        f"/api/projects/{project.id}/tasks", json={"title": "Y", "progress": 250}
    ).json()
    assert task["progress"] == 100


def test_filter_and_sort_tasks(client, project, factory):
    alice = factory.person("Alice")
    factory.task("遅延タスク", owner_id=alice.id, planned_end=day(-5), status="in_progress", progress=10, priority="high")
    factory.task("将来タスク", planned_end=day(20), status="not_started", priority="low")
    factory.task("完了タスク", owner_id=alice.id, planned_end=day(-2), status="done", progress=100)

    overdue = client.get(f"/api/projects/{project.id}/tasks", params={"overdue": True}).json()
    assert [t["title"] for t in overdue] == ["遅延タスク"]

    by_owner = client.get(f"/api/projects/{project.id}/tasks", params={"owner_id": alice.id}).json()
    assert len(by_owner) == 2

    unassigned = client.get(f"/api/projects/{project.id}/tasks", params={"unassigned": True}).json()
    assert [t["title"] for t in unassigned] == ["将来タスク"]

    by_status = client.get(
        f"/api/projects/{project.id}/tasks", params={"status": ["not_started", "done"]}
    ).json()
    assert {t["title"] for t in by_status} == {"将来タスク", "完了タスク"}

    searched = client.get(f"/api/projects/{project.id}/tasks", params={"q": "将来"}).json()
    assert len(searched) == 1

    sorted_desc = client.get(
        f"/api/projects/{project.id}/tasks", params={"sort": "risk_score", "order": "desc"}
    ).json()
    assert sorted_desc[0]["title"] == "遅延タスク"

    by_date = client.get(
        f"/api/projects/{project.id}/tasks", params={"sort": "planned_end", "order": "asc"}
    ).json()
    assert [t["title"] for t in by_date][0] == "遅延タスク"


def test_dependencies_round_trip(client, project, factory):
    first = factory.task("設計", planned_end=day(2))
    second = factory.task("実装", planned_start=day(3), planned_end=day(10))

    linked = client.patch(
        f"/api/tasks/{second.id}", json={"predecessor_task_ids": [first.id]}
    ).json()
    assert linked["predecessor_task_ids"] == [first.id]

    first_read = client.get(f"/api/tasks/{first.id}").json()
    assert first_read["successor_task_ids"] == [second.id]

    dependencies = client.get(f"/api/projects/{project.id}/dependencies").json()
    assert len(dependencies) == 1

    cleared = client.patch(f"/api/tasks/{second.id}", json={"predecessor_task_ids": []}).json()
    assert cleared["predecessor_task_ids"] == []


def test_parent_child_relationship(client, project, factory):
    parent = factory.task("フェーズ1")
    child = client.post(
        f"/api/projects/{project.id}/tasks",
        json={"title": "子タスク", "parent_task_id": parent.id},
    ).json()
    assert child["parent_task_id"] == parent.id

    parent_read = client.get(f"/api/tasks/{parent.id}").json()
    assert parent_read["child_task_ids"] == [child["id"]]

    self_parent = client.patch(f"/api/tasks/{parent.id}", json={"parent_task_id": parent.id})
    assert self_parent.status_code == 400


def test_category_fields_expose_the_parent_chain(client, project, factory):
    """親タスクを大カテゴリとして各画面に出せるだけの情報が返ること。"""
    root = factory.task("ソフトウェア開発", code="C-1")
    middle = factory.task("フェーズ1: 要件・設計", code="C-1-1", parent_task_id=root.id)
    leaf = factory.task("要件定義", code="T-001", parent_task_id=middle.id, planned_end=day(10))

    tasks = {t["id"]: t for t in client.get(f"/api/projects/{project.id}/tasks").json()}

    leaf_read = tasks[leaf.id]
    assert leaf_read["category"] == "ソフトウェア開発"
    assert leaf_read["parent_task_title"] == "フェーズ1: 要件・設計"
    assert leaf_read["path_titles"] == ["ソフトウェア開発", "フェーズ1: 要件・設計"]
    assert leaf_read["depth"] == 2
    assert leaf_read["child_count"] == 0

    root_read = tasks[root.id]
    assert root_read["category"] is None
    assert root_read["path_titles"] == []
    assert root_read["child_count"] == 1


def test_filter_by_category_returns_every_descendant(client, project, factory):
    root = factory.task("ソフトウェア開発")
    phase = factory.task("フェーズ1", parent_task_id=root.id)
    leaf = factory.task("要件定義", parent_task_id=phase.id)
    other = factory.task("インフラ構築")

    inside = client.get(
        f"/api/projects/{project.id}/tasks", params={"category_task_id": root.id}
    ).json()
    assert {t["title"] for t in inside} == {"ソフトウェア開発", "フェーズ1", "要件定義"}
    assert other.title not in {t["title"] for t in inside}

    # 直下だけを見たいときは parent_task_id
    direct = client.get(
        f"/api/projects/{project.id}/tasks", params={"parent_task_id": root.id}
    ).json()
    assert [t["title"] for t in direct] == ["フェーズ1"]

    leaves = client.get(f"/api/projects/{project.id}/tasks", params={"leaves_only": True}).json()
    assert {t["title"] for t in leaves} == {"要件定義", "インフラ構築"}
    assert leaf.id in {t["id"] for t in leaves}


def test_category_survives_a_broken_parent_link(client, project, factory):
    """親子ループが混入してもカテゴリ解決が無限ループしないこと。"""
    first = factory.task("A")
    second = factory.task("B", parent_task_id=first.id)
    first.parent_task_id = second.id
    client.patch(f"/api/tasks/{first.id}", json={"code": "A-1"})

    tasks = client.get(f"/api/projects/{project.id}/tasks").json()
    assert len(tasks) == 2
    assert all("category" in task for task in tasks)
