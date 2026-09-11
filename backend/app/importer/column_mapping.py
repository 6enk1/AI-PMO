"""Header -> domain field matching with synonym and fuzzy fallback."""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "code": ("no", "no.", "id", "task id", "taskid", "タスクid", "wbs", "wbsno", "wbs no", "wbs番号", "番号", "項番", "作業id"),
    "title": (
        "タスク名", "タスク", "task", "task name", "taskname", "作業名", "作業内容", "件名", "名称",
        "項目", "項目名", "activity", "作業項目", "subject", "title", "内容", "実施事項",
    ),
    "parent": ("親タスク", "親", "parent", "parent task", "大分類", "中分類", "フェーズ", "phase", "工程", "カテゴリ", "category", "分類", "グループ"),
    "description": ("詳細", "説明", "description", "detail", "details", "作業詳細", "概要"),
    # カテゴリ（親タスク）の一段上のゴール。親タスクの説明として取り込む
    "category_goal": (
        "ゴール", "カテゴリのゴール", "大カテゴリのゴール", "このカテゴリのゴール", "目的", "目標",
        "狙い", "ねらい", "達成条件", "完了条件", "アウトカム", "goal", "objective", "outcome", "purpose",
    ),
    "owner": ("担当", "担当者", "責任者", "owner", "assignee", "assigned to", "pic", "主担当", "resource", "リソース", "実施者", "担当部署"),
    "planned_start": ("開始日", "開始予定日", "予定開始日", "着手日", "計画開始日", "start", "start date", "startdate", "開始", "予定開始", "着手予定日"),
    "planned_end": (
        "終了日", "終了予定日", "予定終了日", "完了予定日", "期限", "納期", "締切", "締め切り",
        "due", "due date", "duedate", "end", "end date", "enddate", "finish", "deadline", "終了", "予定終了", "完了期限",
    ),
    "actual_start": ("実績開始日", "実開始日", "実績開始", "actual start", "actualstart", "開始実績", "実際の開始日"),
    "actual_end": ("実績終了日", "実終了日", "実績終了", "完了日", "actual end", "actualend", "actual finish", "終了実績", "実際の終了日", "実完了日"),
    "progress": ("進捗", "進捗率", "達成率", "完了率", "progress", "progress %", "progress rate", "% complete", "percent complete", "完了%", "消化率"),
    "status": ("ステータス", "状態", "status", "進捗状況", "state", "対応状況", "作業状態", "進行状況"),
    "priority": ("優先度", "優先順位", "プライオリティ", "priority", "重要度", "importance", "ランク"),
    "dependency": ("依存関係", "依存", "先行タスク", "先行", "前工程", "predecessor", "predecessors", "depends on", "dependency", "前提タスク", "先行作業"),
    "issue": (
        "課題", "課題内容", "課題・懸念", "問題", "問題点", "問題事項", "issue", "issues",
        "懸念", "懸念事項", "懸念点", "リスク", "risk",
        "気になっていること", "気になること", "気になる点", "困っていること", "困りごと",
        "相談事項", "申し送り", "指摘事項", "要望", "コメント欄",
    ),
    "notes": ("備考", "メモ", "note", "notes", "remarks", "コメント", "comment", "補足", "特記事項"),
    "milestone": ("マイルストーン", "milestone", "ms", "重要日程", "節目"),
    "estimated_hours": ("工数", "予定工数", "見積工数", "estimate", "estimated hours", "hours", "人日", "人時", "工数(h)", "工数(人日)", "作業量"),
}

FIELD_LABELS: dict[str, str] = {
    "code": "Task ID / WBS No",
    "title": "タスク名",
    "parent": "親タスク",
    "description": "詳細",
    "category_goal": "カテゴリのゴール",
    "owner": "担当者",
    "planned_start": "開始予定日",
    "planned_end": "終了予定日",
    "actual_start": "実績開始日",
    "actual_end": "実績終了日",
    "progress": "進捗率",
    "status": "Status",
    "priority": "Priority",
    "dependency": "依存関係",
    "issue": "課題",
    "notes": "備考",
    "milestone": "マイルストーン",
    "estimated_hours": "工数",
}

