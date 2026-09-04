from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, services
from ..analysis.snapshot import ProjectSnapshot, build_snapshot
from ..database import get_db
from ..models import Person, Project, Task, TaskDependency
from .deps import get_project, get_snapshot

router = APIRouter(tags=["tasks"])

SORT_KEYS = {
    "planned_end": lambda v: (v.planned_end is None, v.planned_end or date.max),
    "planned_start": lambda v: (v.planned_start is None, v.planned_start or date.max),
    "risk_score": lambda v: v.risk_score,
    "progress": lambda v: v.progress,
    "title": lambda v: v.title,
    "status": lambda v: v.status,
    "priority": lambda v: {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(v.priority, 1),
    "owner": lambda v: (v.owner_id is None, v.owner_id or 0),
    "code": lambda v: v.code or "",
    "days_overdue": lambda v: v.days_overdue,
}


def _next_code(db: Session, project_id: int) -> str:
    count = len(list(db.scalars(select(Task.id).where(Task.project_id == project_id))))
    return f"T-{count + 1:03d}"


def _sync_predecessors(db: Session, task: Task, predecessor_ids: list[int]) -> None:
    existing = list(
        db.scalars(select(TaskDependency).where(TaskDependency.successor_task_id == task.id))
    )
    wanted = {pid for pid in predecessor_ids if pid != task.id}
    for link in existing:
        if link.predecessor_task_id not in wanted:
            db.delete(link)
    current = {link.predecessor_task_id for link in existing}
    for pid in wanted - current:
        predecessor = db.get(Task, pid)
        if predecessor is None or predecessor.project_id != task.project_id:
            raise HTTPException(status_code=400, detail=f"依存タスク {pid} が同一プロジェクトに存在しません")
        db.add(TaskDependency(predecessor_task_id=pid, successor_task_id=task.id, dependency_type="FS"))


@router.get("/api/projects/{project_id}/tasks", response_model=list[schemas.TaskRead])
def list_tasks(
    snapshot: ProjectSnapshot = Depends(get_snapshot),
    status: list[str] | None = Query(default=None),
    priority: list[str] | None = Query(default=None),
    owner_id: int | None = None,
    unassigned: bool = False,
    overdue: bool = False,
    risk_min: float | None = None,
    q: str | None = None,
    parent_task_id: int | None = None,
    sort: str = "planned_end",
    order: str = "asc",
) -> list[schemas.TaskRead]:
    views = snapshot.task_views()
    if status:
        views = [v for v in views if v.status in status]
    if priority:
        views = [v for v in views if v.priority in priority]
    if owner_id is not None:
        views = [v for v in views if v.owner_id == owner_id]
    if unassigned:
        views = [v for v in views if v.owner_id is None]
    if overdue:
        views = [v for v in views if v.is_overdue]
    if risk_min is not None:
        views = [v for v in views if v.risk_score >= risk_min]
    if parent_task_id is not None:
        views = [v for v in views if v.task.parent_task_id == parent_task_id]
    if q:
        needle = q.lower()
        views = [
            v
            for v in views
            if needle in v.title.lower()
            or needle in (v.code or "").lower()
            or needle in (v.task.description or "").lower()
            or needle in (v.task.notes or "").lower()
        ]
    key = SORT_KEYS.get(sort, SORT_KEYS["planned_end"])
    views.sort(key=key, reverse=(order == "desc"))
    return [services.task_to_read(v, snapshot) for v in views]


@router.post("/api/projects/{project_id}/tasks", response_model=schemas.TaskRead, status_code=201)
def create_task(
    payload: schemas.TaskCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> schemas.TaskRead:
    data = payload.model_dump(exclude={"predecessor_task_ids"})
    if not data.get("code"):
        data["code"] = _next_code(db, project.id)
    if data.get("owner_id") is not None:
        owner = db.get(Person, data["owner_id"])
        if owner is None or owner.project_id != project.id:
            raise HTTPException(status_code=400, detail="担当者が同一プロジェクトに存在しません")
    task = Task(project_id=project.id, **data)
    db.add(task)
    db.flush()
    _sync_predecessors(db, task, payload.predecessor_task_ids)
    db.commit()
    snapshot = build_snapshot(db, project.id)
    return services.task_to_read(snapshot.views[task.id], snapshot)


@router.get("/api/tasks/{task_id}", response_model=schemas.TaskRead)
def read_task(task_id: int, db: Session = Depends(get_db)) -> schemas.TaskRead:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    snapshot = build_snapshot(db, task.project_id)
    return services.task_to_read(snapshot.views[task.id], snapshot)


@router.patch("/api/tasks/{task_id}", response_model=schemas.TaskRead)
def update_task(task_id: int, payload: schemas.TaskUpdate, db: Session = Depends(get_db)) -> schemas.TaskRead:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    data = payload.model_dump(exclude_unset=True)
    predecessors = data.pop("predecessor_task_ids", None)
    if data.get("parent_task_id") == task.id:
        raise HTTPException(status_code=400, detail="自分自身を親タスクにはできません")
    if data.get("owner_id") is not None:
        owner = db.get(Person, data["owner_id"])
        if owner is None or owner.project_id != task.project_id:
            raise HTTPException(status_code=400, detail="担当者が同一プロジェクトに存在しません")
    for key, value in data.items():
        setattr(task, key, value)
    # Keep status and progress consistent with each other.
    if data.get("status") == "done" and (task.progress or 0) < 100:
        task.progress = 100.0
    if data.get("status") == "done" and task.actual_end is None:
        task.actual_end = date.today()
    if predecessors is not None:
        _sync_predecessors(db, task, predecessors)
    db.commit()
    snapshot = build_snapshot(db, task.project_id)
    return services.task_to_read(snapshot.views[task.id], snapshot)


@router.delete("/api/tasks/{task_id}", status_code=204, response_model=None)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()


@router.get("/api/projects/{project_id}/dependencies", response_model=list[schemas.DependencyRead])
def list_dependencies(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    task_ids = [t.id for t in db.scalars(select(Task).where(Task.project_id == project.id))]
    if not task_ids:
        return []
    return list(
        db.scalars(select(TaskDependency).where(TaskDependency.successor_task_id.in_(task_ids)))
    )


@router.post("/api/projects/{project_id}/dependencies", response_model=schemas.DependencyRead, status_code=201)
def create_dependency(
    payload: schemas.DependencyCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> TaskDependency:
    if payload.predecessor_task_id == payload.successor_task_id:
        raise HTTPException(status_code=400, detail="同一タスク間の依存は設定できません")
    for task_id in (payload.predecessor_task_id, payload.successor_task_id):
        task = db.get(Task, task_id)
        if task is None or task.project_id != project.id:
            raise HTTPException(status_code=400, detail=f"Task {task_id} がプロジェクト内に存在しません")
    existing = db.scalar(
        select(TaskDependency).where(
            TaskDependency.predecessor_task_id == payload.predecessor_task_id,
            TaskDependency.successor_task_id == payload.successor_task_id,
        )
    )
    if existing:
        return existing
    dependency = TaskDependency(**payload.model_dump())
    db.add(dependency)
    db.commit()
    db.refresh(dependency)
    return dependency


@router.delete("/api/dependencies/{dependency_id}", status_code=204, response_model=None)
def delete_dependency(dependency_id: int, db: Session = Depends(get_db)) -> None:
    dependency = db.get(TaskDependency, dependency_id)
    if dependency is None:
        raise HTTPException(status_code=404, detail="Dependency not found")
    db.delete(dependency)
    db.commit()
