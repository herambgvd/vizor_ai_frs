"""Pure serialisers: rows → bytes in CSV, XLSX, or PDF.

These functions are deliberately DEPENDENCY-FREE of the DB, storage, and the web
layer — they just turn a ``list[dict]`` + an ordered ``list[str]`` of column keys
into the raw bytes of a file. That keeps them trivially unit-testable and reusable
from both the inline (request) path and the Celery (worker) path.

``columns`` fixes the order and selects which keys appear; a missing key in a row
renders as an empty cell rather than raising, so heterogeneous rows are tolerated.
"""

from __future__ import annotations

import csv
import io

# Heavy libs (openpyxl, reportlab) are imported lazily inside the functions that
# need them so importing this module (e.g. just for ``to_csv``) is cheap and does
# not require every export dependency to be installed.


def to_csv(rows: list[dict], columns: list[str]) -> bytes:
    """Render rows to CSV bytes (UTF-8). Header row = ``columns``."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Fill missing keys with "" so ragged rows don't blow up DictWriter.
        writer.writerow({col: row.get(col, "") for col in columns})
    return buf.getvalue().encode("utf-8")


def to_xlsx(rows: list[dict], columns: list[str], sheet: str = "Report") -> bytes:
    """Render rows to an in-memory .xlsx workbook (single sheet)."""
    from openpyxl import Workbook  # lazy: only needed for XLSX exports

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(columns)  # header row
    for row in rows:
        ws.append([row.get(col, "") for col in columns])
    # Save into a BytesIO so nothing touches disk; return the raw bytes.
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(title: str, rows: list[dict], columns: list[str]) -> bytes:
    """Render a simple titled table to PDF bytes via reportlab."""
    from reportlab.lib import colors  # lazy: only needed for PDF exports
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    styles = getSampleStyleSheet()

    # Build the table data: header row followed by one row per record. Every cell
    # is stringified so reportlab never chokes on non-string values.
    table_data = [columns]
    for row in rows:
        table_data.append([str(row.get(col, "")) for col in columns])

    table = Table(table_data, repeatRows=1)  # repeat the header on each page
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    # Title paragraph, a little breathing room, then the table.
    doc.build([Paragraph(title, styles["Title"]), Spacer(1, 12), table])
    return buf.getvalue()
