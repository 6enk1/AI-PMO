"""Tolerant value parsing for spreadsheet cells."""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timedelta

EXCEL_EPOCH = date(1899, 12, 30)

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y年%m月%d日",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%y/%m/%d",
    "%m/%d",
    "%m月%d日",
)

STATUS_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cancelled", ("中止", "キャンセル", "取止", "取りやめ", "cancel", "cancelled", "canceled", "対象外")),
    ("done", ("完了", "済", "終了", "done", "closed", "complete", "completed", "finish", "finished", "100%")),
    ("blocked", ("保留", "中断", "停止", "ブロック", "block", "blocked", "onhold", "on hold", "待ち", "pending")),
    ("in_progress", ("進行", "着手", "対応中", "作業中", "実施中", "progress", "doing", "wip", "ongoing", "started")),
    ("not_started", ("未着手", "未開始", "未実施", "未対応", "not started", "notstarted", "todo", "to do", "new", "未")),
)

PRIORITY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("critical", ("最優先", "最高", "critical", "緊急", "urgent", "s", "sos")),
    ("high", ("高", "high", "重要", "h", "a")),
    ("low", ("低", "low", "l", "c", "軽微")),
    ("medium", ("中", "medium", "normal", "m", "普通", "b")),
)

TRUTHY = ("○", "◯", "●", "yes", "y", "true", "1", "有", "あり", "ms", "milestone", "マイルストーン", "◎", "★", "*")


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return "" if text.lower() in ("nan", "nat", "none", "-", "ー", "―") else text


def clean_str(value: object, max_length: int | None = None) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    return text[:max_length] if max_length else text


def parse_date(value: object) -> date | None:
    """Accept datetimes, Excel serial numbers and a pile of string formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):  # pandas.Timestamp
        try:
            return value.to_pydatetime().date()
        except Exception:  # pragma: no cover - defensive
            return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        serial = float(value)
        if 1 < serial < 100000:
            return EXCEL_EPOCH + timedelta(days=int(serial))
        return None

    text = normalize_text(value)
    if not text:
        return None
    text = text.replace("〜", "").split("(")[0].strip()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt in ("%m/%d", "%m月%d日"):
            parsed = parsed.replace(year=date.today().year)
        return parsed.date()

    match = re.match(r"^(\d{4})\D{1,2}(\d{1,2})\D{1,2}(\d{1,2})", text)
    if match:
        y, m, d = (int(g) for g in match.groups())
        try:
            return date(y, m, d)
        except ValueError:
            return None
    if re.fullmatch(r"\d{8}", text):
        try:
            return datetime.strptime(text, "%Y%m%d").date()
        except ValueError:
            return None
    if re.fullmatch(r"\d{1,5}(\.\d+)?", text):  # Excel serial delivered as text
        return parse_date(float(text))
    return None


def parse_progress(value: object) -> float | None:
    """Return a 0-100 percentage from '80%', 0.8, 80, '完了' and friends."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 100.0 if value else 0.0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        number = float(value)
        if 0 < number <= 1:
            number *= 100
        return max(0.0, min(100.0, round(number, 1)))

    text = normalize_text(value)
    if not text:
        return None
    if "完了" in text or text.lower() in ("done", "complete", "completed"):
        return 100.0
    if "未着手" in text or text.lower() in ("not started", "todo"):
        return 0.0
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*%?", text.replace(",", ""))
    if not match:
        return None
    number = float(match.group(1))
    if "%" not in text and 0 < number <= 1:
        number *= 100
    return max(0.0, min(100.0, round(number, 1)))


def parse_status(value: object, progress: float | None = None) -> str:
    text = normalize_text(value).lower().replace(" ", "")
    if text:
        # Longest keyword wins so that "未着手" is not read as "着手" (in progress).
        best: tuple[int, int, str] | None = None
        for order, (status, keywords) in enumerate(STATUS_KEYWORDS):
            for keyword in keywords:
                needle = keyword.replace(" ", "")
                if needle and needle in text:
                    candidate = (len(needle), -order, status)
                    if best is None or candidate > best:
                        best = candidate
        if best is not None:
            return best[2]
    if progress is not None:
        if progress >= 100:
            return "done"
        if progress > 0:
            return "in_progress"
    return "not_started"


def parse_priority(value: object) -> str:
    text = normalize_text(value).lower().replace(" ", "")
    if not text:
        return "medium"
    for priority, keywords in PRIORITY_KEYWORDS:
        for keyword in keywords:
            if text == keyword or keyword in text:
                return priority
    return "medium"


def parse_severity(value: object) -> str:
    priority = parse_priority(value)
    return priority if priority in ("low", "medium", "high", "critical") else "medium"


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    text = normalize_text(value)
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group(0)) if match else None


def is_truthy(value: object) -> bool:
    text = normalize_text(value).lower()
    return bool(text) and any(text == t or text.startswith(t) for t in TRUTHY)


def split_references(value: object) -> list[str]:
    """Split a dependency / reference cell into individual task references."""
    text = normalize_text(value)
    if not text:
        return []
    parts = re.split(r"[,、;；\n\r/｜|]+", text)
    return [p.strip() for p in parts if p.strip() and p.strip() not in ("-", "なし", "無し")]


def parse_person_names(value: object) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    parts = re.split(r"[,、;；\n\r/／・]+", text)
    return [p.strip() for p in parts if p.strip()]


def wbs_parent_code(code: str | None) -> str | None:
    """'1.2.3' -> '1.2'  /  '1-2' -> '1'. Returns None for a top level code."""
    if not code:
        return None
    text = normalize_text(code)
    if not re.fullmatch(r"[0-9]+([.\-][0-9]+)*", text):
        return None
    parts = re.split(r"[.\-]", text)
    if len(parts) <= 1:
        return None
    separator = "." if "." in text else "-"
    return separator.join(parts[:-1])