REQUIRED_FIELDS = ("title",)

ACTUAL_MARKERS = ("実績", "実際", "actual", "実施")
PLANNED_MARKERS = ("予定", "計画", "plan", "planned")


def normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"[\s_\-/\\()（）\[\]【】「」:：.,、。*＊#※]", "", text)
    return text.replace("％", "%").strip()


@dataclass
class Candidate:
    field: str
    column: str
    score: float
    reason: str


def _score(column_norm: str, synonym_norm: str) -> tuple[float, str]:
    if not column_norm or not synonym_norm:
        return 0.0, ""
    if column_norm == synonym_norm:
        return 1.0, "完全一致"
    if column_norm.startswith(synonym_norm) or column_norm.endswith(synonym_norm):
        return 0.8 + 0.1 * len(synonym_norm) / max(len(column_norm), 1), "前方/後方一致"
    if synonym_norm in column_norm:
        return 0.55 + 0.3 * len(synonym_norm) / max(len(column_norm), 1), "部分一致"
    ratio = difflib.SequenceMatcher(None, column_norm, synonym_norm).ratio()
    if ratio >= 0.8:
        return ratio * 0.8, f"類似度 {ratio:.2f}"
    return 0.0, ""


def _incompatible(field: str, column_norm: str) -> bool:
    """Keep 実績終了日 away from planned_end and 予定終了日 away from actual_end."""
    has_actual = any(normalize_header(m) in column_norm for m in ACTUAL_MARKERS)
    has_planned = any(normalize_header(m) in column_norm for m in PLANNED_MARKERS)
    if field.startswith("planned_") and has_actual and not has_planned:
        return True
    if field.startswith("actual_") and has_planned and not has_actual:
        return True
    return False


def score_candidates(columns: list[str]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for column in columns:
        column_norm = normalize_header(column)
        if not column_norm:
            continue
        for field, synonyms in FIELD_SYNONYMS.items():
            if _incompatible(field, column_norm):
                continue
            best = 0.0
            best_reason = ""
            for synonym in synonyms:
                score, reason = _score(column_norm, normalize_header(synonym))
                if score > best:
                    best, best_reason = score, f"{reason}: 「{synonym}」"
            if best >= 0.5:
                candidates.append(Candidate(field=field, column=column, score=round(best, 3), reason=best_reason))
    return sorted(candidates, key=lambda c: c.score, reverse=True)


def guess_mapping(
    columns: list[str], allow_title_fallback: bool = True
) -> tuple[dict[str, str | None], list[Candidate]]:
    """Greedily assign at most one column per field and one field per column.

    ``allow_title_fallback`` は、タスク名らしい列が無いときに未使用列を仮割当するか。
    課題リスト（タスク名の列が存在しない）では、無関係な列を掴まないよう無効にする。
    """
    candidates = score_candidates(columns)
    mapping: dict[str, str | None] = {field: None for field in FIELD_SYNONYMS}
    used_columns: set[str] = set()
    chosen: list[Candidate] = []
    for candidate in candidates:
        if mapping.get(candidate.field) is not None or candidate.column in used_columns:
            continue
        mapping[candidate.field] = candidate.column
        used_columns.add(candidate.column)
        chosen.append(candidate)

    # A WBS with no recognisable title column still needs one: fall back to the
    # first unused text column so the user has something to correct.
    if allow_title_fallback and mapping.get("title") is None:
        for column in columns:
            if column not in used_columns and normalize_header(column):
                mapping["title"] = column
                used_columns.add(column)
                chosen.append(Candidate("title", column, 0.3, "推定（未検出のため先頭列を仮割当）"))
                break
    return mapping, chosen


def header_match_score(columns: list[str]) -> float:
    """How much a candidate header row looks like a WBS header."""
    candidates = score_candidates([str(c) for c in columns])
    best_per_field: dict[str, float] = {}
    for candidate in candidates:
        best_per_field[candidate.field] = max(best_per_field.get(candidate.field, 0), candidate.score)
    return round(sum(best_per_field.values()), 3)
