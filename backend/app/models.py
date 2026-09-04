"""SQLAlchemy models for the AI PMO domain.

The model layer deliberately keeps Task and Issue as separate first class
objects: a Task is planned work, an Issue is a problem that threatens work.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

TASK_STATUSES = ("not_started", "in_progress", "blocked", "done", "cancelled")
TASK_PRIORITIES = ("low", "medium", "high", "critical")
ISSUE_STATUSES = ("open", "in_progress", "resolved", "closed")
SEVERITIES = ("low", "medium", "high", "critical")
MILESTONE_STATUSES = ("pending", "achieved", "missed")
DEPENDENCY_TYPES = ("FS", "SS", "FF", "SF")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    people: Mapped[list["Person"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    issues: Mapped[list["Issue"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Person(Base, TimestampMixin):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(200))
    capacity_tasks: Mapped[int] = mapped_column(Integer, default=8)

    project: Mapped[Project] = relationship(back_populates="people")
    tasks: Mapped[list["Task"]] = relationship(back_populates="owner")

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_person_project_name"),)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str | None] = mapped_column(String(40), index=True)
    parent_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    estimated_hours: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="tasks")
    owner: Mapped[Person | None] = relationship(back_populates="tasks")
    parent: Mapped["Task | None"] = relationship(remote_side="Task.id", back_populates="children")
    children: Mapped[list["Task"]] = relationship(back_populates="parent")
    issues: Mapped[list["Issue"]] = relationship(back_populates="task")

    # Dependencies where this task is the successor (i.e. what it waits for).
    predecessor_links: Mapped[list["TaskDependency"]] = relationship(
        back_populates="successor",
        foreign_keys="TaskDependency.successor_task_id",
        cascade="all, delete-orphan",
    )
    successor_links: Mapped[list["TaskDependency"]] = relationship(
        back_populates="predecessor",
        foreign_keys="TaskDependency.predecessor_task_id",
        cascade="all, delete-orphan",
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    predecessor_task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    successor_task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    dependency_type: Mapped[str] = mapped_column(String(4), default="FS")
    lag_days: Mapped[int] = mapped_column(Integer, default=0)

    predecessor: Mapped[Task] = relationship(
        foreign_keys=[predecessor_task_id], back_populates="successor_links"
    )
    successor: Mapped[Task] = relationship(
        foreign_keys=[successor_task_id], back_populates="predecessor_links"
    )

    __table_args__ = (
        UniqueConstraint("predecessor_task_id", "successor_task_id", name="uq_dependency_pair"),
    )


class Issue(Base, TimestampMixin):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str | None] = mapped_column(String(40), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    raised_on: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open")
    action_plan: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="issues")
    task: Mapped[Task | None] = relationship(back_populates="issues")
    owner: Mapped[Person | None] = relationship()


class Milestone(Base, TimestampMixin):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")

    project: Mapped[Project] = relationship(back_populates="milestones")


class AIRiskFinding(Base):
    """Persisted output of an AI PMO analysis run.

    Findings are stored so that a PM can see what was flagged and when, and so
    that later phases can diff "what changed since yesterday".
    """

    __tablename__ = "ai_risk_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(30))  # hidden_issue | delay_risk | delay_action
    finding_type: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    risk_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(300))
    explanation: Mapped[str | None] = mapped_column(Text)
    reasoning_summary: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)  # JSON encoded list[str]
    impact: Mapped[str | None] = mapped_column(Text)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    suggested_actions: Mapped[str | None] = mapped_column(Text)  # JSON encoded list
    recommended_reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="rules")  # rules | llm
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
