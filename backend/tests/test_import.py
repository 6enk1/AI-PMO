"""Excel / CSV WBS import: header detection, column mapping and commit."""
from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import pytest
from openpyxl import Workbook

from app.importer.column_mapping import guess_mapping, normalize_header
from app.importer.value_parsers import (
    parse_date,
    parse_priority,
    parse_progress,
    parse_status,
    split_references,
    wbs_parent_code,
)

from .conftest import TODAY


def d(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).strftime("%Y/%m/%d")


def build_workbook(rows: list[list], title_rows: list[list] | None = None) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "WBS"
    for row in title_rows or []:
        sheet.append(row)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------- parsers
def test_parse_progress_variants():
    assert parse_progress("80%") == 80
    assert parse_progress(0.8) == 80
    assert parse_progress(80) == 80
    assert parse_progress("完了") == 100
    assert parse_progress("未着手") == 0
    assert parse_progress(1) == 100
    assert parse_progress("") is None
    assert parse_progress(150) == 100


def test_parse_date_variants():
    assert parse_date("2025/04/01") == date(2025, 4, 1)
    assert parse_date("2025-04-01") == date(2025, 4, 1)
    assert parse_date("2025年4月1日") == date(2025, 4, 1)
    assert parse_date("20250401") == date(2025, 4, 1)
    assert parse_date(45748) == date(2025, 4, 1)  # Excel serial
    assert parse_date(pd.Timestamp("2025-04-01")) == date(2025, 4, 1)
    assert parse_date("") is None
    assert parse_date("未定") is None


def test_parse_status_and_priority():
    assert parse_status("完了") == "done"
    assert parse_status("進行中") == "in_progress"
    assert parse_status("未着手") == "not_started"
    assert parse_status("保留") == "blocked"
    assert parse_status("In Progress") == "in_progress"
    assert parse_status("", progress=100) == "done"
    assert parse_status("", progress=30) == "in_progress"
    assert parse_status("", progress=0) == "not_started"

    assert parse_priority("高") == "high"
    assert parse_priority("High") == "high"
    assert parse_priority("最優先") == "critical"
    assert parse_priority("低") == "low"
    assert parse_priority("") == "medium"


def test_reference_and_wbs_helpers():
    assert split_references("T-001, T-002、T-003") == ["T-001", "T-002", "T-003"]
    assert split_references("なし") == []
    assert wbs_parent_code("1.2.3") == "1.2"
    assert wbs_parent_code("1") is None
    assert wbs_parent_code("T-001") is None


# --------------------------------------------------------------------------- mapping
@pytest.mark.parametrize(
    "header,expected_field",
    [
        ("担当", "owner"), ("担当者", "owner"), ("Owner", "owner"), ("Assignee", "owner"), ("PIC", "owner"),
        ("進捗", "progress"), ("進捗率", "progress"), ("Progress", "progress"), ("Progress %", "progress"),
        ("完了率", "progress"),
        ("タスク名", "title"), ("作業内容", "title"), ("Task Name", "title"),
        ("開始日", "planned_start"), ("開始予定日", "planned_start"), ("Start Date", "planned_start"),
        ("終了日", "planned_end"), ("完了予定日", "planned_end"), ("期限", "planned_end"), ("Due Date", "planned_end"),
        ("ステータス", "status"), ("Status", "status"), ("状態", "status"),
        ("優先度", "priority"), ("Priority", "priority"),
        ("依存関係", "dependency"), ("先行タスク", "dependency"), ("Predecessor", "dependency"),
        ("課題", "issue"), ("備考", "notes"), ("Remarks", "notes"),
    ],
)
def test_header_synonyms_are_recognised(header, expected_field):
    mapping, _ = guess_mapping([header, "ダミー列"])
    assert mapping[expected_field] == header


def test_planned_and_actual_dates_are_not_confused():
    mapping, _ = guess_mapping(["タスク名", "開始予定日", "終了予定日", "実績開始日", "実績終了日"])
    assert mapping["planned_start"] == "開始予定日"
    assert mapping["planned_end"] == "終了予定日"
    assert mapping["actual_start"] == "実績開始日"
    assert mapping["actual_end"] == "実績終了日"


def test_normalize_header_handles_width_and_symbols():
    assert normalize_header("進捗率（％）") == "進捗率%"
    assert normalize_header(" Task  Name ") == "taskname"


