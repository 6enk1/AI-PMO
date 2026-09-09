"""クライアント記入用の課題リストテンプレートを書き出す。

配布用（samples/）とデモ用（frontend/public/）の両方に同じものを置く。
中身の定義は backend/app/importer/template.py 側にあり、API
`GET /api/imports/template` が返すものと同一。

    python samples/generate_issue_template.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.importer.template import template_bytes  # noqa: E402

TARGETS = (
    ROOT / "samples" / "issue_list_template.xlsx",
    ROOT / "frontend" / "public" / "issue_list_template.xlsx",
)


def main() -> None:
    data = template_bytes()
    for path in TARGETS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"wrote {path.relative_to(ROOT)} ({len(data):,} bytes)")


if __name__ == "__main__":
    main()
