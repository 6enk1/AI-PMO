"""クライアント記入用のWBSテンプレート。

課題リスト（:mod:`app.importer.template`）と同じ思想で、**必須はタスク名1列だけ**。
違いは「大カテゴリ」と「このカテゴリのゴール」を持つこと。

タスクの期限や担当だけを集めても、「何のためにやっているのか」が残らない。
カテゴリのゴールを1行書いてもらうと、取り込み後にカテゴリ（親タスク）の説明として
保持され、Task管理のカテゴリ行にそのまま表示される。
"""
from __future__ import annotations

import io
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

FONT = "Meiryo"
SHEET_NAME = "WBS"
GUIDE_SHEET = "記入のしかた"

# (見出し, 列幅)
HEADERS: tuple[tuple[str, int], ...] = (
    ("No", 6),
    ("大カテゴリ", 18),
    ("このカテゴリのゴール", 38),
    ("タスク（必須）", 30),
    ("タスクの詳細", 34),
    ("担当者", 12),
    ("開始予定日", 13),
    ("期限", 13),
    ("状態", 12),
    ("先行タスク", 18),
    ("備考", 22),
)
INPUT_ROWS = 50
WRAP_COLUMNS = (3, 5)  # ゴールと詳細だけ折り返す

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
GOAL_FILL = PatternFill("solid", fgColor="FFF2CC")   # ゴール列は色を変えて目立たせる
INPUT_FILL = PatternFill("solid", fgColor="EAF1FB")
EXAMPLE_FILL = PatternFill("solid", fgColor="F2F2F2")
THIN = Side(style="thin", color="B4C6E7")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

STATUSES = "未着手,進行中,完了,保留"

# 記入例。1つのカテゴリに2行入れて、「ゴールはカテゴリの1行目だけ」を示す。
# 進捗率の列は置いていない。計画を出してもらう時点では % は埋まらないし、
# 「進行中」かどうかが分かれば足りる（％はAI PMO側で運用できる）。
EXAMPLE_ROWS: tuple[tuple[object, ...], ...] = (
    (
        "例1",
        "要件定義",
        "現場が使える業務フローに合意が取れていて、開発に着手できる状態にする",
        "業務ヒアリング",
        "営業・受注・請求の3部門に各2回ヒアリングし、現行フローを文書化する",
        "山田",
        None,  # 日付は実行時に入れる
        None,
        "進行中",
        "",
        "",
    ),
    (
        "例2",
        "要件定義",
        "",  # 同じカテゴリなので空欄でよい
        "要件定義書レビュー",
        "ヒアリング結果をまとめ、部門長レビューで合意を取る",
        "鈴木",
        None,
        None,
        "未着手",
        "業務ヒアリング",
        "山田の作業完了後",
    ),
)

GUIDE_LINES: tuple[tuple[str, bool], ...] = (
    ("この表について", True),
    ("・プロジェクトでやることを、カテゴリごとに並べてください。", False),
    ("・体裁は整えなくて構いません。分かる範囲で埋めれば、残りは空欄でも取り込めます。", False),
    ("", False),
    ("記入するところ", True),
    ("・水色のセルに入力してください。グレーの行は記入例です（消しても、残したままでも構いません）。", False),
    ("・必須は「タスク（必須）」の列だけです。ほかは分かる範囲で構いません。", False),
    ("・1行1タスク。同じカテゴリのタスクは「大カテゴリ」に同じ名前を書いてください。", False),
    ("", False),
    ("「このカテゴリのゴール」について（いちばん大事）", True),
    ("・タスクの期限や担当だけだと、「何のためにやっているのか」が残りません。", False),
    ("・カテゴリごとに、達成したい状態を1行で書いてください。そのカテゴリの1行目だけで構いません。", False),
    ("・「〜を作る」ではなく「〜が決まっていて、〜に着手できる状態」のように、", False),
    ("　達成できたかどうかが判断できる書き方にしてください。", False),
    ("・取り込むと、カテゴリの説明として保持され、Task管理のカテゴリ行に表示されます。", False),
    ("", False),
    ("各列の説明", True),
    ("・No … 通し番号。「1」「1.1」のような階層番号でも構いません（親子関係として取り込みます）。", False),
    ("・大カテゴリ … 工程やフェーズの名前（要件定義 / 設計 / 開発 / テスト など）。", False),
    ("・このカテゴリのゴール … 上記のとおり。カテゴリの1行目だけで構いません。", False),
    ("・タスク（必須） … やること。30文字程度までが読みやすいです。", False),
    ("・タスクの詳細 … 作業内容・前提・成果物など、補足したいこと。", False),
    ("・担当者 … 氏名。未定なら空欄で構いません（複数なら「山田/鈴木」のように区切ってください）。", False),
    ("・開始予定日 / 期限 … 分かる範囲で。期限だけでも構いません（例: 2026/10/31）。", False),
    ("・状態 … 未着手 / 進行中 / 完了 / 保留 から選択。空欄なら未着手として扱います。", False),
    ("　（％での進捗率は書かなくて構いません。必要になったらAI PMOの画面で入れられます）", False),
    ("・先行タスク … このタスクの前に終わっている必要があるタスク名（複数なら「A, B」）。", False),
    ("・備考 … 補足があれば。", False),
    ("", False),
    ("列や行を増やしても大丈夫です", True),
    ("・行は足りなければ追加してください。列を増やしても、順番を入れ替えても取り込めます。", False),
    ("・列名は自動で判別します（「担当」「納期」など、言い方が違っても構いません）。", False),
    ("", False),
    ("取り込んだあとの流れ", True),
    ("・AI PMO の Excel Import から、このファイルをそのままアップロードしてください。", False),
    ("・列の対応・変換結果を確認してから取り込めます。2回目以降は同じファイルを更新して投げれば、", False),
    ("　同じタスクは重複せず更新されます（差分を事前に確認できます）。", False),
    ("・課題・困っていることは、このシートではなく「課題リスト」テンプレートに書いてください。", False),
)


