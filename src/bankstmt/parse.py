"""PDF -> Statement."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pdfplumber

from .banks import detect_bank
from .categorize import Categorizer
from .layout import (
    Layout,
    Word,
    assign_words,
    cell_text,
    find_header,
    group_lines,
    prime_layout,
)
from .models import LayoutNotFoundError, PasswordError, Statement, Transaction
from .narration import classify_type, clean, extract_counterparty
from .values import parse_amount, parse_date

ZERO = Decimal("0")
TOL = Decimal("0.01")

# date-less lines that end the transaction table
STOP_RE = re.compile(
    r"^\s*(statement\s+summary|closing\s+balance|grand\s+total|total\b|end\s+of\s+statement|\*+\s*end|"
    r"legends?\b|abbreviations?\b|registered\s+office|this\s+is\s+a\s+computer)",
    re.I,
)
# date-less lines that are page furniture inside the table
SKIP_RE = re.compile(r"(page\s+\d+\s*(of|/)\s*\d+|^\s*page\s+no|carried\s+forward|brought\s+forward|^\s*c/?f\b|^\s*b/?f\b|continued)", re.I)
OPENING_RE = re.compile(r"opening\s+balance|^\s*b/?f\b|brought\s+forward", re.I)


@dataclass
class _RawRow:
    page: int
    date_text: str
    value_date_text: str = ""
    narration: List[str] = field(default_factory=list)
    ref: str = ""
    debit: str = ""
    credit: str = ""
    amount: str = ""
    balance: str = ""
    drcr: str = ""
    bottom: float = 0.0


def _read_pages(path: str, password: Optional[str]) -> List[Tuple[int, List[Word], str]]:
    pages = []
    try:
        with pdfplumber.open(path, password=password) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                raw = page.extract_words(keep_blank_chars=False, use_text_flow=False)
                words = [Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"]) for w in raw]
                pages.append((i, words, page.extract_text() or ""))
    except Exception as exc:  # pdfplumber wraps pdfminer errors in PdfminerException(inner)
        inner = [exc, *[a for a in exc.args if isinstance(a, BaseException)]]
        names = " ".join(type(e).__name__ for e in inner)
        if "Password" in names or "password" in str(exc).lower() or "encrypt" in str(exc).lower():
            raise PasswordError(
                "This PDF is password-protected. Pass the password (many banks use a combination of "
                "your name/DOB/account number; check the e-mail that came with the statement)."
                if not password
                else "Wrong PDF password."
            ) from exc
        raise
    return pages


def _signed_balance(text: str) -> Optional[Decimal]:
    value, suffix = parse_amount(text)
    if value is None:
        return None
    if suffix == "Dr":
        return -abs(value)
    if suffix == "Cr":
        return abs(value)
    return value


def _extract_rows(pages) -> Tuple[List[_RawRow], List[Layout], Optional[Decimal]]:
    rows: List[_RawRow] = []
    layouts: List[Layout] = []
    layout: Optional[Layout] = None
    in_table = False
    opening: Optional[Decimal] = None

    for page_no, words, _text in pages:
        if not words:
            continue
        lines = group_lines(words, page_no)
        last: Optional[_RawRow] = None
        i = 0
        while i < len(lines):
            line = lines[i]
            header = find_header(lines, i)
            if header:
                layout, consumed = header
                layouts.append(layout)
                in_table, last = True, None
                i += consumed
                prime_layout(layout, lines, i)
                continue
            i += 1
            if layout is None or not in_table:
                continue

            assigned = assign_words(layout, line.words)
            date_text = cell_text(assigned, "date")
            if parse_date(date_text) is None:
                if STOP_RE.match(line.text):
                    in_table, last = False, None
                    continue
                if SKIP_RE.search(line.text):
                    continue
                if OPENING_RE.search(line.text) and not cell_text(assigned, "date"):
                    value = _signed_balance(cell_text(assigned, "balance"))
                    if value is not None and opening is None:
                        opening = value
                    continue
                if last is not None and last.page == page_no and line.top - last.bottom < 2.2 * line.height:
                    narr = cell_text(assigned, "narration")
                    if narr:
                        last.narration.append(narr)
                    ref = cell_text(assigned, "ref")
                    if ref:
                        last.ref += ref
                    last.bottom = line.bottom
                continue

            row = _RawRow(
                page=page_no,
                date_text=date_text,
                value_date_text=cell_text(assigned, "value_date"),
                narration=[t for t in [cell_text(assigned, "narration")] if t],
                ref=cell_text(assigned, "ref"),
                debit=cell_text(assigned, "debit"),
                credit=cell_text(assigned, "credit"),
                amount=cell_text(assigned, "amount"),
                balance=cell_text(assigned, "balance"),
                drcr=cell_text(assigned, "dr_cr"),
                bottom=line.bottom,
            )
            rows.append(row)
            last = row
    return rows, layouts, opening


def _build(row: _RawRow) -> Optional[Transaction]:
    desc = clean(" ".join(row.narration))
    debit, _ = parse_amount(row.debit)
    credit, _ = parse_amount(row.credit)
    amount, amount_suffix = parse_amount(row.amount)
    balance = _signed_balance(row.balance)
    saw_zero = (debit == ZERO) or (credit == ZERO)

    debit = abs(debit) if debit else None
    credit = abs(credit) if credit else None
    guessed = False

    if debit is None and credit is None and amount is not None:
        drcr = row.drcr.strip().lower()
        direction = None
        if drcr.startswith("d"):
            direction = "Dr"
        elif drcr.startswith("c"):
            direction = "Cr"
        elif amount_suffix:
            direction = amount_suffix
        elif amount < 0:
            direction = "Dr"
        if direction == "Dr":
            debit = abs(amount)
        elif direction == "Cr":
            credit = abs(amount)
        else:
            debit, guessed = abs(amount), True  # resolved later from the running balance
    elif debit is None and credit is None and saw_zero:
        debit = ZERO

    if debit is None and credit is None and balance is None:
        return None  # nothing useful on this row
    return Transaction(
        date=parse_date(row.date_text),
        value_date=parse_date(row.value_date_text),
        description=desc,
        ref_no=clean(row.ref),
        debit=debit,
        credit=credit,
        balance=balance,
        page=row.page,
        direction_guessed=guessed,
    )


def _consistent(prev: Transaction, cur: Transaction) -> bool:
    if prev.balance is None or cur.balance is None or cur.direction_guessed:
        return False
    return abs(prev.balance + cur.amount - cur.balance) <= TOL


def _orient(txs: List[Transaction]) -> Tuple[List[Transaction], bool]:
    """Some banks list newest first. Pick the direction in which the running balance adds up."""
    fwd = sum(_consistent(a, b) for a, b in zip(txs, txs[1:]))
    rev_list = txs[::-1]
    rev = sum(_consistent(a, b) for a, b in zip(rev_list, rev_list[1:]))
    if rev > fwd:
        return rev_list, True
    return txs, False


def _resolve_guessed(txs: List[Transaction], opening: Optional[Decimal], warnings: List[str]) -> None:
    prev_balance = opening
    for tx in txs:
        if tx.direction_guessed and tx.debit is not None:
            amt = tx.debit
            if prev_balance is not None and tx.balance is not None:
                delta = tx.balance - prev_balance
                if abs(delta - amt) <= TOL:
                    tx.credit, tx.debit, tx.direction_guessed = amt, None, False
                elif abs(delta + amt) <= TOL:
                    tx.direction_guessed = False
            if tx.direction_guessed:
                warnings.append(
                    f"{tx.date}: could not tell debit from credit for {amt}; assumed debit "
                    "(the statement has a single Amount column without Dr/Cr)."
                )
        if tx.balance is not None:
            prev_balance = tx.balance


def _reconcile(stmt: Statement) -> None:
    prev: Optional[Transaction] = None
    prev_balance = stmt.opening_balance
    mism = checked = 0
    for tx in stmt.transactions:
        if prev_balance is not None and tx.balance is not None and not tx.direction_guessed:
            checked += 1
            expected = prev_balance + tx.amount
            if abs(expected - tx.balance) > TOL:
                mism += 1
                if mism <= 15:
                    stmt.warnings.append(
                        f"Balance mismatch on {tx.date} (page {tx.page}, '{tx.description[:35]}'): "
                        f"expected {expected:,.2f}, statement says {tx.balance:,.2f}. "
                        "A row may be missing or misread."
                    )
        if tx.balance is not None:
            prev_balance = tx.balance
        prev = tx
    stmt.checked_rows, stmt.mismatched_rows = checked, mism
    if mism > 15:
        stmt.warnings.append(f"... and {mism - 15} more balance mismatches.")


def parse_pdf(
    path: str,
    *,
    password: Optional[str] = None,
    bank: Optional[str] = None,
    categorize: bool = True,
    rules: Optional[Dict[str, Iterable[str]]] = None,
) -> Statement:
    """Parse one bank statement PDF.

    Raises ``PasswordError`` for protected files and ``LayoutNotFoundError`` when no
    table header (Date / Narration / Debit / Credit / Balance ...) is recognised.
    """
    pages = _read_pages(path, password)
    if not any(w for _, w, _ in pages):
        raise LayoutNotFoundError(
            "No text found in the PDF. It may be a scanned image; OCR is not supported (yet)."
        )
    rows, layouts, opening = _extract_rows(pages)
    if not layouts:
        raise LayoutNotFoundError(
            "Could not find a transaction table header (Date / Narration / Debit / Credit / Balance). "
            "Run `bankstmt inspect FILE.pdf` and open an issue with the (redacted) output."
        )

    stmt = Statement(source=path, opening_balance=opening)
    first_text = pages[0][2] if pages else ""
    stmt.bank = bank or detect_bank(" ".join(t for _, _, t in pages[:2])) or "Unknown"

    txs = [t for t in (_build(r) for r in rows) if t is not None]
    # drop pure "opening balance" rows that carry a date but no movement
    cleaned: List[Transaction] = []
    for t in txs:
        if t.debit is None and t.credit is None:
            if OPENING_RE.search(t.description) and stmt.opening_balance is None:
                stmt.opening_balance = t.balance
            continue
        cleaned.append(t)
    txs, stmt.reversed_order = _orient(cleaned)
    if stmt.reversed_order:
        stmt.warnings.append("Statement was listed newest-first; output is in chronological order.")
    _resolve_guessed(txs, stmt.opening_balance, stmt.warnings)
    stmt.transactions = txs
    _reconcile(stmt)

    cat = Categorizer(rules) if categorize else None
    for tx in stmt.transactions:
        tx.type = classify_type(tx.description)
        tx.counterparty, ref = extract_counterparty(tx.description, tx.type)
        if not tx.ref_no and ref:
            tx.ref_no = ref
        if cat:
            tx.category = cat.categorize(tx)
    return stmt


def parse_many(paths: Sequence[str], **kwargs) -> Statement:
    """Parse several PDFs (e.g. 12 monthly statements) into one chronological, de-duplicated Statement."""
    merged = Statement(source=", ".join(paths))
    seen = set()
    for p in paths:
        s = parse_pdf(p, **kwargs)
        if merged.bank == "Unknown":
            merged.bank = s.bank
        merged.warnings += [f"{p}: {w}" for w in s.warnings]
        merged.checked_rows += s.checked_rows
        merged.mismatched_rows += s.mismatched_rows
        if merged.opening_balance is None:
            merged.opening_balance = s.opening_balance
        for tx in s.transactions:
            # balance makes the key effectively unique and is immune to differences in line wrapping
            key = (tx.date, tx.debit, tx.credit, tx.balance) if tx.balance is not None else (tx.date, tx.debit, tx.credit, tx.description)
            if key in seen:
                continue
            seen.add(key)
            merged.transactions.append(tx)
    merged.transactions.sort(key=lambda t: t.date)  # stable: keeps in-day order
    return merged
