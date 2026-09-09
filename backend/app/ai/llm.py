from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..analysis.findings import RawFinding
from ..config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは経験豊富なPMO（Project Management Office）アナリストです。
入力として、Pythonの構造化分析エンジンが算出済みの検知結果（Finding）を受け取ります。

厳守事項:
1. 数値・日付・件数を新たに作り出さないこと。入力に含まれる事実のみを使う。
2. evidence（根拠）は入力のものを前提に説明する。根拠のない断定を書かない。
3. 「危険です」「注意が必要です」のような、根拠のない一般論だけの出力は禁止。
4. recommended_action_index は入力の actions 配列の添字から選ぶこと。新しい打ち手を追加しない。
5. 日本語で、PMがそのまま会議で使える具体的な表現にする。1項目あたり2〜3文。

出力はJSONのみ。"""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "explanation": {"type": "string"},
                    "reasoning_summary": {"type": "string"},
                    "impact": {"type": "string"},
                    "recommended_action_index": {"type": "integer"},
                    "recommended_action_why": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "id",
                    "explanation",
                    "reasoning_summary",
                    "impact",
                    "recommended_action_index",
                    "recommended_action_why",
                    "confidence",
                ],
            },
        }
    },
    "required": ["findings"],
}


CLASSIFY_PROMPT = """あなたはPMOアナリストです。プロジェクトのタスク一覧を、WBSの大分類（カテゴリ）へ分類します。

厳守事項:
1. できる限り candidates に挙がっているカテゴリ名を使う。既存カテゴリ（existing=true）は最優先で再利用する。
2. どうしても当てはまらない場合のみ新しいカテゴリ名を作ってよい。新規は最大2つまで。
3. カテゴリ名は工程・領域を表す短い日本語（例: 要件定義、設計、テスト、移行・リリース）。タスク名をそのまま使わない。
4. 全体のカテゴリ数は8個以内に収める。
5. reason には、そのタスクをそのカテゴリに入れた根拠をタスク名の語を引用して1文で書く。

出力はJSONのみ。"""

CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "task_id": {"type": "integer"},
                    "category": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["task_id", "category", "confidence", "reason"],
            },
        }
    },
    "required": ["assignments"],
}


def classify_tasks(
    tasks: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> tuple[dict[int, dict[str, Any]], bool, str | None]:
    """Ask the LLM to assign a category to each task.

    Returns (assignments by task id, llm_used, note). Falls back silently to an
    empty mapping so the caller can keep the rule based result.
    """
    if not tasks:
        return {}, False, None
    if not settings.llm_available:
        return (
            {},
            False,
            "OPENAI_API_KEY が未設定のため、キーワード辞書によるルールベース分類を使用しています。",
        )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, timeout=60.0)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": CLASSIFY_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"candidates": candidates, "tasks": tasks}, ensure_ascii=False, default=str
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "task_categories", "schema": CLASSIFY_SCHEMA, "strict": True},
            },
            temperature=0.1,
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("LLM classification failed, falling back to rules: %s", exc)
        return {}, False, f"LLM呼び出しに失敗したため、ルールベース分類を表示しています（{type(exc).__name__}）。"

    assignments: dict[int, dict[str, Any]] = {}
    for item in data.get("assignments", []):
        try:
            task_id = int(item["task_id"])
        except (KeyError, TypeError, ValueError):
            continue
        category = str(item.get("category") or "").strip()
        if not category:
            continue
        assignments[task_id] = {
            "category": category[:200],
            "confidence": round(max(0.0, min(1.0, float(item.get("confidence") or 0.6))), 2),
            "reason": str(item.get("reason") or "")[:400],
        }
    return assignments, True, f"model={settings.openai_model}"


TRIAGE_PROMPT = """あなたはPMOアシスタントです。クライアントが書いた雑多な文章から、
対応が必要な「課題」だけを拾い上げ、登録できる形に整えます。

ラベルの定義:
- issue: 対応・意思決定を要する記述（遅れ、エラー、確認依頼、判断待ちなど）
- uncertain: 課題らしいが対象や影響範囲が不明瞭で、人の確認が要るもの
- not_issue: 進捗報告・感想・挨拶など、対応の必要がないもの

厳守事項:
1. 元の文章に無い情報を足さない。原因・影響・担当を推測して書かない。
2. title は元の文章の語を使って20〜30文字に要約する。新しい固有名詞を作らない。
3. description は元の文章を読みやすく整えるだけ。事実を変えない。
4. related_task_candidates は与えられた existing_tasks の名前からのみ選ぶ。
   関連が薄ければ空配列にする。無関係なタスクを挙げない。
5. severity_estimate は 高 / 中 / 低 のいずれか。判断材料が弱ければ 不明 とする。
6. 迷ったら issue ではなく uncertain にする。取りこぼしより誤登録を避ける。
7. 1つの入力に複数の課題が含まれる場合は、items を複数返して分割する。
   分割できないときは1件のままでよい。

