"""CSV / JSON / XLSX writers."""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from typing import List, Optional

from .models import Statement, Transaction

COLUMNS = [
    "date", "value_date", "description", "ref_no", "debit", "credit", "amount",
    "balance", "type", "counterparty", "category", "bank",
]


def _money(x: Optional[Decimal]) -> str:
    return "" if x is None else f"{x:.2f}"


def _fmt_date(d, date_format: str) -> str:
    return "" if d is None else d.strftime(date_format)


def rows(stmt: Statement, date_format: str = "%Y-%m-%d") -> List[dict]:
    out = []
    for t in stmt.transactions:
        out.append(
            {
                "date": _fmt_date(t.date, date_format),
                "value_date": _fmt_date(t.value_date, date_format),
                "description": t.description,
                "ref_no": t.ref_no,
                "debit": _money(t.debit),
                "credit": _money(t.credit),
                "amount": _money(t.amount),
                "balance": _money(t.balance),
                "type": t.type,
                "counterparty": t.counterparty,
                "category": t.category,
                "bank": stmt.bank,
            }
        )
    return out


def to_csv(stmt: Statement, date_format: str = "%Y-%m-%d") -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows(stmt, date_format))
    return buf.getvalue()


def to_json(stmt: Statement, date_format: str = "%Y-%m-%d") -> str:
    period = stmt.period
    doc = {
        "bank": stmt.bank,
        "period": [period[0].isoformat(), period[1].isoformat()] if period else None,
        "opening_balance": _money(stmt.opening_balance) or None,
        "closing_balance": _money(stmt.closing_balance) or None,
        "total_debits": _money(stmt.total_debits),
        "total_credits": _money(stmt.total_credits),
        "balance_check": {"rows_checked": stmt.checked_rows, "mismatches": stmt.mismatched_rows},
        "warnings": stmt.warnings,
        "transactions": rows(stmt, date_format),
    }
    return json.dumps(doc, indent=2, ensure_ascii=False)


def to_xlsx(stmt: Statement, path: str) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:  # pragma: no cover
        raise ImportError("Excel export needs openpyxl: pip install 'bankstmt[xlsx]'") from exc
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
        c.alignment = Alignment(horizontal="center")
    for t in stmt.transactions:
        ws.append([
            t.date, t.value_date, t.description, t.ref_no,
            float(t.debit) if t.debit is not None else None,
            float(t.credit) if t.credit is not None else None,
            float(t.amount),
            float(t.balance) if t.balance is not None else None,
            t.type, t.counterparty, t.category, stmt.bank,
        ])
    for row in ws.iter_rows(min_row=2):
        row[0].number_format = row[1].number_format = "dd-mmm-yyyy"
        for idx in (4, 5, 6, 7):
            row[idx].number_format = "#,##0.00"
    widths = [12, 12, 55, 16, 14, 14, 14, 14, 10, 24, 18, 20]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)
