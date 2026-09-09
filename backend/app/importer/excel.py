"""Reading spreadsheets, detecting headers and committing rows into a project."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
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
    """Parse one spreadsheet row.

    Empty cells stay ``None`` so that a sync import never wipes a value that the
    spreadsheet simply does not carry.
    """
    progress = vp.parse_progress(_cell(row, mapping, "progress"))
    status_cell = vp.clean_str(_cell(row, mapping, "status"))
    priority_cell = vp.clean_str(_cell(row, mapping, "priority"))
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
        "progress": progress,
        "status": vp.parse_status(status_cell, progress) if status_cell else None,
        "priority": vp.parse_priority(priority_cell) if priority_cell else None,
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
    mapping, candidates = guess_mapping(columns, allow_title_fallback=False)

    # 列名で拾えなかった自由記述列を課題列として補完する
    auto_issue_column = None
    if not mapping.get("issue"):
        used_columns = {c for c in mapping.values() if c}
        auto_issue_column = find_free_text_column(frame, used_columns)
        if auto_issue_column:
            mapping["issue"] = auto_issue_column

    # 課題列が無い＝タスク一覧のはずなので、タスク名の列を仮割当してでも決める
    if not mapping.get("title") and not mapping.get("issue"):
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
        parsed["status"] = parsed["status"] or derive_status(parsed)
        parsed["priority"] = parsed["priority"] or "medium"
        parsed["progress"] = parsed["progress"] if parsed["progress"] is not None else 0.0
        parsed["planned_start"] = str(parsed["planned_start"]) if parsed["planned_start"] else None
        parsed["planned_end"] = str(parsed["planned_end"]) if parsed["planned_end"] else None
        parsed["actual_start"] = str(parsed["actual_start"]) if parsed["actual_start"] else None
        parsed["actual_end"] = str(parsed["actual_end"]) if parsed["actual_end"] else None
        preview_rows.append(parsed)

    raw_preview = [
        {str(k): vp.normalize_text(v) for k, v in row.items()}
        for _, row in frame.head(PREVIEW_ROWS).iterrows()
    ]

    detected = detect_content(frame, mapping)

    warnings: list[str] = []
    if auto_issue_column:
        warnings.append(
            f"「{auto_issue_column}」列は自由記述に見えたため、課題列として扱います（列マッピングで変更できます）。"
        )
    # 課題リストにタスク用の列が無いのは当たり前なので、警告として出さない
    if detected["content_kind"] != "issues":
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
        **detected,
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


# --------------------------------------------------------------------------- sync
SYNCED_FIELDS: tuple[tuple[str, str], ...] = (
    ("title", "タスク名"),
    ("description", "詳細"),
    ("planned_start", "開始予定日"),
    ("planned_end", "終了予定日"),
    ("actual_start", "実績開始日"),
    ("actual_end", "実績終了日"),
    ("progress", "進捗率"),
    ("status", "Status"),
    ("priority", "Priority"),
    ("estimated_hours", "工数"),
    ("notes", "備考"),
)


def derive_status(parsed: dict[str, Any]) -> str:
    progress = parsed.get("progress")
    if progress is None:
        return "not_started"
    if progress >= 100:
        return "done"
    return "in_progress" if progress > 0 else "not_started"


@dataclass
class RowChange:
    field: str
    label: str
    before: Any
    after: Any


@dataclass
class RowPlan:
    row_index: int
    title: str
    code: str | None
    action: str  # create | update | unchanged | skip
    matched_task_id: int | None = None
    matched_task_title: str | None = None
    matched_by: str | None = None
    changes: list[RowChange] = field(default_factory=list)


def _index_tasks(tasks: list[Task]) -> tuple[dict[str, Task], dict[str, Task]]:
    by_code: dict[str, Task] = {}
    by_title: dict[str, Task] = {}
    for task in tasks:
        if task.code:
            by_code.setdefault(vp.normalize_text(task.code), task)
        by_title.setdefault(vp.normalize_text(task.title), task)
    return by_code, by_title


def _match_task(
    parsed: dict[str, Any],
    by_code: dict[str, Task],
    by_title: dict[str, Task],
    match_by: str,
) -> tuple[Task | None, str | None]:
    """Find the existing task this row refers to."""
    if match_by == "none":
        return None, None
    if match_by in ("auto", "code") and parsed.get("code"):
        found = by_code.get(vp.normalize_text(parsed["code"]))
        if found is not None:
            return found, "code"
        if match_by == "code":
            return None, None
    if match_by in ("auto", "title") and parsed.get("title"):
        found = by_title.get(vp.normalize_text(parsed["title"]))
        if found is not None:
            return found, "title"
    return None, None


def _owner_name_of(task: Task, people: dict[int, Person]) -> str | None:
    person = people.get(task.owner_id) if task.owner_id else None
    return person.name if person else None


def _diff_row(task: Task, parsed: dict[str, Any], owner_name: str | None) -> list[RowChange]:
    """Non-empty incoming values that differ from what is stored."""
    changes: list[RowChange] = []
    for name, label in SYNCED_FIELDS:
        incoming = parsed.get(name)
        if incoming is None:
            continue  # 空欄は「変更なし」として扱う
        current = getattr(task, name)
        if name == "progress":
            if current is not None and abs(float(current) - float(incoming)) < 0.01:
                continue
        elif current == incoming:
            continue
        changes.append(RowChange(field=name, label=label, before=current, after=incoming))
    incoming_owner = (parsed.get("owner") or "").strip() or None
    if incoming_owner:
        names = vp.parse_person_names(incoming_owner)
        first = names[0] if names else None
        if first and first != owner_name:
            changes.append(RowChange(field="owner", label="担当者", before=owner_name, after=first))
    if parsed.get("code") and vp.normalize_text(parsed["code"]) != vp.normalize_text(task.code or ""):
        changes.append(RowChange(field="code", label="Task ID", before=task.code, after=parsed["code"]))
    return changes


def _parse_rows(frame: pd.DataFrame, mapping: dict[str, str | None]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    skipped = 0
    for index, (_, raw_row) in enumerate(frame.iterrows()):
        parsed = mapped_row(raw_row, mapping)
        if not parsed["title"]:
            skipped += 1
            continue
        parsed["_row_index"] = index
        rows.append(parsed)
    return rows, skipped


def _resolve_mapping(request, frame: pd.DataFrame, require_title: bool = True) -> dict[str, str | None]:
    mapping = {k: (v or None) for k, v in (request.mapping or {}).items()}
    if not mapping:
        mapping, _ = guess_mapping([str(c) for c in frame.columns])
    if require_title and not mapping.get("title"):
        raise ValueError("タスク名の列が指定されていません。")
    return mapping


def _default_match_by(request) -> str:
    if request.match_by and request.match_by != "auto":
        return request.match_by
    # 新規プロジェクトなら突き合わせ相手がいないので常に追加
    return "auto" if request.project_id else "none"


def plan_import(db: Session, request) -> dict[str, Any]:
    """Dry run: report what a sync import would create, update or leave alone."""
    path, _ = resolve_upload(request.token)
    frame, _, _ = load_frame(path, request.sheet, request.header_row)
    mapping = _resolve_mapping(request, frame)
    match_by = _default_match_by(request)

    existing: list[Task] = []
    people: dict[int, Person] = {}
    if request.project_id:
        project = db.get(Project, request.project_id)
        if project is None:
            raise ValueError(f"Project {request.project_id} は存在しません。")
        existing = list(db.scalars(select(Task).where(Task.project_id == project.id)))
        people = {
            p.id: p for p in db.scalars(select(Person).where(Person.project_id == project.id))
        }
    by_code, by_title = _index_tasks(existing)

    rows, skipped = _parse_rows(frame, mapping)
    plans: list[RowPlan] = []
    matched_ids: set[int] = set()
    for parsed in rows:
        task, matched_by = _match_task(parsed, by_code, by_title, match_by)
        if task is None:
            plans.append(
                RowPlan(
                    row_index=parsed["_row_index"],
                    title=parsed["title"],
                    code=parsed.get("code"),
                    action="create",
                )
            )
            continue
        matched_ids.add(task.id)
        changes = _diff_row(task, parsed, _owner_name_of(task, people))
        plans.append(
            RowPlan(
                row_index=parsed["_row_index"],
                title=parsed["title"],
                code=parsed.get("code"),
                action="update" if changes else "unchanged",
                matched_task_id=task.id,
                matched_task_title=task.title,
                matched_by=matched_by,
                changes=changes,
            )
        )

    missing = [
        {"task_id": t.id, "title": t.title}
        for t in existing
        if t.id not in matched_ids and match_by != "none"
    ]
    return {
        "match_by": match_by,
        "create_count": len([p for p in plans if p.action == "create"]),
        "update_count": len([p for p in plans if p.action == "update"]),
        "unchanged_count": len([p for p in plans if p.action == "unchanged"]),
        "skipped_rows": skipped,
        "rows": [
            {
                "row_index": p.row_index,
                "title": p.title,
                "code": p.code,
                "action": p.action,
                "matched_task_id": p.matched_task_id,
                "matched_task_title": p.matched_task_title,
                "matched_by": p.matched_by,
                "changes": [
                    {
                        "field": c.field,
                        "label": c.label,
                        "before": str(c.before) if c.before is not None else None,
                        "after": str(c.after) if c.after is not None else None,
                    }
                    for c in p.changes
                ],
            }
            for p in plans
        ],
        "missing_in_file": missing[:50],
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


def commit_import(db: Session, request) -> dict[str, Any]:
    """Create or update tasks / people / issues / dependencies from a spreadsheet."""
    path, filename = resolve_upload(request.token)
    frame, _, _ = load_frame(path, request.sheet, request.header_row)
    mapping = _resolve_mapping(request, frame, require_title=getattr(request, "create_tasks", True))
    match_by = _default_match_by(request)

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

    existing_tasks = list(db.scalars(select(Task).where(Task.project_id == project.id)))
    people_cache: dict[str, Person] = {
        p.name: p for p in db.scalars(select(Person).where(Person.project_id == project.id))
    }
    people_before = len(people_cache)
    by_code, by_title = _index_tasks(existing_tasks)

    rows, skipped = _parse_rows(frame, mapping)
    if not getattr(request, "create_tasks", True):
        # 課題リストだけのファイル。プロジェクトを用意して、あとは課題分析へ渡す。
        db.commit()
        return {
            "project_id": project.id,
            "project_name": project.name,
            "match_by": match_by,
            "created_tasks": 0,
            "updated_tasks": 0,
            "unchanged_tasks": 0,
            "created_people": 0,
            "created_issues": 0,
            "created_dependencies": 0,
            "created_milestones": 0,
            "skipped_rows": skipped,
            "warnings": ["課題リストとして取り込んだため、Taskは作成していません。"],
        }

    touched: list[Task] = []
    created_tasks = 0
    updated_tasks = 0
    unchanged_tasks = 0
    parent_names: dict[int, str] = {}
    dependency_refs: list[tuple[Task, list[str]]] = []
    issue_rows: list[tuple[Task, str]] = []
    milestone_rows: list[dict[str, Any]] = []
    sequence = len(existing_tasks)

    for parsed in rows:
        owner: Person | None = None
        names = vp.parse_person_names(parsed["owner"])
        if names and request.create_missing_people:
            owner = _get_or_create_person(db, project.id, names[0], people_cache)
            if len(names) > 1:
                warnings.append(
                    f"「{parsed['title']}」の担当者が複数指定されていたため、先頭の {names[0]} を主担当にしました。"
                )

        task, _matched_by = _match_task(parsed, by_code, by_title, match_by)
        if task is None:
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
                progress=parsed["progress"] if parsed["progress"] is not None else 0.0,
                status=parsed["status"] or derive_status(parsed),
                priority=parsed["priority"] or "medium",
                estimated_hours=parsed["estimated_hours"],
                notes=parsed["notes"],
            )
            db.add(task)
            db.flush()
            created_tasks += 1
            if task.code:
                by_code.setdefault(vp.normalize_text(task.code), task)
            by_title.setdefault(vp.normalize_text(task.title), task)
        else:
            changed = False
            for name_, _label in SYNCED_FIELDS:
                incoming = parsed.get(name_)
                if incoming is None:
                    continue
                if getattr(task, name_) != incoming:
                    setattr(task, name_, incoming)
                    changed = True
            if owner is not None and task.owner_id != owner.id:
                task.owner_id = owner.id
                changed = True
            if parsed["code"] and parsed["code"] != task.code:
                task.code = parsed["code"]
                changed = True
            if changed:
                updated_tasks += 1
            else:
                unchanged_tasks += 1

        touched.append(task)
        if parsed["parent"]:
            parent_names[task.id] = parsed["parent"]
        if parsed["dependency"]:
            dependency_refs.append((task, parsed["dependency"]))
        if parsed["issue"] and request.create_issues:
            issue_rows.append((task, parsed["issue"]))
        if parsed["milestone"]:
            milestone_rows.append({"title": parsed["title"], "due_date": parsed["planned_end"]})

    # ---- parents: explicit column first, then WBS numbering (1.2 -> 1)
    for task in list(touched):
        name_ = parent_names.get(task.id)
        parent = None
        if name_:
            key = vp.normalize_text(name_)
            parent = by_code.get(key) or by_title.get(key)
            if parent is None:
                parent = Task(project_id=project.id, title=name_[:300], status="not_started", progress=0.0)
                db.add(parent)
                db.flush()
                created_tasks += 1
                touched.append(parent)
                by_title.setdefault(key, parent)
        elif task.code:
            parent_code = vp.wbs_parent_code(task.code)
            if parent_code:
                parent = by_code.get(vp.normalize_text(parent_code))
        if parent is not None and parent.id != task.id and task.parent_task_id != parent.id:
            task.parent_task_id = parent.id

    # ---- dependencies: existing project tasks are valid targets too
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

    # ---- issues written in the WBS itself (再インポートでは重複させない)
    created_issues = 0
    issue_sequence = len(list(db.scalars(select(Issue.id).where(Issue.project_id == project.id))))
    for task, text in issue_rows:
        title = text[:300]
        duplicate = db.scalar(
            select(Issue).where(Issue.project_id == project.id, Issue.task_id == task.id, Issue.title == title)
        )
        if duplicate is not None:
            continue
        issue_sequence += 1
        db.add(
            Issue(
                project_id=project.id,
                code=f"I-{issue_sequence:03d}",
                task_id=task.id,
                title=title,
                description=f"WBSの課題列から自動生成（Task: {task.title}）\n{text}",
                severity="high"
                if task.status != "done" and task.planned_end and task.planned_end < date.today()
                else "medium",
                owner_id=task.owner_id,
                raised_on=date.today(),
                status="open",
            )
        )
        created_issues += 1

    created_milestones = 0
    for row in milestone_rows:
        title = row["title"][:300]
        duplicate = db.scalar(
            select(Milestone).where(Milestone.project_id == project.id, Milestone.title == title)
        )
        if duplicate is not None:
            continue
        db.add(Milestone(project_id=project.id, title=title, due_date=row["due_date"], status="pending"))
        created_milestones += 1

    # ---- project window from the imported plan
    starts = [t.planned_start for t in touched if t.planned_start]
    ends = [t.planned_end for t in touched if t.planned_end]
    if starts:
        project.start_date = min(starts) if not project.start_date else min(project.start_date, min(starts))
    if ends:
        project.end_date = max(ends) if not project.end_date else max(project.end_date, max(ends))

    db.commit()

    created_people = (
        len(list(db.scalars(select(Person.id).where(Person.project_id == project.id)))) - people_before
    )
    return {
        "project_id": project.id,
        "project_name": project.name,
        "match_by": match_by,
        "created_tasks": created_tasks,
        "updated_tasks": updated_tasks,
        "unchanged_tasks": unchanged_tasks,
        "created_people": max(0, created_people),
        "created_issues": created_issues,
        "created_dependencies": created_dependencies,
        "created_milestones": created_milestones,
        "skipped_rows": skipped,
        "warnings": warnings[:20],
    }

def _first_text(row, candidates: list[str | None], columns: list[str]) -> str | None:
    """関連タスクの手がかりを、タスク名列 → 親タスク列の順で拾う。"""
    for column in candidates:
        if column and column in columns:
            value = vp.clean_str(row.get(column))
            if value:
                return value
    return None


def issue_rows(request) -> dict[str, Any]:
    """課題列（自由記述）の全行テキストを取り出す。分類はここでは行わない。"""
    path, _ = resolve_upload(request.token)
    frame, _, _ = load_frame(path, request.sheet, request.header_row)
    columns = [str(c) for c in frame.columns]

    mapping = {k: (v or None) for k, v in (request.mapping or {}).items()}
    if not mapping:
        mapping, _ = guess_mapping(columns)
    column = request.text_column or mapping.get("issue")
    if column and column not in columns:
        column = None
    title_column = mapping.get("title")

    # テンプレートの「重要度」「期限」列は、書かれていればそのまま使う
    severity_column = mapping.get("priority")
    due_column = mapping.get("planned_end")

    rows: list[dict[str, Any]] = []
    if column:
        for index, (_, raw_row) in enumerate(frame.iterrows()):
            text = vp.clean_str(raw_row.get(column))
            if not text:
                continue
            rows.append(
                {
                    "row_index": index,
                    "text": text,
                    "task_hint": _first_text(raw_row, [title_column, mapping.get("parent")], columns),
                    "severity_hint": vp.clean_str(raw_row.get(severity_column))
                    if severity_column in columns
                    else None,
                    "due_date": vp.parse_date(raw_row.get(due_column)) if due_column in columns else None,
                }
            )

    return {"text_column": column, "rows": rows, "available_columns": columns}

# --------------------------------------------------------------------------- 内容判定
TASK_SIGNAL_FIELDS = (
    "planned_start", "planned_end", "actual_start", "actual_end",
    "progress", "status", "priority", "dependency", "owner", "estimated_hours", "code",
)
FREE_TEXT_MIN_LENGTH = 12  # これ以上の長さなら「自由記述」とみなす
# 連番（No列）はどんな表にもあるので、WBSの根拠としては弱い
WEAK_TASK_FIELDS = ("code",)
# 重要度・担当・期限は課題リストにもよくある列なので、自由記述の課題列が
# あるときはWBSの根拠にしない（WBS固有なのは予定開始日・進捗・依存など）
ISSUE_COMPATIBLE_FIELDS = ("priority", "owner", "planned_end")


def find_free_text_column(frame: pd.DataFrame, used: set[str]) -> str | None:
    """列名で判別できなかった自由記述列を、中身の長さから探す。

    先方が作る課題リストは列名が独特（「気になっていること」など）なので、
    辞書に無い名前でも拾えるようにしておく。
    """
    best: tuple[str, float] | None = None
    for column in frame.columns:
        name = str(column)
        if name in used:
            continue
        values = [vp.clean_str(value) or "" for value in frame[name]]
        values = [v for v in values if v]
        if len(values) < 2:
            continue
        long_values = [v for v in values if len(v) >= FREE_TEXT_MIN_LENGTH]
        if len(long_values) < 2:
            continue
        score = sum(len(v) for v in long_values) / len(values)
        if best is None or score > best[1]:
            best = (name, score)
    return best[0] if best else None


def detect_content(frame: pd.DataFrame, mapping: dict[str, str | None]) -> dict[str, Any]:
    """アップロードされた中身が WBS か課題リストかを判定する。

    ヘッダーの有無だけでなく、実際に値が入っているかまで見る。列名だけ揃っていて
    中身が空の表で誤判定しないため。判断がつかないときは unknown を返し、
    画面側でユーザーに一言確認してもらう。
    """
    evidence: list[str] = []

    def filled(column: str | None) -> int:
        if not column or column not in frame.columns:
            return 0
        return sum(1 for value in frame[column] if vp.clean_str(value))

    issue_column = mapping.get("issue")
    issue_texts = (
        [vp.clean_str(value) or "" for value in frame[issue_column]]
        if issue_column and issue_column in frame.columns
        else []
    )
    issue_texts = [t for t in issue_texts if t]
    long_issue_texts = [t for t in issue_texts if len(t) >= FREE_TEXT_MIN_LENGTH]

    task_fields = [f for f in TASK_SIGNAL_FIELDS if mapping.get(f) and filled(mapping[f]) > 0]
    ignored = ISSUE_COMPATIBLE_FIELDS if long_issue_texts else ()
    strong_task_fields = [
        f for f in task_fields if f not in WEAK_TASK_FIELDS and f not in ignored
    ]
    if strong_task_fields:
        labels = [FIELD_LABELS.get(f, f) for f in strong_task_fields]
        evidence.append("タスク用の列に値がある: " + "、".join(labels[:5]))
    elif task_fields and not long_issue_texts:
        labels = [FIELD_LABELS.get(f, f) for f in task_fields]
        evidence.append("タスク用の列に値がある: " + "、".join(labels[:5]))
    elif [f for f in task_fields if f in ignored]:
        # ユーザーが書いた列名でそのまま伝えたほうが分かりやすい
        names = [str(mapping[f]) for f in task_fields if f in ignored and mapping.get(f)]
        evidence.append(
            "「" + "、".join(names) + "」の列もあるが、課題リストにもよくある列なのでWBSとは判定しない"
        )

    if issue_texts:
        evidence.append(
            f"課題列「{issue_column}」に {len(issue_texts)} 行の記述"
            + (f"（うち {len(long_issue_texts)} 行は自由記述）" if long_issue_texts else "")
        )

    # 課題列が無くても、タスク名の列が長文だけで構成されていれば課題リストとみなす
    title_column = mapping.get("title")
    title_texts = [vp.clean_str(value) or "" for value in frame[title_column]] if title_column in frame.columns else []
    title_texts = [t for t in title_texts if t]
    long_titles = [t for t in title_texts if len(t) >= 25]
    title_is_prose = bool(title_texts) and len(long_titles) / len(title_texts) >= 0.5
    if title_is_prose and not strong_task_fields:
        evidence.append(f"「{title_column}」列が長文中心で、タスク名というより記述に見える")

    has_task_data = len(strong_task_fields) >= 2
    has_issue_text = bool(long_issue_texts) or (title_is_prose and not strong_task_fields)

    if has_task_data and has_issue_text:
        kind, confidence = "mixed", 0.8
    elif has_task_data:
        kind, confidence = "wbs", 0.9 if len(strong_task_fields) >= 3 else 0.7
    elif has_issue_text:
        kind, confidence = "issues", 0.8 if long_issue_texts else 0.6
    else:
        kind, confidence = "unknown", 0.3
        evidence.append("タスク用の列も自由記述の課題列も判別できなかった")

    return {
        "content_kind": kind,
        "content_confidence": round(confidence, 2),
        "content_evidence": evidence,
        "has_task_data": has_task_data,
        "has_issue_text": has_issue_text,
    }
