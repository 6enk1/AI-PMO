from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, services
from ..analysis.snapshot import ProjectSnapshot, build_snapshot
from ..database import get_db
from ..models import Issue, Project, Task
from .deps import get_project, get_snapshot

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[schemas.ProjectSummary])
def list_projects(db: Session = Depends(get_db)) -> list[schemas.ProjectSummary]:
    projects = list(db.scalars(select(Project).order_by(Project.created_at.desc())))
    out: list[schemas.ProjectSummary] = []
    for project in projects:
        snapshot = build_snapshot(db, project.id)
        summary = schemas.ProjectSummary.model_validate(project)
        summary.task_count = len(snapshot.views)
        summary.open_task_count = len(snapshot.active_views())
        summary.overdue_task_count = len(snapshot.overdue_views())
        summary.open_issue_count = len(snapshot.open_issues())
        out.append(summary)
    return out


@router.post("", response_model=schemas.ProjectRead, status_code=201)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=schemas.ProjectRead)
def read_project(project: Project = Depends(get_project)) -> Project:
    return project


@router.patch("/{project_id}", response_model=schemas.ProjectRead)
def update_project(
    payload: schemas.ProjectUpdate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> Project:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204, response_model=None)
def delete_project(project: Project = Depends(get_project), db: Session = Depends(get_db)) -> None:
    db.delete(project)
    db.commit()


@router.get("/{project_id}/dashboard", response_model=schemas.DashboardResponse)
def dashboard(snapshot: ProjectSnapshot = Depends(get_snapshot)) -> schemas.DashboardResponse:
    return services.build_dashboard(snapshot)


@router.get("/{project_id}/milestones", response_model=list[schemas.MilestoneRead])
def list_milestones(snapshot: ProjectSnapshot = Depends(get_snapshot)) -> list[schemas.MilestoneRead]:
    ordered = sorted(snapshot.milestones, key=lambda m: (m.due_date is None, m.due_date))
    return [services.milestone_to_read(m, snapshot) for m in ordered]


@router.post("/{project_id}/milestones", response_model=schemas.MilestoneRead, status_code=201)
def create_milestone(
    payload: schemas.MilestoneCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> schemas.MilestoneRead:
    from ..models import Milestone

    milestone = Milestone(project_id=project.id, **payload.model_dump())
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return services.milestone_to_read(milestone)


@router.patch("/{project_id}/milestones/{milestone_id}", response_model=schemas.MilestoneRead)
def update_milestone(
    milestone_id: int,
    payload: schemas.MilestoneUpdate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> schemas.MilestoneRead:
    from ..models import Milestone

    milestone = db.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id != project.id:
        raise HTTPException(status_code=404, detail="Milestone not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(milestone, key, value)
    db.commit()
    db.refresh(milestone)
    return services.milestone_to_read(milestone)


@router.delete("/{project_id}/milestones/{milestone_id}", status_code=204, response_model=None)
def delete_milestone(
    milestone_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> None:
    from ..models import Milestone

    milestone = db.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id != project.id:
        raise HTTPException(status_code=404, detail="Milestone not found")
    db.delete(milestone)
    db.commit()


@router.get("/{project_id}/stats")
def project_stats(snapshot: ProjectSnapshot = Depends(get_snapshot), db: Session = Depends(get_db)) -> dict:
    """Lightweight counters for the project switcher."""
    return {
        "tasks": db.scalar(select(Task.id).where(Task.project_id == snapshot.project.id)) is not None,
        "task_count": len(snapshot.views),
        "issue_count": db.query(Issue).filter(Issue.project_id == snapshot.project.id).count(),
    }
