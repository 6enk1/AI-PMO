"""Demo data so a fresh install has something meaningful to look at.

Run with:  python -m app.seed
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal, init_db
from .models import Issue, Milestone, Person, Project, Task, TaskDependency

DEMO_PROJECT_NAME = "基幹システム刷新 PJ (デモ)"


def seed_demo_project(db: Session, today: date | None = None) -> Project:
    today = today or date.today()

    def d(offset: int) -> date:
        return today + timedelta(days=offset)

    project = Project(
        name=DEMO_PROJECT_NAME,
        description="AI PMO の機能を確認するためのデモプロジェクト。意図的に遅延・課題を含んでいます。",
        start_date=d(-60),
        end_date=d(60),
    )
    db.add(project)
    db.flush()

    people = {
        "sato": Person(project_id=project.id, name="佐藤 健一", role="PM", capacity_tasks=6),
        "tanaka": Person(project_id=project.id, name="田中 美咲", role="開発リード", capacity_tasks=4),
        "suzuki": Person(project_id=project.id, name="鈴木 大輔", role="アーキテクト", capacity_tasks=5),
        "takahashi": Person(project_id=project.id, name="高橋 由紀", role="QAリード", capacity_tasks=5),
    }
    db.add_all(people.values())
    db.flush()

    def task(code, title, **kwargs) -> Task:
        t = Task(project_id=project.id, code=code, title=title, **kwargs)
        db.add(t)
        return t

    phase1 = task("P-1", "フェーズ1: 要件・設計", status="in_progress", progress=80, priority="high")
    phase2 = task("P-2", "フェーズ2: 開発", status="in_progress", progress=25, priority="high")
    phase3 = task("P-3", "フェーズ3: テスト・移行", status="not_started", progress=0, priority="medium")
    db.flush()

    t1 = task(
        "T-001", "要件定義", parent_task_id=phase1.id, owner_id=people["sato"].id,
        planned_start=d(-60), planned_end=d(-40), actual_start=d(-60), actual_end=d(-38),
        progress=100, status="done", priority="high",
    )
    t2 = task(
        "T-002", "API仕様確定", parent_task_id=phase1.id, owner_id=people["sato"].id,
        planned_start=d(-20), planned_end=d(-4), actual_start=d(-20),
        progress=60, status="in_progress", priority="critical",
        notes="顧客からの回答待ちが続いている",
    )
    t3 = task(
        "T-005", "DB設計", parent_task_id=phase1.id, owner_id=people["suzuki"].id,
        planned_start=d(-18), planned_end=d(-6), actual_start=d(-18),
        progress=95, status="in_progress", priority="high",
    )
    t4 = task(
        "T-003", "バックエンド実装", parent_task_id=phase2.id, owner_id=people["tanaka"].id,
        planned_start=d(-2), planned_end=d(12), progress=0, status="not_started", priority="high",
    )
    t5 = task(
        "T-004", "フロントエンド実装", parent_task_id=phase2.id, owner_id=people["tanaka"].id,
        planned_start=d(0), planned_end=d(14), actual_start=d(0), progress=20,
        status="in_progress", priority="high",
    )
    t6 = task(
        "T-007", "移行設計", parent_task_id=phase2.id, owner_id=people["tanaka"].id,
        planned_start=d(-5), planned_end=d(2), actual_start=d(-5), progress=30,
        status="in_progress", priority="medium",
    )
    t7 = task(
        "T-010", "セキュリティ検証", parent_task_id=phase2.id, owner_id=people["tanaka"].id,
        planned_start=d(-10), planned_end=d(1), actual_start=d(-8), progress=10,
        status="in_progress", priority="critical",
        description="脆弱性診断ツールの実行環境構築で技術課題が発生している",
    )
    t8 = task(
        "T-006", "テスト計画", parent_task_id=phase3.id, planned_start=d(3), planned_end=d(10),
        progress=0, status="not_started", priority="medium",
    )
    t9 = task(
        "T-008", "総合テスト", parent_task_id=phase3.id, owner_id=people["takahashi"].id,
        planned_start=d(15), planned_end=d(30), progress=0, status="not_started", priority="high",
    )
    t10 = task(
        "T-009", "ユーザー教育", parent_task_id=phase3.id, owner_id=people["takahashi"].id,
        planned_start=d(25), planned_end=d(32), progress=0, status="not_started", priority="low",
    )
    db.flush()

    for predecessor, successor in (
        (t1, t2), (t1, t3), (t2, t4), (t2, t5), (t3, t4), (t4, t9), (t5, t9), (t8, t9), (t9, t10)
    ):
        db.add(
            TaskDependency(
                predecessor_task_id=predecessor.id, successor_task_id=successor.id, dependency_type="FS"
            )
        )

    db.add_all(
        [
            Issue(
                project_id=project.id, code="I-001", task_id=t2.id,
                title="顧客からのAPI仕様回答待ち",
                description="外部連携APIの認証方式について顧客の回答が届いていない。",
                severity="high", owner_id=people["sato"].id, raised_on=d(-12), due_date=d(-2),
                status="open", action_plan="週次定例で再依頼",
            ),
            Issue(
                project_id=project.id, code="I-002", task_id=t5.id,
                title="性能要件が未確定",
                description="同時接続数の目標値が決まっておらず、画面設計の判断ができない。",
                severity="medium", raised_on=d(-8), due_date=d(5), status="open",
            ),
            Issue(
                project_id=project.id, code="I-003", task_id=t6.id,
                title="移行元データに不整合",
                description="旧システムのマスタに重複レコードが存在する。",
                severity="high", owner_id=people["tanaka"].id, raised_on=d(-6), due_date=d(3), status="in_progress",
            ),
            Issue(
                project_id=project.id, code="I-004", task_id=t7.id,
                title="診断ツールの技術検証が失敗",
                description="検証環境でツールが起動せず、原因調査中。技術課題。",
                severity="critical", owner_id=people["tanaka"].id, raised_on=d(-4), due_date=d(2), status="open",
            ),
            Issue(
                project_id=project.id, code="I-005", task_id=t5.id,
                title="画面遷移の仕様確認",
                description="確認済み。", severity="low", owner_id=people["suzuki"].id,
                raised_on=d(-20), due_date=d(-10), status="resolved", resolution="仕様書 v1.2 に反映済み",
            ),
        ]
    )

    db.add_all(
        [
            Milestone(project_id=project.id, title="内部リリース判定", due_date=d(12), status="pending"),
            Milestone(project_id=project.id, title="本番リリース", due_date=d(45), status="pending"),
            Milestone(project_id=project.id, title="要件定義完了", due_date=d(-38), status="achieved"),
        ]
    )
    db.commit()
    db.refresh(project)
    return project


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        existing = db.scalar(select(Project).where(Project.name == DEMO_PROJECT_NAME))
        if existing:
            print(f"デモプロジェクトは既に存在します (id={existing.id})")
            return
        project = seed_demo_project(db)
        print(f"デモプロジェクトを作成しました (id={project.id}): {project.name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
