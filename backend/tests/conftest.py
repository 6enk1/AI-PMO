"""Test fixtures: an isolated SQLite file and a TestClient per test."""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

import pytest

_TMP = tempfile.mkdtemp(prefix="ai-pmo-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["UPLOAD_DIR"] = f"{_TMP}/uploads"
os.environ["LLM_ENABLED"] = "off"
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Issue, Milestone, Person, Project, Task, TaskDependency  # noqa: E402

TODAY = date.today()


@pytest.fixture(autouse=True)
def _fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> TestClient:
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


@pytest.fixture
def project(db: Session) -> Project:
    project = Project(name="テストPJ", start_date=day(-30), end_date=day(60))
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@pytest.fixture
def factory(db: Session, project: Project):
    class Factory:
        project_id = project.id

        def person(self, name: str, **kwargs) -> Person:
            person = Person(project_id=project.id, name=name, **kwargs)
            db.add(person)
            db.commit()
            db.refresh(person)
            return person

        def task(self, title: str, **kwargs) -> Task:
            task = Task(project_id=project.id, title=title, **kwargs)
            db.add(task)
            db.commit()
            db.refresh(task)
            return task

        def dependency(self, predecessor: Task, successor: Task, dependency_type: str = "FS") -> TaskDependency:
            link = TaskDependency(
                predecessor_task_id=predecessor.id,
                successor_task_id=successor.id,
                dependency_type=dependency_type,
            )
            db.add(link)
            db.commit()
            return link

        def issue(self, title: str, **kwargs) -> Issue:
            issue = Issue(project_id=project.id, title=title, **kwargs)
            db.add(issue)
            db.commit()
            db.refresh(issue)
            return issue

        def milestone(self, title: str, **kwargs) -> Milestone:
            milestone = Milestone(project_id=project.id, title=title, **kwargs)
            db.add(milestone)
            db.commit()
            db.refresh(milestone)
            return milestone

    return Factory()
