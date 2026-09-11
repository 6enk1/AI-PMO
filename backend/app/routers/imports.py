from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..importer import excel
from ..importer.template import template_bytes
from ..importer.wbs_template import wbs_template_bytes

router = APIRouter(prefix="/api/imports", tags=["import"])

ALLOWED_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".csv")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/template")
def download_template(
    kind: str = Query("issues", pattern="^(issues|wbs)$"),
) -> Response:
    """クライアントに配る記入用テンプレート（記入例・入力規則つき）。

    ``kind=issues`` が課題リスト、``kind=wbs`` がWBS（カテゴリのゴールつき）。
    """
    if kind == "wbs":
        content, filename = wbs_template_bytes(), "wbs_template.xlsx"
    else:
        content, filename = template_bytes(), "issue_list_template.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/analyze", response_model=schemas.ImportAnalyzeResponse)
async def analyze(file: UploadFile = File(...)) -> schemas.ImportAnalyzeResponse:
    """Upload a WBS and get sheets, detected header row and a column mapping."""
    filename = file.filename or "upload.xlsx"
    if not filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(status_code=400, detail="対応形式は .xlsx / .xlsm / .xls / .csv です")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="ファイルが空です")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="ファイルサイズが大きすぎます（上限20MB）")
    token = excel.store_upload(filename, content)
    try:
        return schemas.ImportAnalyzeResponse(**excel.analyze_upload(token))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"ファイルを解析できませんでした: {exc}") from exc


@router.get("/{token}/preview", response_model=schemas.ImportAnalyzeResponse)
def preview(
    token: str,
    sheet: str | None = Query(default=None),
    header_row: int | None = Query(default=None, ge=0),
) -> schemas.ImportAnalyzeResponse:
    """Re-analyze an already uploaded file with a different sheet / header row."""
    try:
        return schemas.ImportAnalyzeResponse(**excel.analyze_upload(token, sheet, header_row))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"ファイルを解析できませんでした: {exc}") from exc


@router.post("/plan", response_model=schemas.ImportPlanResponse)
def plan(payload: schemas.ImportCommitRequest, db: Session = Depends(get_db)) -> schemas.ImportPlanResponse:
    """取り込み前の差分確認（更新/追加/変更なしの件数と変更内容）。"""
    try:
        return schemas.ImportPlanResponse(**excel.plan_import(db, payload))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/issue-rows", response_model=schemas.ImportIssueRowsResponse)
def issue_rows(payload: schemas.ImportIssueRowsRequest) -> schemas.ImportIssueRowsResponse:
    """課題列の自由記述を全行取り出す（/api/issues/analyze への入力用）。"""
    try:
        return schemas.ImportIssueRowsResponse(**excel.issue_rows(payload))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/commit", response_model=schemas.ImportCommitResponse)
def commit(payload: schemas.ImportCommitRequest, db: Session = Depends(get_db)) -> schemas.ImportCommitResponse:
    try:
        return schemas.ImportCommitResponse(**excel.commit_import(db, payload))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