# --------------------------------------------------------------------------- API flow
HEADER = ["No", "タスク名", "担当者", "開始予定日", "完了予定日", "進捗率", "状態", "優先度", "先行タスク", "課題", "備考"]


def sample_rows():
    return [
        ["1", "要件定義", "佐藤", d(-30), d(-20), "100%", "完了", "高", "", "", ""],
        ["2", "API仕様確定", "佐藤", d(-20), d(-4), "60%", "進行中", "最優先", "要件定義", "顧客回答待ち", "難航中"],
        ["3", "バックエンド実装", "田中", d(-2), d(12), "0%", "未着手", "高", "API仕様確定", "", ""],
        ["4", "テスト", "", d(15), d(30), "", "", "", "バックエンド実装", "", ""],
    ]


def test_analyze_detects_header_and_mapping(client):
    content = build_workbook([HEADER] + sample_rows(), title_rows=[["社内システム開発 WBS"], []])
    response = client.post(
        "/api/imports/analyze",
        files={"file": ("wbs.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["header_row"] == 2  # the two title rows above the header are skipped
    assert body["mapping"]["title"] == "タスク名"
    assert body["mapping"]["owner"] == "担当者"
    assert body["mapping"]["planned_end"] == "完了予定日"
    assert body["mapping"]["progress"] == "進捗率"
    assert body["mapping"]["dependency"] == "先行タスク"
    assert len(body["preview"]) == 4
    assert body["preview"][1]["title"] == "API仕様確定"
    assert body["preview"][1]["progress"] == 60
    assert body["preview"][1]["status"] == "in_progress"
    assert body["preview"][1]["priority"] == "critical"
    assert body["preview"][0]["status"] == "done"
    assert body["sheets"][0]["name"] == "WBS"


def test_commit_creates_project_tasks_people_and_dependencies(client):
    content = build_workbook([HEADER] + sample_rows())
    analyzed = client.post(
        "/api/imports/analyze", files={"file": ("wbs.xlsx", content, "application/octet-stream")}
    ).json()

    committed = client.post(
        "/api/imports/commit",
        json={
            "token": analyzed["token"],
            "mapping": analyzed["mapping"],
            "new_project_name": "インポートPJ",
        },
    )
    assert committed.status_code == 200, committed.text
    result = committed.json()
    assert result["created_tasks"] == 4
    assert result["created_people"] == 2  # 佐藤 / 田中（空欄はスキップ）
    assert result["created_issues"] == 1
    assert result["created_dependencies"] == 3

    project_id = result["project_id"]
    tasks = client.get(f"/api/projects/{project_id}/tasks").json()
    by_title = {t["title"]: t for t in tasks}
    assert by_title["要件定義"]["status"] == "done"
    assert by_title["要件定義"]["progress"] == 100
    assert by_title["API仕様確定"]["owner_name"] == "佐藤"
    assert by_title["API仕様確定"]["is_overdue"] is True
    assert by_title["バックエンド実装"]["predecessor_task_ids"] == [by_title["API仕様確定"]["id"]]
    # A row with no status and no progress falls back to not_started.
    assert by_title["テスト"]["status"] == "not_started"

    issues = client.get(f"/api/projects/{project_id}/issues").json()
    assert issues[0]["title"] == "顧客回答待ち"
    assert issues[0]["task_id"] == by_title["API仕様確定"]["id"]

    # The project window is derived from the imported plan.
    project = client.get(f"/api/projects/{project_id}").json()
    assert project["start_date"] is not None and project["end_date"] is not None


def test_commit_into_existing_project(client, project):
    content = build_workbook([HEADER] + sample_rows())
    analyzed = client.post(
        "/api/imports/analyze", files={"file": ("wbs.xlsx", content, "application/octet-stream")}
    ).json()
    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "project_id": project.id},
    ).json()
    assert result["project_id"] == project.id
    assert len(client.get(f"/api/projects/{project.id}/tasks").json()) == 4


def test_csv_import_with_english_headers(client):
    csv = (
        "Task Name,Assignee,Start Date,Due Date,Progress,Status,Priority\n"
        f"Design,Alice,{d(-10)},{d(-2)},0.5,In Progress,High\n"
        f"Build,Bob,{d(-1)},{d(10)},0,Not Started,Medium\n"
    ).encode("utf-8")
    analyzed = client.post(
        "/api/imports/analyze", files={"file": ("plan.csv", csv, "text/csv")}
    ).json()
    assert analyzed["mapping"]["title"] == "Task Name"
    assert analyzed["mapping"]["owner"] == "Assignee"
    assert analyzed["preview"][0]["progress"] == 50

    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "new_project_name": "CSV PJ"},
    ).json()
    assert result["created_tasks"] == 2
    tasks = client.get(f"/api/projects/{result['project_id']}/tasks").json()
    assert {t["owner_name"] for t in tasks} == {"Alice", "Bob"}


