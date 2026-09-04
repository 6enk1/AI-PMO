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
