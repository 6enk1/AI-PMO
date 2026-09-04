from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, services
from ..analysis.snapshot import ProjectSnapshot, build_snapshot
from ..database import get_db
from ..models import Issue, Project
from .deps import get_project, get_snapshot

router = APIRouter(tags=["issues"])

SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _next_code(db: Session, project_id: int) -> str:
    count = len(list(db.scalars(select(Issue.id).where(Issue.project_id == project_id))))
    return f"I-{count + 1:03d}"


@router.get("/api/projects/{project_id}/issues", response_model=list[schemas.IssueRead])
def list_issues(
    snapshot: ProjectSnapshot = Depends(get_snapshot),
    status: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    owner_id: int | None = None,
    task_id: int | None = None,
    open_only: bool = False,
    q: str | None = None,
    sort: str = "severity",
    order: str = "desc",
) -> list[schemas.IssueRead]:
    issues = list(snapshot.issues)
    if status:
        issues = [i for i in issues if i.status in status]
    if severity:
        issues = [i for i in issues if i.severity in severity]
    if owner_id is not None:
        issues = [i for i in issues if i.owner_id == owner_id]
    if task_id is not None:
        issues = [i for i in issues if i.task_id == task_id]
    if open_only:
        issues = [i for i in issues if i.status not in ("resolved", "closed")]
    if q:
        needle = q.lower()
        issues = [i for i in issues if needle in i.title.lower() or needle in (i.description or "").lower()]

    keys = {
        "severity": lambda i: SEVERITY_ORDER.get(i.severity, 1),
        "due_date": lambda i: (i.due_date is None, i.due_date or snapshot.today),
        "status": lambda i: i.status,
        "title": lambda i: i.title,
        "created_at": lambda i: i.created_at,
    }
    issues.sort(key=keys.get(sort, keys["severity"]), reverse=(order == "desc"))
    return [services.issue_to_read(i, snapshot) for i in issues]


@router.post("/api/projects/{project_id}/issues", response_model=schemas.IssueRead, status_code=201)
def create_issue(
    payload: schemas.IssueCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> schemas.IssueRead:
    data = payload.model_dump()
    if not data.get("code"):
        data["code"] = _next_code(db, project.id)
    issue = Issue(project_id=project.id, **data)
    db.add(issue)
    db.commit()
    db.refresh(issue)
    snapshot = build_snapshot(db, project.id)
    return services.issue_to_read(issue, snapshot)


@router.get("/api/issues/{issue_id}", response_model=schemas.IssueRead)
def read_issue(issue_id: int, db: Session = Depends(get_db)) -> schemas.IssueRead:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return services.issue_to_read(issue, build_snapshot(db, issue.project_id))


@router.patch("/api/issues/{issue_id}", response_model=schemas.IssueRead)
def update_issue(issue_id: int, payload: schemas.IssueUpdate, db: Session = Depends(get_db)) -> schemas.IssueRead:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(issue, key, value)
    db.commit()
    db.refresh(issue)
    return services.issue_to_read(issue, build_snapshot(db, issue.project_id))


@router.delete("/api/issues/{issue_id}", status_code=204, response_model=None)
def delete_issue(issue_id: int, db: Session = Depends(get_db)) -> None:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    db.delete(issue)
    db.commit()
