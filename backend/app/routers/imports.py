from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..importer import excel

router = APIRouter(prefix="/api/imports", tags=["import"])

ALLOWED_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".csv")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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


@router.post("/commit", response_model=schemas.ImportCommitResponse)
def commit(payload: schemas.ImportCommitRequest, db: Session = Depends(get_db)) -> schemas.ImportCommitResponse:
    try:
        return schemas.ImportCommitResponse(**excel.commit_import(db, payload))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
