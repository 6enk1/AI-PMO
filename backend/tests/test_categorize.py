"""Automatic categorisation: keyword classification, suggestions and apply."""
from __future__ import annotations

import pytest

from app.analysis.categorize import classify_text, suggest_categories
from app.analysis.snapshot import build_snapshot

from .conftest import TODAY, day


@pytest.mark.parametrize(
    "title,expected",
    [
        ("現行業務調査", "要件定義"),
        ("要件定義書の作成", "要件定義"),
        ("基本設計", "設計"),
        ("API仕様確定", "設計"),
        ("Backend開発", "開発・実装"),
        ("フロントエンド実装", "開発・実装"),
        ("総合テスト", "テスト"),
        ("UAT準備", "テスト"),
        ("本番リリース", "移行・リリース"),
        ("データ移行リハーサル", "移行・リリース"),
        ("ユーザー教育", "教育・展開"),
        ("ベンダー選定", "調達・契約"),
        ("セキュリティ診断", "セキュリティ"),
        ("サーバ環境構築", "インフラ・環境"),
        ("週次定例の準備", "プロジェクト管理"),
    ],
)
def test_keyword_classification(title, expected):
    guess = classify_text(title)
    assert guess.label == expected
    assert guess.matched, "分類には必ず根拠となる一致語が残ること"
    assert 0 < guess.confidence <= 0.95


def test_unclassifiable_text_returns_nothing():
    assert classify_text("打ち合わせ").label is None
    assert classify_text("").label is None


def test_description_and_notes_are_used_as_a_hint():
    assert classify_text("フェーズA", "結合テストの準備を行う").label == "テスト"


def test_suggestions_group_uncategorized_tasks(db, project, factory):
    factory.task("現行業務調査", planned_end=day(5))
    factory.task("要件定義書作成", planned_end=day(8))
    factory.task("基本設計", planned_end=day(12))
    factory.task("詳細設計", planned_end=day(15))

    snapshot = build_snapshot(db, project.id, today=TODAY)
    suggestions = {s.task_title: s for s in suggest_categories(snapshot)}

    assert suggestions["現行業務調査"].suggested_category == "要件定義"
    assert suggestions["基本設計"].suggested_category == "設計"
    assert all(s.reason for s in suggestions.values())
    assert all(s.source == "rules" for s in suggestions.values())


def test_existing_categories_are_reused_instead_of_creating_duplicates(db, project, factory):
    phase = factory.task("フェーズ2: 開発")
    factory.task("画面実装", parent_task_id=phase.id)
    factory.task("バッチ開発")

    snapshot = build_snapshot(db, project.id, today=TODAY)
    suggestion = next(s for s in suggest_categories(snapshot) if s.task_title == "バッチ開発")

    assert suggestion.suggested_category == "フェーズ2: 開発"
    assert suggestion.existing_category_id == phase.id
    assert "再利用" in suggestion.reason


def test_already_categorized_tasks_are_skipped_by_default(db, project, factory):
    phase = factory.task("設計")
    factory.task("基本設計", parent_task_id=phase.id)
    factory.task("詳細設計")

    snapshot = build_snapshot(db, project.id, today=TODAY)
    titles = {s.task_title for s in suggest_categories(snapshot)}
    assert titles == {"詳細設計"}

    everything = {s.task_title for s in suggest_categories(snapshot, include_categorized=True)}
    assert "基本設計" not in everything  # 既に正しいカテゴリにいるので提案不要


def test_categories_themselves_are_never_reclassified(db, project, factory):
    phase = factory.task("テスト")
    factory.task("結合テスト", parent_task_id=phase.id)

    snapshot = build_snapshot(db, project.id, today=TODAY)
    assert all(s.task_id != phase.id for s in suggest_categories(snapshot, include_categorized=True))


# --------------------------------------------------------------------------- API
def test_suggest_endpoint_falls_back_to_rules(client, project, factory):
    factory.task("現行業務調査")
    factory.task("総合テスト")

    body = client.get(f"/api/projects/{project.id}/categories/suggest").json()
    assert body["llm_used"] is False
    assert "ルールベース" in body["llm_note"]
    categories = {s["suggested_category"] for s in body["suggestions"]}
    assert categories == {"要件定義", "テスト"}


