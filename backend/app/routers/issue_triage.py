"""自由記述の課題リストを判定・整形し、確認後にまとめて登録する。

Excel Import の後段として使うが、analyze はテキスト配列を受け取る汎用APIなので、
将来 Word / PDF / 貼り付けテキストを足すときもそのまま流用できる。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..ai.llm import triage_statements
from ..analysis.issue_triage import triage_rows
from ..importer.value_parsers import parse_severity
from ..database import get_db
from ..models import Issue, Person, Project, Task

router = APIRouter(prefix="/api/issues", tags=["issue-triage"])

SEVERITY_MAP = {"高": "high", "中": "medium", "低": "low", "不明": "medium"}


@router.post("/analyze", response_model=schemas.IssueAnalyzeResponse)
def analyze(payload: schemas.IssueAnalyzeRequest, db: Session = Depends(get_db)) -> schemas.IssueAnalyzeResponse:
    """各行を課題 / 要確認 / 課題ではない に分類し、登録候補へ整形する（書き込みはしない）。"""
    tasks: list[tuple[int | None, str]] = []
    if payload.project_id is not None:
        project = db.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {payload.project_id} not found")
        tasks = [
            (task.id, task.title)
            for task in db.scalars(select(Task).where(Task.project_id == project.id))
        ]

    raw_rows = [
        (row.row_index if row.row_index is not None else index, row.text, row.task_hint)
        for index, row in enumerate(payload.rows)
    ]
    triaged = triage_rows(raw_rows, tasks)
    # 記入者が書いた重要度・期限は、推定より優先して使う
    hints = {
        (row.row_index if row.row_index is not None else index): row
        for index, row in enumerate(payload.rows)
    }

    # ---- LLMがあれば説明・分割・ラベルを上書きする（候補タスクは実在名のみ）
    llm_used, llm_note = False, None
    if payload.use_llm and triaged:
        statements = [
            {"id": f"s{index}", "text": entry["statement"], "context": entry["source_text"][:400]}
            for index, entry in enumerate(triaged)
        ]
        grouped, llm_used, llm_note = triage_statements(statements, [title for _, title in tasks])
    else:
        grouped = {}

    by_title = {title: task_id for task_id, title in tasks}
    items: list[schemas.IssueTriageItem] = []
    for index, entry in enumerate(triaged):
        result = entry["result"]
        overrides = grouped.get(f"s{index}") or []
        if not overrides:
            overrides = [None]
        for part, override in enumerate(overrides):
            label = result.label
            title = result.title
            description = result.description
            severity_jp = result.severity_estimate
            confidence = result.confidence
            reasons = list(result.reasons)
            candidates = [c.as_dict() for c in result.related_task_candidates]
            source = "rules"

            if override is not None:
                label = override["label"]
                title = override["title"] or title
                description = override["description"] or description
                severity_jp = override["severity_estimate"]
                confidence = override["confidence"]
                if override["reason"]:
                    reasons = [override["reason"]]
                if override["related_task_titles"]:
                    candidates = [
                        {"task_id": by_title.get(name), "title": name, "score": 1.0}
                        for name in override["related_task_titles"]
                    ]
                source = "llm"

            if label == "not_issue":
                title, description = title or "", description or ""

            hint = hints.get(entry["row_index"])
            severity = SEVERITY_MAP.get(severity_jp, "medium")
            due_date = hint.due_date if hint else None
            if hint and hint.severity_hint:
                severity = parse_severity(hint.severity_hint)
                severity_jp = {"high": "高", "medium": "中", "low": "低", "critical": "高"}.get(severity, "不明")
                reasons = [*reasons, f"記入された重要度「{hint.severity_hint}」を使用"]

            items.append(
                schemas.IssueTriageItem(
                    id=f"r{entry['row_index']}-{entry['part_index']}-{part}",
                    row_index=entry["row_index"],
                    part_index=entry["part_index"],
                    source_text=entry["source_text"],
                    statement=entry["statement"],
                    label=label,  # type: ignore[arg-type]
                    confidence=confidence,
                    title=title,
                    description=description,
                    severity_estimate=severity_jp,  # type: ignore[arg-type]
                    severity=severity,  # type: ignore[arg-type]
                    due_date=due_date,
                    reasons=reasons,
                    related_task_candidates=[schemas.TriageTaskCandidate(**c) for c in candidates],
                    split=entry["split"] or len(overrides) > 1,
                    source=source,
                )
            )

    counts = {label: len([i for i in items if i.label == label]) for label in ("issue", "uncertain", "not_issue")}
    return schemas.IssueAnalyzeResponse(
        llm_used=llm_used, llm_note=llm_note, counts=counts, items=items
    )


@router.post("/bulk_create", response_model=schemas.IssueBulkCreateResponse)
def bulk_create(
    payload: schemas.IssueBulkCreateRequest, db: Session = Depends(get_db)
) -> schemas.IssueBulkCreateResponse:
    """確認済みの候補をまとめて Issue として登録する。"""
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {payload.project_id} not found")

    task_ids = {t.id for t in db.scalars(select(Task).where(Task.project_id == project.id))}
    person_ids = {p.id for p in db.scalars(select(Person).where(Person.project_id == project.id))}
    sequence = len(list(db.scalars(select(Issue.id).where(Issue.project_id == project.id))))

    created: list[Issue] = []
    skipped: list[str] = []
    for item in payload.items:
        title = item.title.strip()
        if not title:
            skipped.append("課題名が空の行をスキップしました")
            continue
        if item.task_id is not None and item.task_id not in task_ids:
            skipped.append(f"「{title}」の関連Taskがプロジェクト内に無いため、関連付けを外しました")
        if item.owner_id is not None and item.owner_id not in person_ids:
            skipped.append(f"「{title}」の担当者がプロジェクト内に無いため、未設定にしました")
        sequence += 1
        issue = Issue(
            project_id=project.id,
            code=f"I-{sequence:03d}",
            task_id=item.task_id if item.task_id in task_ids else None,
            title=title[:300],
            description=item.description,
            severity=item.severity,
            owner_id=item.owner_id if item.owner_id in person_ids else None,
            due_date=item.due_date,
            status=item.status,
        )
        db.add(issue)
        created.append(issue)

    db.commit()
    return schemas.IssueBulkCreateResponse(
        created=len(created), issue_ids=[issue.id for issue in created], skipped=skipped[:20]
    )