def build_wbs_template(today: date | None = None) -> Workbook:
    today = today or date.today()
    book = Workbook()

    sheet = book.active
    sheet.title = SHEET_NAME

    sheet["A1"] = "WBS（作業一覧）"
    sheet["A1"].font = Font(name=FONT, size=14, bold=True)
    sheet["A2"] = "やること（タスク）をカテゴリごとに並べ、カテゴリには「達成したいゴール」を1行書いてください。"
    sheet["A2"].font = Font(name=FONT, size=9, color="595959")
    sheet["A3"] = "記入するのは水色のセルです。必須は「タスク（必須）」の列だけで、ほかは分かる範囲で構いません。"
    sheet["A3"].font = Font(name=FONT, size=9, color="595959")

    header_row = 5
    for index, (title, width) in enumerate(HEADERS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
        cell = sheet.cell(row=header_row, column=index, value=title)
        cell.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    sheet.row_dimensions[header_row].height = 30

    # 記入例（グレー・斜体）。実データと見分けが付くようにしておく。
    # 例2は例1の後続なので、日程も後ろに置く（そのまま取り込んでも矛盾を出さない）
    example_dates = ((3, 14), (15, 25))
    for offset, values in enumerate(EXAMPLE_ROWS):
        row = header_row + 1 + offset
        example = list(values)
        start_offset, end_offset = example_dates[offset]
        example[6] = (today + timedelta(days=start_offset)).strftime("%Y/%m/%d")
        example[7] = (today + timedelta(days=end_offset)).strftime("%Y/%m/%d")
        for index, value in enumerate(example, start=1):
            cell = sheet.cell(row=row, column=index, value=value)
            cell.font = Font(name=FONT, size=10, italic=True, color="7F7F7F")
            cell.fill = EXAMPLE_FILL
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=index in WRAP_COLUMNS)
        sheet.row_dimensions[row].height = 34

    first_input = header_row + 1 + len(EXAMPLE_ROWS)
    last_input = first_input + INPUT_ROWS - 1
    for row in range(first_input, last_input + 1):
        sheet.row_dimensions[row].height = 28
        for index in range(1, len(HEADERS) + 1):
            cell = sheet.cell(row=row, column=index)
            cell.font = Font(name=FONT, size=10)
            cell.fill = GOAL_FILL if index == 3 else INPUT_FILL
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=index in WRAP_COLUMNS)

    def add(validation: DataValidation, cells: str) -> None:
        sheet.add_data_validation(validation)
        validation.add(cells)

    add(
        DataValidation(
            type="list", formula1=f'"{STATUSES}"', allow_blank=True, showDropDown=False,
            promptTitle="状態",
            prompt="未着手 / 進行中 / 完了 / 保留 から選んでください。空欄なら未着手として扱います。",
        ),
        f"I{first_input}:I{last_input}",
    )
    for column, title in (("G", "開始予定日"), ("H", "期限")):
        add(
            DataValidation(
                type="date", operator="greaterThan", formula1="DATE(2000,1,1)", allow_blank=True,
                promptTitle=title, prompt="2026/10/31 のような日付で入れてください。分からなければ空欄で構いません。",
                errorTitle="日付を入れてください", error="2026/10/31 のような日付で入力してください。",
            ),
            f"{column}{first_input}:{column}{last_input}",
        )
    add(
        DataValidation(
            type="textLength", operator="greaterThan", formula1="0", allow_blank=True,
            promptTitle="大カテゴリ",
            prompt="工程やフェーズの名前（要件定義 / 設計 / 開発 / テスト など）。同じカテゴリには同じ名前を書いてください。",
        ),
        f"B{first_input}:B{last_input}",
    )
    add(
        DataValidation(
            type="textLength", operator="greaterThan", formula1="0", allow_blank=True,
            promptTitle="このカテゴリのゴール",
            prompt="達成したい状態を1行で。そのカテゴリの1行目だけで構いません（例: 業務フローに合意が取れていて、開発に着手できる状態）。",
        ),
        f"C{first_input}:C{last_input}",
    )

    # 見出しと、カテゴリ・ゴール列を常に見えるようにしておく
    sheet.freeze_panes = sheet.cell(row=first_input, column=4)

    guide = book.create_sheet(GUIDE_SHEET)
    guide.column_dimensions["A"].width = 96
    for index, (line, is_heading) in enumerate(GUIDE_LINES, start=1):
        cell = guide.cell(row=index, column=1, value=line)
        cell.font = Font(name=FONT, size=11 if is_heading else 10, bold=is_heading)
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    return book


def wbs_template_bytes(today: date | None = None) -> bytes:
    buffer = io.BytesIO()
    build_wbs_template(today).save(buffer)
    return buffer.getvalue()
