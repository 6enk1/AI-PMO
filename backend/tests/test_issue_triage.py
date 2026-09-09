"""自由記述の課題リストの判定・整形と、確認後の一括登録。"""
from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.analysis.issue_triage import (
    classify_statement,
    match_tasks,
    split_statements,
    summarize_title,
)

TASKS = [(1, "API仕様確定"), (2, "データ移行設計"), (3, "総合テスト"), (4, "ユーザー教育")]


# --------------------------------------------------------------------------- 分類
@pytest.mark.parametrize(
    "text,expected",
    [
        ("API仕様の回答が先方から返ってきておらず、開発が止まっています", "issue"),
        ("移行データにエラーが出ていて取り込めません", "issue"),
        ("画面の表示内容について確認してほしいです", "issue"),
        ("テスト環境の準備が遅れています", "issue"),
        ("要件定義は予定通り完了しました", "not_issue"),
        ("特にありません", "not_issue"),
        ("先週分の作業を実施しました。ご報告まで", "not_issue"),
        ("ありがとうございました", "not_issue"),
    ],
)
def test_labels_are_assigned_from_the_wording(text, expected):
    result = classify_statement(text, TASKS)
    assert result.label == expected
    assert result.reasons, "判定理由が空にならないこと"


def test_vague_text_becomes_uncertain():
    assert classify_statement("検討中", TASKS).label == "uncertain"
    assert classify_statement("そのあたりどうなんでしょうか", TASKS).label == "uncertain"


def test_report_and_issue_in_one_sentence_needs_a_human():
    result = classify_statement("設計は完了しましたが、レビュー指摘が残っていて対応が必要です", TASKS)
    assert result.label == "uncertain"
    assert any("混在" in reason for reason in result.reasons)


def test_severity_is_estimated_only_for_issues():
    assert classify_statement("至急対応が必要です。本番が停止しています", TASKS).severity_estimate == "高"
    assert classify_statement("できれば見直したいという程度の課題です", TASKS).severity_estimate == "低"
    assert classify_statement("移行データにエラーが出ています", TASKS).severity_estimate == "中"
    # 課題と断定できない行に重要度を決め打ちしない
    assert classify_statement("検討中", TASKS).severity_estimate == "不明"
    assert classify_statement("完了しました", TASKS).severity_estimate == "不明"


# --------------------------------------------------------------------------- 整形
def test_title_uses_only_words_from_the_source():
    text = "外部連携APIの認証方式が決まっていないため、実装に着手できません"
    title = summarize_title(text)
    assert len(title) <= 28
    # 元文に無い語を作らない
    compact = text.replace("、", "").replace("。", "")
    assert title.rstrip("…").replace("、", "") in compact


def test_description_keeps_the_original_content():
    text = "  移行元データに重複レコードがあり、\n 取り込みが失敗します。 "
    result = classify_statement(text, TASKS)
    assert "重複レコード" in result.description
    assert "取り込みが失敗" in result.description
    assert result.description == result.description.strip()


def test_not_issue_rows_carry_no_generated_fields():
    result = classify_statement("順調に進んでいます", TASKS)
    assert result.label == "not_issue"
    assert result.title == "" and result.description == ""


# --------------------------------------------------------------------------- 分割
def test_multiple_issues_in_one_cell_are_split():
    text = "移行データの件を確認してほしいです。あとテスト環境でエラーが出ていて進められません"
    parts = split_statements(text)
    assert len(parts) == 2
    assert all(classify_statement(p, TASKS).label == "issue" for p in parts)


def test_bullets_and_newlines_are_split():
    assert len(split_statements("・API仕様が未定\n・テスト環境が使えない")) == 2
    assert len(split_statements("1. 権限設定が未対応\n2. 帳票の出力でエラー")) == 2


def test_a_single_long_sentence_is_not_forced_apart():
    text = "先週から続いている移行データの不整合について、原因調査が終わっていません"
    assert len(split_statements(text)) == 1


def test_empty_text_yields_nothing():
    assert split_statements("") == []
    assert split_statements("   \n  ") == []


# --------------------------------------------------------------------------- 関連タスク
def test_related_tasks_are_only_suggested_when_they_match():
    hits = match_tasks("API仕様確定の回答が来ていません", TASKS)
    assert [c.title for c in hits] == ["API仕様確定"]

    assert match_tasks("駐車場の場所を教えてください", TASKS) == []


def test_related_tasks_are_ranked_and_capped():
    hits = match_tasks("総合テストとユーザー教育の日程が未定です", TASKS, limit=2)
    assert len(hits) <= 2
    assert {c.title for c in hits} <= {"総合テスト", "ユーザー教育"}


# --------------------------------------------------------------------------- API
def test_analyze_endpoint_separates_issues_from_noise(client, project, factory):
    factory.task("API仕様確定")
    body = client.post(
        "/api/issues/analyze",
        json={
            "project_id": project.id,
            "rows": [
                {"row_index": 0, "text": "API仕様確定の回答が先方から来ておらず開発が止まっています"},
                {"row_index": 1, "text": "要件定義は予定通り完了しました。ありがとうございました"},
                {"row_index": 2, "text": "検討中"},
            ],
        },
    ).json()

    assert body["llm_used"] is False
    assert "ルールベース" in body["llm_note"]
    labels = {item["row_index"]: item["label"] for item in body["items"]}
    assert labels[0] == "issue"
    assert labels[1] == "not_issue"
    assert labels[2] == "uncertain"
    assert body["counts"]["issue"] == 1

    issue_item = next(item for item in body["items"] if item["row_index"] == 0)
    assert issue_item["title"] and len(issue_item["title"]) <= 30
    assert issue_item["severity"] in ("low", "medium", "high", "critical")
    assert [c["title"] for c in issue_item["related_task_candidates"]] == ["API仕様確定"]
    assert issue_item["related_task_candidates"][0]["task_id"] is not None


