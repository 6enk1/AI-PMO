"""アップロードされた中身が WBS か課題リストかの自動判定。"""
from __future__ import annotations

import io
from datetime import timedelta

from openpyxl import Workbook

from .conftest import TODAY


def d(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).strftime("%Y/%m/%d")


def upload(client, header: list[str], rows: list[list], name: str = "f.xlsx") -> dict:
    book = Workbook()
    sheet = book.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return client.post(
        "/api/imports/analyze",
        files={"file": (name, buffer.getvalue(), "application/octet-stream")},
    ).json()


def test_a_wbs_is_detected_as_tasks(client):
    body = upload(
        client,
        ["No", "タスク名", "担当者", "開始日", "終了日", "進捗", "状態"],
        [
            ["1", "要件定義", "山田", d(-10), d(-2), "100%", "完了"],
            ["2", "基本設計", "佐藤", d(-1), d(10), "40%", "進行中"],
        ],
    )
    assert body["content_kind"] == "wbs"
    assert body["has_task_data"] is True
    assert body["has_issue_text"] is False
    assert body["content_confidence"] >= 0.7
    assert any("タスク用の列" in e for e in body["content_evidence"])


def test_a_free_text_issue_list_is_detected_as_issues(client):
    body = upload(
        client,
        ["No", "項目", "課題・気になること"],
        [
            ["1", "全体", "経営層の意思決定がまだ出ていません。承認会議が延期になっています"],
            ["2", "設計", "帳票の出力仕様が決まっておらず、実装に進めない状態です"],
        ],
    )
    assert body["content_kind"] == "issues"
    assert body["has_issue_text"] is True
    assert body["has_task_data"] is False
    assert any("課題列" in e for e in body["content_evidence"])


def test_a_wbs_with_an_issue_column_is_mixed(client):
    body = upload(
        client,
        ["No", "タスク名", "担当者", "開始日", "終了日", "進捗", "課題"],
        [
            ["1", "要件定義", "山田", d(-10), d(-2), "100%", ""],
            ["2", "API仕様確定", "佐藤", d(-8), d(-1), "60%", "先方からの回答が届いておらず止まっています"],
        ],
    )
    assert body["content_kind"] == "mixed"
    assert body["has_task_data"] and body["has_issue_text"]


def test_column_headers_without_values_are_not_counted(client):
    """列名だけ揃っていて中身が空の表を WBS と誤判定しない。"""
    body = upload(
        client,
        ["タスク名", "担当者", "開始日", "終了日", "進捗"],
        [["名前だけの行", "", "", "", ""]],
    )
    assert body["content_kind"] == "unknown"
    assert body["has_task_data"] is False


def test_an_ambiguous_file_asks_instead_of_guessing(client):
    body = upload(client, ["項目", "メモ"], [["A", "短い"], ["B", "メモ"]])
    assert body["content_kind"] == "unknown"
    assert body["content_confidence"] < 0.5
    assert any("判別できなかった" in e for e in body["content_evidence"])


def test_a_prose_only_list_without_an_issue_column_is_issues(client):
    """課題列が無くても、名称列が長文だけなら課題リストとして扱う。"""
    body = upload(
        client,
        ["No", "内容"],
        [
            ["1", "経営層の意思決定がまだ出ておらず、後続の作業が止まっている状態です"],
            ["2", "帳票の出力仕様が決まっていないため、実装に着手できていません"],
        ],
    )
    assert body["content_kind"] == "issues"
    assert any("長文中心" in e for e in body["content_evidence"])


def test_importing_an_issue_list_creates_no_tasks(client):
    analyzed = upload(
        client,
        ["No", "項目", "課題・気になること"],
        [["1", "全体", "経営層の意思決定がまだ出ていません。承認会議が延期になっています"]],
    )
    result = client.post(
        "/api/imports/commit",
        json={
            "token": analyzed["token"],
            "mapping": analyzed["mapping"],
            "new_project_name": "課題のみPJ",
            "create_tasks": False,
        },
    ).json()

    assert result["created_tasks"] == 0
    assert result["warnings"]
    project_id = result["project_id"]
    assert client.get(f"/api/projects/{project_id}/tasks").json() == []

    # プロジェクトはできているので、そのまま課題分析に進める
    rows = client.post(
        "/api/imports/issue-rows",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"]},
    ).json()
    assert len(rows["rows"]) == 1
    analyzed_issues = client.post(
        "/api/issues/analyze", json={"project_id": project_id, "rows": rows["rows"]}
    ).json()
    assert analyzed_issues["counts"]["issue"] >= 1


def test_a_known_issue_header_is_mapped_by_name(client):
    body = upload(
        client,
        ["No", "項目", "気になっていること"],
        [
            ["1", "全体", "経営層の意思決定がまだ出ていません。承認会議が延期になっています"],
            ["2", "設計", "帳票の出力仕様が決まっておらず、実装に進めない状態です"],
        ],
    )
    assert body["mapping"]["issue"] == "気になっていること"
    assert body["content_kind"] == "issues"


def test_a_free_text_column_is_found_even_with_an_unknown_header(client):
    """辞書に無い列名でも、中身の長さから課題列と判断する。"""
    body = upload(
        client,
        ["No", "項目", "先方からの申し伝え事項2024"],
        [
            ["1", "全体", "経営層の意思決定がまだ出ていません。承認会議が延期になっています"],
            ["2", "設計", "帳票の出力仕様が決まっておらず、実装に進めない状態です"],
            ["3", "進捗", "特にありません"],
        ],
    )
    assert body["mapping"]["issue"] == "先方からの申し伝え事項2024"
    assert body["content_kind"] == "issues"
    assert any("自由記述に見えた" in w for w in body["warnings"])


def test_a_short_memo_column_is_not_treated_as_free_text(client):
    body = upload(client, ["項目", "メモ"], [["A", "短い"], ["B", "メモ"], ["C", "確認"]])
    assert body["mapping"]["issue"] is None
    assert body["content_kind"] == "unknown"