def test_apply_creates_categories_and_assigns_parents(client, project, factory):
    first = factory.task("現行業務調査")
    second = factory.task("要件定義書作成")

    result = client.post(
        f"/api/projects/{project.id}/categories/apply",
        json={
            "assignments": [
                {"task_id": first.id, "category_name": "要件定義"},
                {"task_id": second.id, "category_name": "要件定義"},
            ]
        },
    ).json()

    assert result["updated_tasks"] == 2
    assert result["created_categories"] == ["要件定義"]  # カテゴリは1度だけ作られる

    tasks = {t["title"]: t for t in client.get(f"/api/projects/{project.id}/tasks").json()}
    assert tasks["現行業務調査"]["category"] == "要件定義"
    assert tasks["要件定義書作成"]["category"] == "要件定義"
    assert tasks["要件定義"]["child_count"] == 2


def test_apply_reuses_an_existing_category(client, project, factory):
    phase = factory.task("フェーズ1: 要件・設計")
    task = factory.task("現行業務調査")

    result = client.post(
        f"/api/projects/{project.id}/categories/apply",
        json={"assignments": [{"task_id": task.id, "category_name": "フェーズ1: 要件・設計"}]},
    ).json()

    assert result["created_categories"] == []
    assert result["updated_tasks"] == 1
    read = client.get(f"/api/tasks/{task.id}").json()
    assert read["parent_task_id"] == phase.id


def test_apply_refuses_to_build_a_cycle(client, project, factory):
    parent = factory.task("親")
    child = factory.task("子", parent_task_id=parent.id)

    result = client.post(
        f"/api/projects/{project.id}/categories/apply",
        json={"assignments": [{"task_id": parent.id, "category_name": "子"}]},
    ).json()

    assert result["updated_tasks"] == 0
    assert result["skipped"]
    assert client.get(f"/api/tasks/{parent.id}").json()["parent_task_id"] is None
    assert client.get(f"/api/tasks/{child.id}").json()["parent_task_id"] == parent.id


def test_apply_is_idempotent(client, project, factory):
    task = factory.task("総合テスト")
    body = {"assignments": [{"task_id": task.id, "category_name": "テスト"}]}
    client.post(f"/api/projects/{project.id}/categories/apply", json=body)
    again = client.post(f"/api/projects/{project.id}/categories/apply", json=body).json()

    assert again["updated_tasks"] == 0
    assert again["created_categories"] == []
    tasks = client.get(f"/api/projects/{project.id}/tasks").json()
    assert len([t for t in tasks if t["title"] == "テスト"]) == 1


def test_summary_tasks_roll_up_dates_and_progress(client, project, factory):
    """自動生成したカテゴリは日付も進捗も持たないので、子から集計する。"""
    category = factory.task("要件定義")
    factory.task(
        "現行業務調査", parent_task_id=category.id, planned_start=day(-10), planned_end=day(-4),
        status="done", progress=100,
    )
    factory.task(
        "要件定義書作成", parent_task_id=category.id, planned_start=day(-3), planned_end=day(6),
        status="in_progress", progress=40,
    )

    read = client.get(f"/api/tasks/{category.id}").json()
    assert read["is_summary"] is True
    assert read["effective_start"] == str(day(-10))
    assert read["effective_end"] == str(day(6))
    assert 60 <= read["effective_progress"] <= 75  # 期間で重み付けした平均
    assert read["progress"] == 0  # 保存値そのものは変えない


def test_auto_created_categories_do_not_raise_false_inconsistencies(client, db, project, factory):
    from app.analysis.hidden_issues import detect_hidden_issues
    from app.analysis.snapshot import build_snapshot

    category = factory.task("テスト")
    factory.task(
        "結合テスト", parent_task_id=category.id, planned_start=day(-5), planned_end=day(5),
        status="in_progress", progress=80, actual_start=day(-5),
    )

    snapshot = build_snapshot(db, project.id, today=TODAY)
    findings = detect_hidden_issues(snapshot)
    assert all(f.task_id != category.id for f in findings if f.finding_type == "progress_inconsistency")


def test_a_parent_claiming_more_progress_than_its_children_is_still_flagged(db, project, factory):
    from app.analysis.hidden_issues import detect_hidden_issues
    from app.analysis.snapshot import build_snapshot

    category = factory.task("設計", status="in_progress", progress=90)
    factory.task(
        "基本設計", parent_task_id=category.id, planned_start=day(-5), planned_end=day(5),
        status="in_progress", progress=20, actual_start=day(-5),
    )

    snapshot = build_snapshot(db, project.id, today=TODAY)
    findings = [
        f
        for f in detect_hidden_issues(snapshot)
        if f.finding_type == "progress_inconsistency" and f.task_id == category.id
    ]
    assert findings
    assert any("子Taskとの乖離" in e.label for e in findings[0].evidence)