出力はJSONのみ。"""

TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string", "enum": ["issue", "uncertain", "not_issue"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity_estimate": {"type": "string", "enum": ["高", "中", "低", "不明"]},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                    "related_task_titles": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "id", "label", "title", "description",
                    "severity_estimate", "confidence", "reason", "related_task_titles",
                ],
            },
        }
    },
    "required": ["items"],
}


def triage_statements(
    statements: list[dict[str, Any]], existing_tasks: list[str]
) -> tuple[dict[str, list[dict[str, Any]]], bool, str | None]:
    """自由記述の分類・整形をLLMに任せる。

    戻り値は (入力id -> 出力items, llm_used, note)。失敗時は空dictを返し、
    呼び出し側はルールベースの結果をそのまま使う。
    """
    if not statements:
        return {}, False, None
    if not settings.llm_available:
        return (
            {},
            False,
            "OPENAI_API_KEY が未設定のため、キーワード辞書によるルールベース判定を使用しています。",
        )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, timeout=90.0)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": TRIAGE_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"existing_tasks": existing_tasks[:200], "inputs": statements},
                        ensure_ascii=False,
                        default=str,
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "issue_triage", "schema": TRIAGE_SCHEMA, "strict": True},
            },
            temperature=0.1,
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("LLM triage failed, falling back to rules: %s", exc)
        return {}, False, f"LLM呼び出しに失敗したため、ルールベース判定を表示しています（{type(exc).__name__}）。"

    allowed = {t for t in existing_tasks}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in data.get("items", []):
        key = str(item.get("id") or "")
        if not key:
            continue
        label = item.get("label")
        if label not in ("issue", "uncertain", "not_issue"):
            continue
        grouped.setdefault(key, []).append(
            {
                "label": label,
                "title": str(item.get("title") or "")[:300],
                "description": str(item.get("description") or "")[:4000],
                "severity_estimate": item.get("severity_estimate") or "不明",
                "confidence": round(max(0.0, min(1.0, float(item.get("confidence") or 0.5))), 2),
                "reason": str(item.get("reason") or "")[:400],
                # 実在するタスク名しか通さない
                "related_task_titles": [t for t in item.get("related_task_titles", []) if t in allowed],
            }
        )
    return grouped, True, f"model={settings.openai_model}"


@dataclass
class LLMResult:
    findings: list[RawFinding]
    llm_used: bool
    note: str | None = None


def _serialise(finding: RawFinding, index: int) -> dict[str, Any]:
    return {
        "id": f"f{index}",
        "category": finding.category,
        "finding_type": finding.finding_type,
        "title": finding.title,
        "severity": finding.severity,
        "risk_score": finding.risk_score,
        "task": finding.task_title,
        "person": finding.person_name,
        "cause_category": finding.cause_category,
        "cause_hypothesis": finding.cause_hypothesis,
        "evidence": [{"label": e.label, "detail": e.detail} for e in finding.evidence],
        "baseline_impact": finding.impact,
        "actions": [
            {"index": i, "action": a.action, "why": a.why, "effort": a.effort}
            for i, a in enumerate(finding.actions)
        ],
    }


def enrich_findings(
    findings: list[RawFinding], project_context: dict[str, Any] | None = None
) -> LLMResult:
    """Have the LLM narrate the findings. Falls back to the rule based text."""
    if not findings:
        return LLMResult(findings=findings, llm_used=False, note=None)

    if not settings.llm_available:
        return LLMResult(
            findings=findings,
            llm_used=False,
            note="OPENAI_API_KEY が未設定のため、ルールベースの推論エンジンで説明文を生成しています。",
        )

    try:
        from openai import OpenAI  # imported lazily so the app runs without the SDK

        client = OpenAI(api_key=settings.openai_api_key, timeout=45.0)
        payload = {
            "project": project_context or {},
            "findings": [_serialise(f, i) for i, f in enumerate(findings)],
        }
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "pmo_findings", "schema": RESPONSE_SCHEMA, "strict": True},
            },
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("LLM enrichment failed, falling back to rules: %s", exc)
        return LLMResult(
            findings=findings,
            llm_used=False,
            note=f"LLM呼び出しに失敗したため、ルールベースの説明を表示しています（{type(exc).__name__}）。",
        )

    by_id = {f"f{i}": f for i, f in enumerate(findings)}
    for item in data.get("findings", []):
        finding = by_id.get(str(item.get("id")))
        if finding is None:
            continue
        # Only narrative fields are overwritten; evidence and scores are ours.
        if item.get("explanation"):
            finding.explanation = str(item["explanation"])
        if item.get("reasoning_summary"):
            finding.reasoning_summary = str(item["reasoning_summary"])
        if item.get("impact"):
            finding.impact = str(item["impact"])
        idx = item.get("recommended_action_index")
        if isinstance(idx, int) and 0 <= idx < len(finding.actions):
            finding.recommended_action = finding.actions[idx].action
            finding.recommended_action_why = (
                str(item.get("recommended_action_why")) or finding.actions[idx].why
            )
        confidence = item.get("confidence")
        if isinstance(confidence, (int, float)):
            finding.confidence = round(max(0.0, min(1.0, float(confidence))), 2)
        finding.source = "llm"

    return LLMResult(findings=findings, llm_used=True, note=f"model={settings.openai_model}")
