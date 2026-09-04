"""Automatic task categorisation.

Categories are not a separate entity: a category is simply a task that has
children. This module proposes which category each task belongs to, using a
keyword taxonomy first (deterministic, explainable) and optionally letting the
LLM refine the result - the same Structured Analysis -> LLM Reasoning order the
rest of the AI PMO layer follows.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .snapshot import ProjectSnapshot, TaskView

# 一般的なプロジェクトの工程。上から順に評価し、最長一致を優先する。
TAXONOMY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("企画・構想", ("企画", "構想", "提案", "rfp", "rfi", "稟議", "キックオフ", "立ち上げ", "planning", "kickoff", "コンセプト")),
    ("要件定義", ("要件定義", "要件", "要求", "ヒアリング", "業務調査", "現行調査", "現行業務", "as-is", "to-be", "requirement", "課題整理", "業務整理")),
    ("設計", ("基本設計", "詳細設計", "設計", "アーキテクチャ", "画面設計", "db設計", "er図", "方式", "仕様確定", "仕様策定", "design", "方針策定")),
    ("開発・実装", ("実装", "開発", "製造", "コーディング", "バッチ", "api", "frontend", "backend", "build", "implement", "coding", "画面作成")),
    ("テスト", ("テスト", "検証", "単体", "結合", "総合", "uat", "受入", "品質", "test", "qa", "レビュー")),
    ("移行・リリース", ("データ移行", "移行", "リリース", "本番", "カットオーバー", "切替", "デプロイ", "展開", "release", "migration", "deploy")),
    ("インフラ・環境", ("インフラ", "環境構築", "サーバ", "ネットワーク", "クラウド", "aws", "azure", "gcp", "基盤", "infra", "構築環境")),
    ("セキュリティ", ("セキュリティ", "脆弱性", "診断", "監査", "認証", "security", "権限設計")),
    ("データ", ("マスタ整備", "マスタ", "データ整備", "データ連携", "etl", "集計", "分析基盤", "データ")),
    ("運用・保守", ("運用", "保守", "監視", "サポート", "障害対応", "ヘルプデスク", "operation", "maintenance")),
    ("教育・展開", ("教育", "研修", "トレーニング", "マニュアル", "説明会", "training", "ドキュメント")),
    ("調達・契約", ("調達", "契約", "発注", "ベンダー", "見積", "購買", "procurement", "選定")),
    ("プロジェクト管理", ("進捗管理", "定例", "報告", "pmo", "課題管理", "wbs", "会議", "調整", "management", "全体管理")),
)

MAX_SUGGESTED_CATEGORIES = 8


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower().replace(" ", "")


@dataclass
class CategoryGuess:
    label: str | None
    confidence: float
    matched: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if not self.label:
            return "分類の手がかりになる語が見つかりませんでした"
        return "キーワード一致: " + "、".join(self.matched)


def classify_text(*parts: str | None) -> CategoryGuess:
    """Classify free text into one taxonomy label. Longest keyword wins."""
    text = _normalize(" ".join(p for p in parts if p))
    if not text:
        return CategoryGuess(None, 0.0)

    best_label: str | None = None
    best_score = 0.0
    best_matches: list[str] = []
    for label, keywords in TAXONOMY:
        matched = [k for k in keywords if _normalize(k) in text]
        if not matched:
            continue
        # 長いキーワードほど具体的なので重く見る
        score = sum(len(_normalize(k)) for k in matched) + 0.5 * (len(matched) - 1)
        if score > best_score:
            best_label, best_score, best_matches = label, score, matched

    if best_label is None:
        return CategoryGuess(None, 0.0)
    confidence = min(0.95, 0.45 + 0.12 * len(best_matches) + 0.03 * best_score)
    return CategoryGuess(best_label, round(confidence, 2), best_matches)


def classify_task(view: TaskView) -> CategoryGuess:
    return classify_text(view.title, view.task.description, view.task.notes)


@dataclass
class Suggestion:
    task_id: int
    task_code: str | None
    task_title: str
    current_category: str | None
    suggested_category: str
    existing_category_id: int | None  # 既存カテゴリを再利用する場合のTask ID
    confidence: float
    reason: str
    source: str = "rules"


def existing_categories(snapshot: ProjectSnapshot) -> dict[int, str]:
    """Tasks that already act as a category (they have children)."""
    return {v.id: v.title for v in snapshot.task_views() if v.child_ids}


def suggest_categories(
    snapshot: ProjectSnapshot, include_categorized: bool = False
) -> list[Suggestion]:
    """Propose a category for each task, reusing the project's own categories."""
    # 既存カテゴリを taxonomy ラベルへ写像し、同じ工程なら再利用する
    reuse: dict[str, tuple[int, str]] = {}
    for category_id, title in existing_categories(snapshot).items():
        guess = classify_text(title)
        if guess.label and guess.label not in reuse:
            reuse[guess.label] = (category_id, title)

    suggestions: list[Suggestion] = []
    for view in snapshot.task_views():
        if view.child_ids:
            continue  # カテゴリ自体は分類対象にしない
        if view.task.parent_task_id and not include_categorized:
            continue
        guess = classify_task(view)
        if not guess.label:
            continue
        reused = reuse.get(guess.label)
        current = snapshot.category_of(view.id)
        label = reused[1] if reused else guess.label
        if current == label:
            continue  # すでにそのカテゴリに入っている
        suggestions.append(
            Suggestion(
                task_id=view.id,
                task_code=view.code,
                task_title=view.title,
                current_category=current,
                suggested_category=label,
                existing_category_id=reused[0] if reused else None,
                confidence=guess.confidence,
                reason=guess.reason
                + (f"（既存カテゴリ「{reused[1]}」を再利用）" if reused else ""),
            )
        )

    # 1件しか入らないカテゴリを乱立させない
    counts: dict[str, int] = {}
    for s in suggestions:
        counts[s.suggested_category] = counts.get(s.suggested_category, 0) + 1
    keep = {
        name
        for name in sorted(counts, key=lambda n: counts[n], reverse=True)[:MAX_SUGGESTED_CATEGORIES]
    }
    return [s for s in suggestions if s.suggested_category in keep]
