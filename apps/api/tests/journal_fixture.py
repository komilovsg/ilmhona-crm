"""An invented teacher's journal, laid out like the real «Журнал класса» (fake names, no real
data): a title, a row of lesson numbers «У1…» with a «сс» label, a header row of dates with «№» and
«ФИО студента», marks б / н / у, then Телефон / Telegram / ✅ Посещено / 📊 % посещ., a struck-through
row for a student who left and a totals row."""

from datetime import date
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

Student = tuple[str, list[str | None], bool]  # name, one mark per date, struck


def journal_xlsx(
    dates: list[date | str],
    students: list[Student],
    *,
    title: bool = True,
    numbers: bool = True,
    number_col: bool = True,
    extras: bool = True,
    sheet: str = "Журнал",
    wb: Workbook | None = None,
) -> bytes:
    own = wb is None
    wb = wb or Workbook()
    ws: Any = wb.active if own else wb.create_sheet()
    ws.title = sheet
    lead = 1 if number_col else 0  # columns before the names
    row = 1
    if title:
        ws.cell(row, 1, "Журнал класса — Python, группа 1")
        row += 1
    if numbers:
        ws.cell(row, 1, "сс")
        for i in range(len(dates)):
            ws.cell(row, lead + 2 + i, f"У{i + 1}")
        row += 1
    if number_col:
        ws.cell(row, 1, "№")
    ws.cell(row, lead + 1, "ФИО студента")
    for i, d in enumerate(dates):
        c = ws.cell(row, lead + 2 + i, d)
        if isinstance(d, date):
            c.number_format = "dd.mm"
    tail = lead + 2 + len(dates)
    if extras:
        for k, h in enumerate(("Телефон", "Telegram", "✅ Посещено", "📊 % посещ.")):
            ws.cell(row, tail + k, h)
    for n, (name, marks, struck) in enumerate(students, start=1):
        row += 1
        if number_col:
            ws.cell(row, 1, n)
        cell = ws.cell(row, lead + 1, name)
        if struck:
            cell.font = Font(strike=True)
        for i, m in enumerate(marks):
            if m:
                ws.cell(row, lead + 2 + i, m)
        if extras:
            ws.cell(row, tail, f"+9929000000{n:02d}")
            ws.cell(row, tail + 1, f"@fake_student_{n}")
            ws.cell(row, tail + 2, sum(m == "б" for m in marks))
            ws.cell(row, tail + 3, "80%")
    row += 1
    ws.cell(row, lead + 1, "Итого")
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
