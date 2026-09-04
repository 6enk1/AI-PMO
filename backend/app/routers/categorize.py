from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..ai.llm import classify_tasks
from ..analysis.categorize import TAXONOMY, Suggestion, existing_categories, suggest_categories
from ..analysis.snapshot import ProjectSnapshot, build_snapshot
from ..database import get_db
from ..models import Project, Task
from .deps import get_project, get_snapshot

router = APIRouter(prefix="/api/projects/{project_id}", tags=["categorize"])


@router.get("/categories/suggest", response_model=schemas.CategorySuggestResponse)
def suggest(
    snapshot: ProjectSnapshot = Depends(get_snapshot),
    include_categorized: bool = Query(
        default=False, description="既にカテゴリが付いているTaskも対象にするか"
    ),
    use_llm: bool = Query(default=True, description="LLMで分類を精緻化するか（未設定時は自動でルールベース）"),
) -> schemas.CategorySuggestResponse:
    """タスク名・説明・備考からカテゴリを推定する。"""
    categories = existing_categories(snapshot)
    rule_suggestions = suggest_categories(snapshot, include_categorized=include_categorized)
    by_task = {s.task_id: s for s in rule_suggestions}

    # 分類対象（カテゴリ自身は除く）
    targets = [
        v
        for v in snapshot.task_views()
        if not v.child_ids and (include_categorized or not v.task.parent_task_id)
    ]

    llm_used, llm_note = False, None
    if use_llm and targets:
        candidates = [
            {"name": title, "existing": True} for title in categories.values()
        ] + [{"name": name, "existing": False} for name, _ in TAXONOMY]
        payload = [
            {
                "task_id": v.id,
                "title": v.title,
                "description": (v.task.description or "")[:200],
                "notes": (v.task.notes or "")[:200],
            }
            for v in targets
        ]
        assignments, llm_used, llm_note = classify_tasks(payload, candidates)
        title_to_id = {title: task_id for task_id, title in categories.items()}
        for task_id, item in assignments.items():
            view = snapshot.views.get(task_id)
            if view is None or view.child_ids:
                continue
            name = item["category"]
            current = snapshot.category_of(task_id)
            if current == name:
                by_task.pop(task_id, None)  # 既にそのカテゴリなら提案しない
                continue
            by_task[task_id] = Suggestion(
                task_id=task_id,
                task_code=view.code,
                task_title=view.title,
                current_category=current,
                suggested_category=name,
                existing_category_id=title_to_id.get(name),
                confidence=item["confidence"],
                reason=item["reason"] or "LLMによる分類",
                source="llm",
            )

    return schemas.CategorySuggestResponse(
        project_id=snapshot.project.id,
        llm_used=llm_used,
        llm_note=llm_note,
        existing_categories=[
            {"task_id": task_id, "title": title} for task_id, title in categories.items()
        ],
        suggestions=sorted(
            (schemas.CategorySuggestion(**vars(s)) for s in by_task.values()),
            key=lambda s: (s.suggested_category, -s.confidence),
        ),
        unmatched_task_ids=[v.id for v in targets if v.id not in by_task],
    )


@router.post("/categories/apply", response_model=schemas.CategoryApplyResponse)
def apply(
    payload: schemas.CategoryApplyRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
) -> schemas.CategoryApplyResponse:
    """提案を確定し、必要ならカテゴリ（親タスク）を作成して割り当てる。"""
    if not payload.assignments:
        return schemas.CategoryApplyResponse(updated_tasks=0)

    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.project_id == project.id))}
    by_title = {t.title: t for t in tasks.values()}
    created: list[str] = []
    skipped: list[str] = []
    updated = 0

    def is_descendant(candidate: Task, ancestor_id: int) -> bool:
        seen: set[int] = set()
        current = candidate.parent_task_id
        while current and current not in seen:
            if current == ancestor_id:
                return True
            seen.add(current)
            current = tasks[current].parent_task_id if current in tasks else None
        return False

    for assignment in payload.assignments:
        task = tasks.get(assignment.task_id)
        if task is None:
            skipped.append(f"Task {assignment.task_id} はこのプロジェクトに存在しません")
            continue
        name = assignment.category_name.strip()
        category = by_title.get(name)
        if category is None:
            category = Task(project_id=project.id, title=name[:300], status="not_started")
            db.add(category)
            db.flush()
            tasks[category.id] = category
            by_title[name] = category
            created.append(name)
        if category.id == task.id or is_descendant(category, task.id):
            skipped.append(f"「{task.title}」は循環するため割り当てをスキップしました")
            continue
        if task.parent_task_id != category.id:
            task.parent_task_id = category.id
            updated += 1

    db.commit()
    return schemas.CategoryApplyResponse(
        updated_tasks=updated, created_categories=created, skipped=skipped
    )
