"""Shared FastAPI dependencies."""
from __future__ import annotations

from datetime import date

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..analysis.snapshot import ProjectSnapshot, build_snapshot
from ..database import get_db
from ..models import Project


def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def get_snapshot(
    project_id: int,
    db: Session = Depends(get_db),
    as_of: date | None = Query(default=None, description="分析基準日（既定: 本日）"),
) -> ProjectSnapshot:
    try:
        return build_snapshot(db, project_id, today=as_of)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
