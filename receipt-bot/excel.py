import os
from datetime import date
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

HEADERS = ["Огноо", "нэр", "нэмжих нэгж", "тоо", "нэгжийн үнэ", "Нийт дүн"]
HEAD_FILL = PatternFill("solid", fgColor="B4A7D6")
NEW_FILL = PatternFill("solid", fgColor="B7DEE8")  # шинэ (сүүлд нэмсэн) мөрүүд


def _new(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Худалдан авалт"
    ws.append(HEADERS)
    for c, w in zip("ABCDEF", (13, 38, 14, 8, 14, 14)):
        ws.column_dimensions[c].width = w
    for cell in ws[1]:
        cell.fill, cell.font = HEAD_FILL, Font(bold=True)
    return wb


def append_items(path, d: date, items):
    wb = load_workbook(path) if os.path.exists(path) else _new(path)
    ws = wb.active
    if ws.tables:
        for t in list(ws.tables):
            del ws.tables[t]
    for row in ws.iter_rows(min_row=2):  # өмнөх шинэ тэмдэглэгээг арилгана
        for c in row:
            c.fill = PatternFill(fill_type=None)
    for it in items:
        r = ws.max_row + 1
        ws.append([d, it.name, None, it.qty, it.price, f"=D{r}*E{r}"])
        ws.cell(r, 1).number_format = "d/m/yyyy"
        for col in (4, 5, 6):
            ws.cell(r, col).number_format = "#,##0"
        ws.cell(r, 6).font = Font(bold=True)
        for col in range(1, 7):
            ws.cell(r, col).fill = NEW_FILL
    ws.auto_filter.ref = f"A1:F{ws.max_row}"
    ws.freeze_panes = "A2"
    wb.save(path)
