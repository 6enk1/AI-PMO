"""自由記述の課題リストを、登録可能な課題候補へ整理する。

先方が作る課題リストは1行1課題になっておらず、進捗報告や感想が混ざる。
ここでは行テキストを

    分割 → 分類（issue / uncertain / not_issue）→ 課題名・詳細・重要度の生成

の順で処理する。すべてキーワード辞書によるルールベースで完結し、
LLMが使える場合は :mod:`app.ai.llm` が結果を上書きする（捏造は許さない）。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

LABELS = ("issue", "uncertain", "not_issue")
SEVERITIES = ("高", "中", "低", "不明")

# 対応・意思決定を要する記述
ISSUE_KEYWORDS: tuple[str, ...] = (
    "遅れ", "遅延", "間に合わ", "未対応", "未着手", "未定", "決まっていない", "決まってない",
    "エラー", "不具合", "障害", "動かない", "動作しない", "落ちる", "できない", "出来ない",
    "不足", "足りない", "困っ", "止まっ", "停止", "懸念", "リスク", "問題", "課題",
    "確認してほしい", "確認をお願い", "確認願います", "回答待ち", "返答がない", "返事がない",
    "対応してほしい", "対応が必要", "対応をお願い", "要検討", "検討したい", "調整が必要",
    "依頼したい", "至急", "修正してほしい", "見直し", "漏れ", "抜け", "ミス", "手戻り",
    "齟齬", "認識違い", "食い違", "не",  # 誤入力対策のダミーは入れない
    "遅い", "重い", "つながらない", "反映されない", "表示されない", "解決していない",
    "承認待ち", "決裁待ち", "調整中で", "ペンディング", "保留", "難しい", "厳しい",
)
# 上の辞書に紛れ込んだ非日本語トークンを除外
ISSUE_KEYWORDS = tuple(k for k in ISSUE_KEYWORDS if re.search(r"[ぁ-んァ-ヶ一-龥]", k))

# 進捗報告・感想・挨拶
NOT_ISSUE_KEYWORDS: tuple[str, ...] = (
    "完了しました", "完了です", "完了済", "対応済み", "対応完了", "済みです", "終わりました",
    "順調", "予定通り", "予定どおり", "問題ありません", "問題なし", "特にありません",
    "特になし", "実施しました", "実施済", "共有します", "共有まで", "ご報告", "報告します",
    "よろしくお願いします", "ありがとうございました", "ありがとうございます", "お疲れ様",
    "以上です", "参考まで", "承知しました", "了解しました", "引き続き",
)

# 否定形など、単語だけでは拾えない言い回し。
# 「特にありません」「問題ありません」を巻き込まないよう、あり + ません は除外する。
ISSUE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?<!あり)ません(?!でした)", "否定の言い回し"),
    (r"てい?ない", "否定の言い回し"),
    (r"止ま[らりるっ]", "作業が止まっている"),
    (r"進め(?:られ)?な|進まな|進んでいな|進められませ", "進められない"),
    (r"(?:てお|てい)らず", "否定の言い回し"),
    (r"(?:未|不)(?:確定|明確|整備|整理)", "未確定"),
    (r"延期|中断|見送り|持ち越し", "予定の後ろ倒し"),
    (r"催促|督促", "催促が必要"),
    (r"わからな|分からな|不明", "内容が不明"),
)

SEVERITY_HIGH = ("至急", "緊急", "重大", "クリティカル", "致命", "全面停止", "業務停止", "止まっている", "使えない", "リリースできない")
SEVERITY_LOW = ("軽微", "参考まで", "余裕があれば", "できれば", "将来的に", "いずれ", "念のため")

# 対象や影響がぼやける表現
VAGUE_MARKERS = ("かもしれ", "かも。", "たぶん", "多分", "気がする", "ような気", "どうなん", "？", "?", "検討中", "どうしよう")

BULLET_PATTERN = re.compile(r"^\s*(?:[・･\-–—*●○◆■□▪]|[0-9０-９]{1,2}\s*[.)．）、]|[①-⑳]|[（(][0-9０-９]{1,2}[)）])\s*")
SENTENCE_SPLIT = re.compile(r"(?<=[。！!？?])\s*")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def _clean_segment(segment: str) -> str:
    text = BULLET_PATTERN.sub("", normalize(segment))
    return re.sub(r"\s+", " ", text).strip(" 　・")


def _issue_hits(text: str) -> list[str]:
    hits = [k for k in ISSUE_KEYWORDS if k in text]
    hits += [label for pattern, label in ISSUE_PATTERNS if re.search(pattern, text)]
    return list(dict.fromkeys(hits))


def _not_issue_hits(text: str) -> list[str]:
    return [k for k in NOT_ISSUE_KEYWORDS if k in text]


def _mask(text: str, keywords: list[str]) -> str:
    """「問題ありません」の中の「問題」を課題語と数えないよう、報告語を伏せる。"""
    masked = text
    for keyword in keywords:
        masked = masked.replace(keyword, "〓" * len(keyword))
    return masked


def split_statements(text: str) -> list[str]:
    """1セルの自由記述を、課題候補の単位へ分割する。

    改行・箇条書き・番号を優先し、それでも1本の長文なら、課題を示す語が
    複数の文にまたがるときだけ文単位で割る（無理に分割はしない）。
    """
    raw = normalize(text)
    if not raw:
        return []

    segments = [s for s in re.split(r"[\n\r]+", raw) if s.strip()]
    # 箇条書き記号が文中に並ぶケース（1行に「・A ・B」）も割る
    expanded: list[str] = []
    for segment in segments:
        parts = re.split(r"\s*[・･]\s*(?=\S)", segment) if segment.count("・") >= 2 else [segment]
        expanded.extend(p for p in parts if p.strip())

    results: list[str] = []
    for segment in expanded:
        cleaned = _clean_segment(segment)
        if not cleaned:
            continue
        sentences = [s.strip() for s in SENTENCE_SPLIT.split(cleaned) if s.strip()]
        # 課題を示す語を含む文が2つ以上あるときだけ、文単位に分ける
        if len(sentences) >= 2 and sum(1 for s in sentences if _issue_hits(s)) >= 2:
            results.extend(s for s in sentences if len(s) >= 4)
        else:
            results.append(cleaned)

    return [r for r in results if len(r) >= 3]


@dataclass
class TaskCandidate:
    task_id: int | None
    title: str
    score: float

    def as_dict(self) -> dict:
        return {"task_id": self.task_id, "title": self.title, "score": round(self.score, 2)}


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"[\s　,、。・:：/（）()\[\]「」]", "", text.lower())
    return {compact[i : i + 2] for i in range(len(compact) - 1)} if len(compact) >= 2 else set()


def match_tasks(
    text: str, tasks: list[tuple[int | None, str]], limit: int = 3, threshold: float = 0.34
) -> list[TaskCandidate]:
    """既存タスク名との一致度から関連タスク候補を返す。

    無関係な提案をしないため、部分一致か十分な bigram 一致がある場合しか返さない。
    """
    haystack = normalize(text).lower()
    haystack_grams = _bigrams(haystack)
    candidates: list[TaskCandidate] = []
    for task_id, title in tasks:
        name = normalize(title)
        if not name:
            continue
        lowered = name.lower()
        if len(lowered) >= 3 and lowered in haystack:
            candidates.append(TaskCandidate(task_id, name, 1.0))
            continue
        grams = _bigrams(lowered)
        if not grams:
            continue
        overlap = len(grams & haystack_grams) / len(grams)
        if overlap >= threshold:
            candidates.append(TaskCandidate(task_id, name, round(overlap, 2)))
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:limit]


def summarize_title(text: str, max_length: int = 28) -> str:
    """元の語だけを使って課題名を作る（要約であって生成ではない）。"""
    cleaned = _clean_segment(text)
    first = SENTENCE_SPLIT.split(cleaned)[0].strip() if cleaned else ""
    base = first or cleaned
    # 文末の丁寧語だけ落とす。内容語は削らない。
    base = re.sub(r"(?:して)?(?:ください|下さい|お願いします|願います|しています|しております|します|です|ます)$", "", base).strip("　 、。")
    if len(base) <= max_length:
        return base or cleaned[:max_length]
    return base[: max_length - 1] + "…"


def estimate_severity(text: str, label: str) -> str:
    if label != "issue":
        return "不明"
    if any(k in text for k in SEVERITY_HIGH):
        return "高"
    if any(k in text for k in SEVERITY_LOW):
        return "低"
    return "中"


@dataclass
class TriageResult:
    text: str
    label: str
    confidence: float
    title: str
    description: str
    severity_estimate: str
    reasons: list[str] = field(default_factory=list)
    related_task_candidates: list[TaskCandidate] = field(default_factory=list)
    source: str = "rules"


def classify_statement(text: str, tasks: list[tuple[int | None, str]] | None = None) -> TriageResult:
    cleaned = _clean_segment(text)
    not_issue_hits = _not_issue_hits(cleaned)
    issue_hits = _issue_hits(_mask(cleaned, not_issue_hits))
    vague = [m for m in VAGUE_MARKERS if m in cleaned]
    reasons: list[str] = []

    if issue_hits:
        reasons.append("課題を示す語: " + "、".join(issue_hits[:4]))
    if not_issue_hits:
        reasons.append("報告・挨拶を示す語: " + "、".join(not_issue_hits[:3]))
    if vague:
        reasons.append("曖昧な表現: " + "、".join(vague[:3]))

    if not cleaned:
        label, confidence = "not_issue", 0.6
        reasons.append("本文が空")
    elif issue_hits and not not_issue_hits:
        confidence = min(0.92, 0.6 + 0.1 * len(issue_hits))
        if vague:
            confidence -= 0.2
        # 対象が書かれていない短文は「課題っぽいが情報不足」に寄せる
        if len(cleaned) < 10 and len(issue_hits) == 1:
            confidence -= 0.15
            reasons.append("対象や影響範囲が書かれていない")
        label = "issue" if confidence >= 0.65 else "uncertain"
    elif not_issue_hits and not issue_hits:
        label, confidence = "not_issue", min(0.9, 0.65 + 0.08 * len(not_issue_hits))
    elif issue_hits and not_issue_hits:
        # 報告と課題が同じ文にあるとき。課題側の根拠が複数あれば課題として扱い、
        # 1つだけなら人の目で確かめてもらう。
        if len(issue_hits) >= 2:
            label, confidence = "issue", 0.65
            reasons.append("報告と課題が混在しているが、課題側の根拠が複数ある")
        else:
            label, confidence = "uncertain", 0.5
            reasons.append("報告と課題が同じ文に混在している")
    elif vague:
        # 「検討中」「どうなんでしょうか」など、対象も結論も読み取れないもの
        label, confidence = "uncertain", 0.35
        reasons.append("対象や結論が読み取れない")
    elif len(cleaned) < 4:
        label, confidence = "not_issue", 0.6
        reasons.append("本文が短すぎて判断材料がない")
    else:
        label, confidence = "uncertain", 0.4
        reasons.append("課題を示す語も報告を示す語も見つからない")

    confidence = round(max(0.05, min(0.95, confidence)), 2)
    severity = estimate_severity(cleaned, label)
    return TriageResult(
        text=cleaned,
        label=label,
        confidence=confidence,
        title=summarize_title(cleaned) if label != "not_issue" else "",
        description=cleaned if label != "not_issue" else "",
        severity_estimate=severity,
        reasons=reasons,
        related_task_candidates=match_tasks(cleaned, tasks or []),
    )


def triage_rows(
    rows: list[tuple[int, str, str | None]],
    tasks: list[tuple[int | None, str]] | None = None,
) -> list[dict]:
    """(row_index, text, task_hint) の配列を分割・分類する。

    task_hint は取り込み元の行が持つタスク名（あれば関連タスク候補の手がかりにする）。
    """
    out: list[dict] = []
    for row_index, text, task_hint in rows:
        statements = split_statements(text)
        if not statements:
            continue
        for part_index, statement in enumerate(statements):
            result = classify_statement(statement, tasks)
            if task_hint:
                hint_matches = match_tasks(task_hint, tasks or [], limit=1)
                known = {c.title for c in result.related_task_candidates}
                for candidate in hint_matches:
                    if candidate.title not in known:
                        result.related_task_candidates.append(candidate)
            out.append(
                {
                    "row_index": row_index,
                    "part_index": part_index,
                    "source_text": text,
                    "statement": statement,
                    "result": result,
                    "split": len(statements) > 1,
                }
            )
    return out