def test_analyze_works_without_a_project(client):
    body = client.post(
        "/api/issues/analyze",
        json={"rows": [{"text": "帳票出力でエラーが出ています"}]},
    ).json()
    assert body["items"][0]["label"] == "issue"
    assert body["items"][0]["related_task_candidates"] == []


def test_analyze_splits_a_cell_into_several_candidates(client, project):
    body = client.post(
        "/api/issues/analyze",
        json={
            "project_id": project.id,
            "rows": [{"row_index": 0, "text": "権限設定が未対応です。あと帳票の出力でエラーが出ています"}],
        },
    ).json()
    assert len(body["items"]) == 2
    assert all(item["split"] for item in body["items"])
    assert len({item["id"] for item in body["items"]}) == 2


def test_analyze_rejects_an_unknown_project(client):
    response = client.post("/api/issues/analyze", json={"project_id": 9999, "rows": []})
    assert response.status_code == 404


def test_bulk_create_registers_only_what_was_sent(client, project, factory):
    task = factory.task("API仕様確定")
    person = factory.person("佐藤")
    result = client.post(
        "/api/issues/bulk_create",
        json={
            "project_id": project.id,
            "items": [
                {"title": "API仕様の回答待ち", "description": "先方からの回答が届いていない",
                 "severity": "high", "task_id": task.id, "owner_id": person.id},
                {"title": "帳票出力のエラー", "severity": "medium"},
            ],
        },
    ).json()

    assert result["created"] == 2
    assert len(result["issue_ids"]) == 2

    issues = {i["title"]: i for i in client.get(f"/api/projects/{project.id}/issues").json()}
    assert issues["API仕様の回答待ち"]["severity"] == "high"
    assert issues["API仕様の回答待ち"]["task_title"] == "API仕様確定"
    assert issues["API仕様の回答待ち"]["owner_name"] == "佐藤"
    assert issues["帳票出力のエラー"]["task_id"] is None
    assert {i["code"] for i in issues.values()} == {"I-001", "I-002"}


def test_bulk_create_drops_references_from_another_project(client, project, db):
    from app.models import Project, Task

    other = Project(name="別PJ")
    db.add(other)
    db.commit()
    foreign = Task(project_id=other.id, title="別PJのタスク")
    db.add(foreign)
    db.commit()

    result = client.post(
        "/api/issues/bulk_create",
        json={"project_id": project.id, "items": [{"title": "課題", "task_id": foreign.id}]},
    ).json()

    assert result["created"] == 1
    assert result["skipped"]
    assert client.get(f"/api/projects/{project.id}/issues").json()[0]["task_id"] is None


def test_bulk_create_rejects_an_unknown_project(client):
    response = client.post("/api/issues/bulk_create", json={"project_id": 9999, "items": []})
    assert response.status_code == 404


# --------------------------------------------------------------------------- Import連携
def test_import_issue_rows_returns_every_free_text_row(client):
    book = Workbook()
    sheet = book.active
    sheet.append(["No", "作業内容", "課題・気になること"])
    sheet.append(["1", "要件定義", "特にありません"])
    sheet.append(["2", "API仕様確定", "先方の回答が来ていません。至急確認したいです"])
    sheet.append(["3", "画面設計", ""])
    buffer = io.BytesIO()
    book.save(buffer)

    analyzed = client.post(
        "/api/imports/analyze",
        files={"file": ("issues.xlsx", buffer.getvalue(), "application/octet-stream")},
    ).json()

    rows = client.post(
        "/api/imports/issue-rows",
        json={"token": analyzed["token"], "mapping": analyzed["mapping"]},
    ).json()

    assert rows["text_column"] == "課題・気になること"
    assert [r["text"] for r in rows["rows"]] == [
        "特にありません",
        "先方の回答が来ていません。至急確認したいです",
    ]
    assert rows["rows"][1]["task_hint"] == "API仕様確定"  # 同じ行のタスク名を手がかりに渡す

    # そのまま analyze に流せる
    body = client.post("/api/issues/analyze", json={"rows": rows["rows"]}).json()
    labels = [item["label"] for item in body["items"]]
    assert "not_issue" in labels and "issue" in labels


def test_negated_wording_is_recognised_as_an_issue():
    """「決まっていない」「止まります」のような否定・停滞の言い回しを拾う。"""
    assert classify_statement("経営層の意思決定がまだ出ていません", TASKS).label == "issue"
    assert classify_statement("承認会議が延期になっており、後続が止まります", TASKS).label == "issue"
    assert classify_statement("見積が1社しか届いていません", TASKS).label == "issue"


def test_report_phrases_are_not_mistaken_for_issue_keywords():
    """「問題ありません」の中の「問題」を課題語と数えない。"""
    result = classify_statement("問題ありません", TASKS)
    assert result.label == "not_issue"
    assert not any("課題を示す語" in reason for reason in result.reasons)


def test_a_mixed_sentence_with_strong_evidence_is_an_issue():
    result = classify_statement("環境構築は完了しましたが、ログインでエラーが出ていて検証が進められません", TASKS)
    assert result.label == "issue"
    assert any("混在" in reason for reason in result.reasons)
