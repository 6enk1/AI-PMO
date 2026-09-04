"""Reading spreadsheets, detecting headers and committing rows into a project."""
from __future__ import annotations

import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Issue, Milestone, Person, Project, Task, TaskDependency
from . import value_parsers as vp
from .column_mapping import FIELD_LABELS, guess_mapping, header_match_score

MAX_HEADER_SCAN_ROWS = 15
PREVIEW_ROWS = 10
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp")


def upload_dir() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_upload(filename: str, content: bytes) -> str:
    token = uuid.uuid4().hex
    suffix = Path(filename).suffix.lower() or ".xlsx"
    target = upload_dir() / f"{token}{suffix}"
    target.write_bytes(content)
    (upload_dir() / f"{token}.json").write_text(
        json.dumps({"filename": filename, "path": str(target)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return token


def resolve_upload(token: str) -> tuple[Path, str]:
    meta_path = upload_dir() / f"{token}.json"
    if not meta_path.exists():
        raise FileNotFoundError("アップロードされたファイルが見つかりません。再度アップロードしてください。")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    path = Path(meta["path"])
    if not path.exists():
        raise FileNotFoundError("アップロードされたファイルが見つかりません。再度アップロードしてください。")
    return path, meta.get("filename", path.name)


# --------------------------------------------------------------------------- reading
def _read_csv(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            return pd.read_csv(path, header=None, dtype=object, encoding=encoding, keep_default_na=False, na_values=[""])
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:  # pragma: no cover - encoding dependent
            last_error = exc
    raise ValueError(f"CSVを読み込めませんでした: {last_error}")


def list_sheets(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        return ["CSV"]
    with pd.ExcelFile(path) as book:
        return list(book.sheet_names)


def read_raw(path: Path, sheet: str | None = None) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return _read_csv(path)
    with pd.ExcelFile(path) as book:
        target = sheet if sheet in book.sheet_names else book.sheet_names[0]
        return pd.read_excel(book, sheet_name=target, header=None, dtype=object)


def detect_header_row(raw: pd.DataFrame) -> int:
    """Pick the row that most looks like a WBS header."""
    best_row, best_score = 0, -1.0
    for index in range(min(MAX_HEADER_SCAN_ROWS, len(raw))):
        values = [vp.normalize_text(v) for v in raw.iloc[index].tolist()]
        filled = [v for v in values if v]
        if len(filled) < 2:
            continue
        # Header cells are labels, not data: penalise rows full of dates/numbers.
        data_like = sum(1 for v in filled if vp.parse_date(v) or re.fullmatch(r"-?\d+(\.\d+)?%?", v))
        score = header_match_score(filled) + 0.25 * len(filled) - 0.5 * data_like
        if score > best_score:
            best_row, best_score = index, score
    return best_row


def _dedupe(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for index, column in enumerate(columns):
        name = column or f"列{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}.{seen[name]}"
        else:
            seen[name] = 0
        out.append(name)
    return out


def load_frame(path: Path, sheet: str | None = None, header_row: int | None = None) -> tuple[pd.DataFrame, int, str]:
    raw = read_raw(path, sheet)
    sheets = list_sheets(path)
    selected = sheet if sheet in sheets else sheets[0]
    if raw.empty:
        return pd.DataFrame(), 0, selected
    row = header_row if header_row is not None else detect_header_row(raw)
    row = max(0, min(row, len(raw) - 1))
    header = [vp.normalize_text(v) for v in raw.iloc[row].tolist()]
    frame = raw.iloc[row + 1 :].copy()
    frame.columns = _dedupe(header)
    frame = frame.dropna(axis=1, how="all")
    frame = frame.loc[:, [c for c in frame.columns if vp.normalize_text(c)]]
    frame = frame.dropna(how="all")
    frame = frame.reset_index(drop=True)
    return frame, row, selected


# --------------------------------------------------------------------------- analyze
def _cell(row: pd.Series, mapping: dict[str, str | None], field: str) -> Any:
    column = mapping.get(field)
    if not column or column not in row.index:
        return None
    return row[column]


def mapped_row(row: pd.Series, mapping: dict[str, str | None]) -> dict[str, Any]:
    progress = vp.parse_progress(_cell(row, mapping, "progress"))
    return {
        "code": vp.clean_str(_cell(row, mapping, "code"), 40),
        "title": vp.clean_str(_cell(row, mapping, "title"), 300),
        "parent": vp.clean_str(_cell(row, mapping, "parent"), 300),
        "description": vp.clean_str(_cell(row, mapping, "description")),
        "owner": vp.clean_str(_cell(row, mapping, "owner"), 120),
        "planned_start": vp.parse_date(_cell(row, mapping, "planned_start")),
        "planned_end": vp.parse_date(_cell(row, mapping, "planned_end")),
        "actual_start": vp.parse_date(_cell(row, mapping, "actual_start")),
        "actual_end": vp.parse_date(_cell(row, mapping, "actual_end")),
        "progress": progress if progress is not None else 0.0,
        "status": vp.parse_status(_cell(row, mapping, "status"), progress),
        "priority": vp.parse_priority(_cell(row, mapping, "priority")),
        "dependency": vp.split_references(_cell(row, mapping, "dependency")),
        "issue": vp.clean_str(_cell(row, mapping, "issue"), 1000),
        "notes": vp.clean_str(_cell(row, mapping, "notes")),
        "milestone": vp.is_truthy(_cell(row, mapping, "milestone")),
        "estimated_hours": vp.parse_float(_cell(row, mapping, "estimated_hours")),
    }


def analyze_upload(
    token: str, sheet: str | None = None, header_row: int | None = None
) -> dict[str, Any]:
    path, filename = resolve_upload(token)
    sheets = list_sheets(path)
    frame, detected_header, selected = load_frame(path, sheet, header_row)
    columns = [str(c) for c in frame.columns]
    mapping, candidates = guess_mapping(columns)

    sheet_infos = []
    for name in sheets:
        try:
            sheet_frame, sheet_header, _ = load_frame(path, name)
            sheet_infos.append(
                {
                    "name": name,
                    "row_count": int(len(sheet_frame)),
                    "header_row": sheet_header,
                    "columns": [str(c) for c in sheet_frame.columns],
                }
            )
        except Exception:  # pragma: no cover - a broken sheet must not kill the upload
            sheet_infos.append({"name": name, "row_count": 0, "header_row": 0, "columns": []})

    preview_rows: list[dict[str, Any]] = []
    for _, row in frame.head(PREVIEW_ROWS).iterrows():
        parsed = mapped_row(row, mapping)
        parsed["planned_start"] = str(parsed["planned_start"]) if parsed["planned_start"] else None
        parsed["planned_end"] = str(parsed["planned_end"]) if parsed["planned_end"] else None
        parsed["actual_start"] = str(parsed["actual_start"]) if parsed["actual_start"] else None
        parsed["actual_end"] = str(parsed["actual_end"]) if parsed["actual_end"] else None
        preview_rows.append(parsed)

    raw_preview = [
        {str(k): vp.normalize_text(v) for k, v in row.items()}
        for _, row in frame.head(PREVIEW_ROWS).iterrows()
    ]

    warnings: list[str] = []
    if not mapping.get("title"):
        warnings.append("タスク名の列を特定できませんでした。列マッピングで指定してください。")
    if not mapping.get("planned_end"):
        warnings.append("終了予定日の列が見つかりません。期限超過・遅延リスクの検出精度が下がります。")
    if not mapping.get("owner"):
        warnings.append("担当者の列が見つかりません。担当者別の負荷分析ができません。")
    if len(frame) == 0:
        warnings.append("データ行が0件です。ヘッダー行の指定を見直してください。")

    used = {c for c in mapping.values() if c}
    return {
        "token": token,
        "filename": filename,
        "sheets": sheet_infos,
        "selected_sheet": selected,
        "header_row": detected_header,
        "columns": columns,
        "mapping": mapping,
        "mapping_candidates": [
            {"field": c.field, "column": c.column, "confidence": c.score, "reason": c.reason}
            for c in candidates
        ],
        "unmapped_columns": [c for c in columns if c not in used],
        "preview": preview_rows,
        "raw_preview": raw_preview,
        "warnings": warnings,
        "known_fields": [{"field": f, "label": label} for f, label in FIELD_LABELS.items()],
    }


# --------------------------------------------------------------------------- commit
def _get_or_create_person(db: Session, project_id: int, name: str, cache: dict[str, Person]) -> Person:
    key = name.strip()
    if key in cache:
        return cache[key]
    person = db.scalar(select(Person).where(Person.project_id == project_id, Person.name == key))
    if person is None:
        person = Person(project_id=project_id, name=key[:120])
        db.add(person)
        db.flush()
    cache[key] = person
    return person


def next_task_code(db: Session, project_id: int) -> str:
    count = len(list(db.scalars(select(Task.id).where(Task.project_id == project_id))))
    return f"T-{count + 1:03d}"


def commit_import(db: Session, request) -> dict[str, Any]:
    """Create tasks / people / issues / dependencies from a mapped spreadsheet."""
    path, filename = resolve_upload(request.token)
    frame, _, _ = load_frame(path, request.sheet, request.header_row)
    mapping = {k: (v or None) for k, v in (request.mapping or {}).items()}
    if not mapping:
        mapping, _ = guess_mapping([str(c) for c in frame.columns])
    if not mapping.get("title"):
        raise ValueError("タスク名の列が指定されていません。")

    warnings: list[str] = []
    project: Project | None = None
    if request.project_id:
        project = db.get(Project, request.project_id)
        if project is None:
            raise ValueError(f"Project {request.project_id} は存在しません。")
    if project is None:
        name = request.new_project_name or Path(filename).stem or "Imported Project"
        project = Project(name=name[:200], description=f"{filename} からインポート")
        db.add(project)
        db.flush()

    people_cache: dict[str, Person] = {}
    created_people_before = len(list(db.scalars(select(Person.id).where(Person.project_id == project.id))))

    rows: list[dict[str, Any]] = []
    skipped = 0
    for _, raw_row in frame.iterrows():
        parsed = mapped_row(raw_row, mapping)
        if not parsed["title"]:
            skipped += 1
            continue
        rows.append(parsed)

    created_tasks: list[Task] = []
    by_code: dict[str, Task] = {}
    by_title: dict[str, Task] = {}
    parent_names: dict[int, str] = {}
    dependency_refs: list[tuple[Task, list[str]]] = []
    issue_rows: list[tuple[Task, str]] = []
    milestone_rows: list[dict[str, Any]] = []

    sequence = len(list(db.scalars(select(Task.id).where(Task.project_id == project.id))))
    for parsed in rows:
        owner = None
        names = vp.parse_person_names(parsed["owner"])
        if names and request.create_missing_people:
            owner = _get_or_create_person(db, project.id, names[0], people_cache)
            if len(names) > 1:
                warnings.append(f"「{parsed['title']}」の担当者が複数指定されていたため、先頭の {names[0]} を主担当にしました。")

        sequence += 1
        task = Task(
            project_id=project.id,
            code=parsed["code"] or f"T-{sequence:03d}",
            title=parsed["title"],
            description=parsed["description"],
            owner_id=owner.id if owner else None,
            planned_start=parsed["planned_start"],
            planned_end=parsed["planned_end"],
            actual_start=parsed["actual_start"],
            actual_end=parsed["actual_end"],
            progress=parsed["progress"],
            status=parsed["status"],
            priority=parsed["priority"],
            estimated_hours=parsed["estimated_hours"],
            notes=parsed["notes"],
        )
        db.add(task)
        db.flush()
        created_tasks.append(task)
        if task.code:
            by_code[vp.normalize_text(task.code)] = task
        by_title.setdefault(vp.normalize_text(task.title), task)
        if parsed["parent"]:
            parent_names[task.id] = parsed["parent"]
        if parsed["dependency"]:
            dependency_refs.append((task, parsed["dependency"]))
        if parsed["issue"] and request.create_issues:
            issue_rows.append((task, parsed["issue"]))
        if parsed["milestone"]:
            milestone_rows.append({"title": parsed["title"], "due_date": parsed["planned_end"]})

    # ---- parents: explicit column first, then WBS numbering (1.2 -> 1)
    for task in created_tasks:
        name = parent_names.get(task.id)
        parent = None
        if name:
            key = vp.normalize_text(name)
            parent = by_code.get(key) or by_title.get(key)
            if parent is None:
                parent = Task(project_id=project.id, title=name[:300], status="not_started", progress=0.0)
                db.add(parent)
                db.flush()
                created_tasks.append(parent)
                by_title.setdefault(key, parent)
        elif task.code:
            parent_code = vp.wbs_parent_code(task.code)
            if parent_code:
                parent = by_code.get(vp.normalize_text(parent_code))
        if parent is not None and parent.id != task.id:
            task.parent_task_id = parent.id

    # ---- dependencies: match by code, then exact title, then partial title
    created_dependencies = 0
    for task, refs in dependency_refs:
        for ref in refs:
            key = vp.normalize_text(ref)
            predecessor = by_code.get(key) or by_title.get(key)
            if predecessor is None:
                matches = [t for k, t in by_title.items() if key and key in k]
                predecessor = matches[0] if len(matches) == 1 else None
            if predecessor is None or predecessor.id == task.id:
                warnings.append(f"「{task.title}」の依存先「{ref}」を解決できませんでした。")
                continue
            exists = db.scalar(
                select(TaskDependency).where(
                    TaskDependency.predecessor_task_id == predecessor.id,
                    TaskDependency.successor_task_id == task.id,
                )
            )
            if exists:
                continue
            db.add(
                TaskDependency(
                    predecessor_task_id=predecessor.id,
                    successor_task_id=task.id,
                    dependency_type="FS",
                )
            )
            created_dependencies += 1

    # ---- issues written in the WBS itself
    created_issues = 0
    issue_sequence = len(list(db.scalars(select(Issue.id).where(Issue.project_id == project.id))))
    for task, text in issue_rows:
        issue_sequence += 1
        db.add(
            Issue(
                project_id=project.id,
                code=f"I-{issue_sequence:03d}",
                task_id=task.id,
                title=text[:300],
                description=f"WBSの課題列から自動生成（Task: {task.title}）\n{text}",
                severity="high" if task.status != "done" and task.planned_end and task.planned_end < date.today() else "medium",
                owner_id=task.owner_id,
                raised_on=date.today(),
                status="open",
            )
        )
        created_issues += 1

    created_milestones = 0
    for row in milestone_rows:
        db.add(
            Milestone(
                project_id=project.id,
                title=row["title"][:300],
                due_date=row["due_date"],
                status="pending",
            )
        )
        created_milestones += 1

    # ---- project window from the imported plan
    starts = [t.planned_start for t in created_tasks if t.planned_start]
    ends = [t.planned_end for t in created_tasks if t.planned_end]
    if starts:
        project.start_date = min(starts) if not project.start_date else min(project.start_date, min(starts))
    if ends:
        project.end_date = max(ends) if not project.end_date else max(project.end_date, max(ends))

    db.commit()

    created_people = len(list(db.scalars(select(Person.id).where(Person.project_id == project.id)))) - created_people_before
    return {
        "project_id": project.id,
        "project_name": project.name,
        "created_tasks": len(created_tasks),
        "created_people": max(0, created_people),
        "created_issues": created_issues,
        "created_dependencies": created_dependencies,
        "created_milestones": created_milestones,
        "skipped_rows": skipped,
        "warnings": warnings[:20],
    }