def test_user_can_override_the_mapping(client):
    header = ["項目", "担当", "いつまで", "どれくらい"]
    rows = [["設計書作成", "山田", d(5), "30%"]]
    content = build_workbook([header] + rows)
    analyzed = client.post(
        "/api/imports/analyze", files={"file": ("odd.xlsx", content, "application/octet-stream")}
    ).json()

    mapping = dict(analyzed["mapping"])
    mapping["title"] = "項目"
    mapping["owner"] = "担当"
    mapping["planned_end"] = "いつまで"
    mapping["progress"] = "どれくらい"

    preview = client.get(
        f"/api/imports/{analyzed['token']}/preview", params={"header_row": 0}
    ).json()
    assert preview["columns"] == header

    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": mapping, "new_project_name": "手動マッピングPJ"},
    ).json()
    assert result["created_tasks"] == 1
    task = client.get(f"/api/projects/{result['project_id']}/tasks").json()[0]
    assert task["title"] == "設計書作成"
    assert task["owner_name"] == "山田"
    assert task["progress"] == 30
    assert task["planned_end"] is not None


def test_wbs_numbering_builds_parent_child(client):
    header = ["WBS No", "タスク名", "担当者", "開始日", "終了日", "進捗"]
    rows = [
        ["1", "フェーズ1", "佐藤", d(-10), d(10), "50%"],
        ["1.1", "要件定義", "佐藤", d(-10), d(-5), "100%"],
        ["1.2", "基本設計", "田中", d(-4), d(10), "20%"],
    ]
    content = build_workbook([header] + rows)
    analyzed = client.post(
        "/api/imports/analyze", files={"file": ("wbs2.xlsx", content, "application/octet-stream")}
    ).json()
    assert analyzed["mapping"]["code"] == "WBS No"

    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "new_project_name": "階層PJ"},
    ).json()
    tasks = {t["code"]: t for t in client.get(f"/api/projects/{result['project_id']}/tasks").json()}
    assert tasks["1.1"]["parent_task_id"] == tasks["1"]["id"]
    assert tasks["1.2"]["parent_task_id"] == tasks["1"]["id"]
    assert sorted(tasks["1"]["child_task_ids"]) == sorted([tasks["1.1"]["id"], tasks["1.2"]["id"]])


def test_rows_without_a_title_are_skipped(client):
    content = build_workbook([HEADER, ["", "", "", "", "", "", "", "", "", "", ""], sample_rows()[0]])
    analyzed = client.post(
        "/api/imports/analyze", files={"file": ("sparse.xlsx", content, "application/octet-stream")}
    ).json()
    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "new_project_name": "スパースPJ"},
    ).json()
    assert result["created_tasks"] == 1


def test_unsupported_file_type_is_rejected(client):
    response = client.post(
        "/api/imports/analyze", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 400


def test_missing_token_returns_404(client):
    response = client.post(
        "/api/imports/commit", json={"token": "does-not-exist", "mapping": {"title": "A"}}
    )
    assert response.status_code == 404


def test_analysis_runs_on_imported_data(client):
    """The imported WBS must immediately produce AI PMO findings."""
    content = build_workbook([HEADER] + sample_rows())
    analyzed = client.post(
        "/api/imports/analyze", files={"file": ("wbs.xlsx", content, "application/octet-stream")}
    ).json()
    result = client.post(
        "/api/imports/commit",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"], "new_project_name": "分析PJ"},
    ).json()

    dashboard = client.get(f"/api/projects/{result['project_id']}/dashboard").json()
    assert dashboard["overdue_tasks"] >= 1
    assert dashboard["focus_items"]

    ai = client.get(f"/api/projects/{result['project_id']}/ai-pmo").json()
    assert ai["hidden_issues"]
    assert ai["delay_actions"]
