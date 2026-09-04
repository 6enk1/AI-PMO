from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import schemas, services
from ..analysis.risk import top_risks
from ..analysis.snapshot import ProjectSnapshot
from ..config import settings
from ..database import get_db
from .deps import get_snapshot

router = APIRouter(prefix="/api/projects/{project_id}", tags=["ai-pmo"])


@router.get("/ai-pmo", response_model=schemas.AIPMOResponse)
def ai_pmo(
    snapshot: ProjectSnapshot = Depends(get_snapshot),
    use_llm: bool = Query(default=True, description="LLMによる説明生成を使うか（未設定時は自動でルールベース）"),
    risk_threshold: float = Query(default=40.0, ge=0, le=100),
    db=Depends(get_db),
) -> schemas.AIPMOResponse:
    """Structured Analysis -> LLM Reasoning -> Recommendation."""
    return services.build_ai_pmo(db, snapshot, use_llm=use_llm, risk_threshold=risk_threshold)


@router.get("/risks", response_model=list[schemas.TaskRisk])
def risks(
    snapshot: ProjectSnapshot = Depends(get_snapshot),
    threshold: float = Query(default=40.0, ge=0, le=100),
    limit: int = Query(default=30, ge=1, le=200),
) -> list[schemas.TaskRisk]:
    return [services.task_risk(v, snapshot) for v in top_risks(snapshot, threshold=threshold, limit=limit)]


@router.get("/hidden-issues", response_model=list[schemas.Finding])
def hidden_issues(snapshot: ProjectSnapshot = Depends(get_snapshot)) -> list[schemas.Finding]:
    from ..analysis.hidden_issues import detect_hidden_issues

    findings = services._default_explanations(detect_hidden_issues(snapshot))
    return [services.finding_to_schema(f, i, snapshot) for i, f in enumerate(findings)]


@router.get("/llm-status")
def llm_status() -> dict:
    return {
        "llm_available": settings.llm_available,
        "model": settings.openai_model if settings.llm_available else None,
        "note": (
            "OPENAI_API_KEY が設定されているためLLM推論を使用します。"
            if settings.llm_available
            else "OPENAI_API_KEY 未設定。ルールベース推論で動作します（機能は全て利用可能）。"
        ),
    }
