"""同期インポート: 既存Taskと突き合わせて更新する取り込み。"""
from __future__ import annotations

import io
from datetime import timedelta

from openpyxl import Workbook

from .conftest import TODAY

HEADER = ["No", "タスク名", "担当者", "開始予定日", "完了予定日", "進捗率", "状態", "先行タスク", "課題"]


def d(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).strftime("%Y/%m/%d")


def workbook(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "WBS"
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def upload(client, rows: list[list]) -> dict:
    content = workbook(rows)
    return client.post(
        "/api/imports/analyze", files={"file": ("wbs.xlsx", content, "application/octet-stream")}
    ).json()


BASE_ROWS = [
    ["1", "要件定義", "佐藤", d(-20), d(-10), "100%", "完了", "", ""],
    ["2", "基本設計", "佐藤", d(-9), d(-1), "60%", "進行中", "要件定義", "レビュー待ち"],
    ["3", "実装", "田中", d(0), d(14), "0%", "未着手", "基本設計", ""],
]


def seed_project(client) -> int:
    analyzed = upload(client, BASE_ROWS)
    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "new_project_name": "同期PJ"},
    ).json()
    assert result["created_tasks"] == 3
    assert result["match_by"] == "none"  # 新規PJは突き合わせ相手がいない
    return result["project_id"]


def test_reimporting_the_same_file_changes_nothing(client):
    project_id = seed_project(client)
    analyzed = upload(client, BASE_ROWS)

    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "project_id": project_id},
    ).json()

    assert result["match_by"] == "auto"
    assert result["created_tasks"] == 0
    assert result["updated_tasks"] == 0
    assert result["unchanged_tasks"] == 3
    assert len(client.get(f"/api/projects/{project_id}/tasks").json()) == 3


def test_updated_rows_are_applied_and_new_rows_added(client):
    project_id = seed_project(client)
    updated_rows = [
        BASE_ROWS[0],
        ["2", "基本設計", "佐藤", d(-9), d(3), "80%", "進行中", "要件定義", "レビュー待ち"],
        BASE_ROWS[2],
        ["4", "総合テスト", "高橋", d(15), d(30), "0%", "未着手", "実装", ""],
    ]
    analyzed = upload(client, updated_rows)

    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "project_id": project_id},
    ).json()

    assert result["updated_tasks"] == 1
    assert result["created_tasks"] == 1
    assert result["unchanged_tasks"] == 2

    tasks = {t["title"]: t for t in client.get(f"/api/projects/{project_id}/tasks").json()}
    assert len(tasks) == 4
    assert tasks["基本設計"]["progress"] == 80
    assert tasks["基本設計"]["planned_end"] == str(TODAY + timedelta(days=3))
    assert tasks["総合テスト"]["owner_name"] == "高橋"
    # 既存Taskを指す依存も解決される
    assert tasks["総合テスト"]["predecessor_task_ids"] == [tasks["実装"]["id"]]


def test_empty_cells_do_not_wipe_existing_values(client):
    project_id = seed_project(client)
    # 担当者・日付・課題が空のまま、進捗だけ更新したファイル
    analyzed = upload(client, [["2", "基本設計", "", "", "", "75%", "", "", ""]])

    client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "project_id": project_id},
    )

    tasks = {t["title"]: t for t in client.get(f"/api/projects/{project_id}/tasks").json()}
    task = tasks["基本設計"]
    assert task["progress"] == 75
    assert task["owner_name"] == "佐藤"  # 空欄で消えない
    assert task["planned_start"] == str(TODAY + timedelta(days=-9))
    assert task["planned_end"] == str(TODAY + timedelta(days=-1))
    assert task["status"] == "in_progress"


def test_matching_falls_back_to_the_task_name(client):
    project_id = seed_project(client)
    # Task ID列を含まないファイル（タスク名で突き合わせる）
    book = Workbook()
    sheet = book.active
    sheet.append(["タスク名", "進捗率"])
    sheet.append(["基本設計", "90%"])
    buffer = io.BytesIO()
    book.save(buffer)
    analyzed = client.post(
        "/api/imports/analyze",
        files={"file": ("names.xlsx", buffer.getvalue(), "application/octet-stream")},
    ).json()

    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "project_id": project_id},
    ).json()

    assert result["updated_tasks"] == 1
    assert result["created_tasks"] == 0
    tasks = {t["title"]: t for t in client.get(f"/api/projects/{project_id}/tasks").json()}
    assert tasks["基本設計"]["progress"] == 90


def test_match_by_none_always_appends(client):
    project_id = seed_project(client)
    analyzed = upload(client, BASE_ROWS)

    result = client.post(
        "/api/imports/commit",
        json={
            "token": analyzed["token"],
            "mapping": analyzed["mapping"],
            "project_id": project_id,
            "match_by": "none",
        },
    ).json()

    assert result["created_tasks"] == 3
    assert result["updated_tasks"] == 0
    assert len(client.get(f"/api/projects/{project_id}/tasks").json()) == 6


def test_issues_are_not_duplicated_on_reimport(client):
    project_id = seed_project(client)
    assert len(client.get(f"/api/projects/{project_id}/issues").json()) == 1

    analyzed = upload(client, BASE_ROWS)
    client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "project_id": project_id},
    )
    assert len(client.get(f"/api/projects/{project_id}/issues").json()) == 1


# --------------------------------------------------------------------------- plan
def test_plan_reports_the_diff_without_writing(client):
    project_id = seed_project(client)
    rows = [
        BASE_ROWS[0],
        ["2", "基本設計", "田中", d(-9), d(3), "80%", "進行中", "要件定義", ""],
        ["9", "受入テスト", "高橋", d(20), d(30), "0%", "未着手", "", ""],
    ]
    analyzed = upload(client, rows)
    body = {"token": analyzed["token"], "mapping": analyzed["mapping"], "project_id": project_id}

    plan = client.post("/api/imports/plan", json=body).json()

    assert plan["match_by"] == "auto"
    assert plan["update_count"] == 1
    assert plan["create_count"] == 1
    assert plan["unchanged_count"] == 1

    by_title = {row["title"]: row for row in plan["rows"]}
    assert by_title["受入テスト"]["action"] == "create"
    assert by_title["要件定義"]["action"] == "unchanged"

    update = by_title["基本設計"]
    assert update["action"] == "update"
    assert update["matched_by"] == "code"
    fields = {change["field"]: change for change in update["changes"]}
    assert fields["progress"]["before"] == "60.0" and fields["progress"]["after"] == "80.0"
    assert fields["owner"]["before"] == "佐藤" and fields["owner"]["after"] == "田中"
    assert "planned_end" in fields

    # ファイルに無い既存Taskも知らせる
    assert [m["title"] for m in plan["missing_in_file"]] == ["実装"]

    # plan は書き込まない
    tasks = {t["title"]: t for t in client.get(f"/api/projects/{project_id}/tasks").json()}
    assert tasks["基本設計"]["progress"] == 60
    assert len(tasks) == 3


def test_plan_for_a_new_project_is_all_creates(client):
    analyzed = upload(client, BASE_ROWS)
    plan = client.post(
        "/api/imports/plan",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "new_project_name": "新PJ"},
    ).json()

    assert plan["match_by"] == "none"
    assert plan["create_count"] == 3
    assert plan["update_count"] == 0
    assert plan["missing_in_file"] == []
