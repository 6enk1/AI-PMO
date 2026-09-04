from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, services
from ..analysis.snapshot import ProjectSnapshot
from ..database import get_db
from ..models import Person, Project
from .deps import get_project, get_snapshot

router = APIRouter(tags=["people"])


@router.get("/api/projects/{project_id}/people", response_model=list[schemas.PersonWorkload])
def list_people(snapshot: ProjectSnapshot = Depends(get_snapshot)) -> list[schemas.PersonWorkload]:
    people = sorted(
        snapshot.loads.values(),
        key=lambda load: (len(load.overdue_task_ids), len(load.open_task_ids)),
        reverse=True,
    )
    return [services.person_workload(load.person.id, snapshot) for load in people]


@router.post("/api/projects/{project_id}/people", response_model=schemas.PersonRead, status_code=201)
def create_person(
    payload: schemas.PersonCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> Person:
    existing = db.scalar(
        select(Person).where(Person.project_id == project.id, Person.name == payload.name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名の担当者が既に登録されています")
    person = Person(project_id=project.id, **payload.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.patch("/api/people/{person_id}", response_model=schemas.PersonRead)
def update_person(person_id: int, payload: schemas.PersonUpdate, db: Session = Depends(get_db)) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(person, key, value)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/api/people/{person_id}", status_code=204, response_model=None)
def delete_person(person_id: int, db: Session = Depends(get_db)) -> None:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    db.delete(person)
    db.commit()
