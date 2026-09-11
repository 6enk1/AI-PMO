"""クライアント記入用テンプレート（WBS / 課題リスト）を書き出す。

配布用（samples/）とデモ用（frontend/public/）の両方に同じものを置く。
中身の定義は backend/app/importer/ 側にあり、API
`GET /api/imports/template?kind=wbs|issues` が返すものと同一。

    python samples/generate_templates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.importer.template import template_bytes  # noqa: E402
from app.importer.wbs_template import wbs_template_bytes  # noqa: E402

TEMPLATES = (
    ("issue_list_template.xlsx", template_bytes),
    ("wbs_template.xlsx", wbs_template_bytes),
)
TARGET_DIRS = (ROOT / "samples", ROOT / "frontend" / "public")


def main() -> None:
    for filename, build in TEMPLATES:
        data = build()
        for directory in TARGET_DIRS:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / filename
            path.write_bytes(data)
            print(f"wrote {path.relative_to(ROOT)} ({len(data):,} bytes)")


if __name__ == "__main__":
    main()
