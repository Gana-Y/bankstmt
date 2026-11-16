"""Layout-aware table reconstruction.

Many bank PDFs draw no table borders, so ``extract_tables`` finds nothing. Instead we:

1. group words into visual lines,
2. find the header line (Date / Narration / Debit / Credit / Balance ...),
3. assign every word of every following line to a column using the header geometry,
4. glue date-less lines (wrapped narrations) onto the transaction above.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .values import is_amount_token, is_date_token

NUMERIC_KEYS = ("debit", "credit", "balance", "amount")
DATE_KEYS = ("date", "value_date")

HEADER_RULES: Sequence[Tuple[str, "re.Pattern[str]"]] = [
    ("serial", re.compile(r"^(s ?no|sl ?no|sr ?no|serial( no)?|s n)$")),
    ("value_date", re.compile(r"\b(value|val)\b.*\b(date|dt)\b|^val dt$")),
    ("dr_cr", re.compile(r"^(dr cr|cr dr|drcr|crdr|dr or cr)$")),
    ("balance", re.compile(r"\bbalance\b|\bbal\b")),
    ("debit", re.compile(r"\b(withdrawals?|debits?|dr)\b")),
    ("credit", re.compile(r"\b(deposits?|credits?|cr)\b")),
    ("date", re.compile(r"\b(date|dt)\b")),
    ("ref", re.compile(r"\b(chq|cheque|ref|reference|instrument|utr)\b")),
    ("narration", re.compile(r"\b(narration|description|particulars|remarks|details)\b")),
    ("amount", re.compile(r"\bamount\b|\bamt\b")),
]


def normalize_header(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def classify_header(text: str) -> Optional[str]:
    norm = normalize_header(text)
    for key, pattern in HEADER_RULES:
        if pattern.search(norm):
            return key
    return None


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    words: List[Word]
    page: int

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def height(self) -> float:
        return statistics.median(w.height for w in self.words)


@dataclass
class Column:
    key: Optional[str]
    x0: float
    x1: float
    label: str = ""

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Layout:
    columns: List[Column]
    page: int = 0
    #: right edge of the date text per date column, learned from the data rows
    date_right: Dict[str, float] = field(default_factory=dict)

    def cols(self, *keys: str) -> List[Column]:
        return [c for c in self.columns if c.key in keys]

    @property
    def keys(self) -> set:
        return {c.key for c in self.columns if c.key}

    def describe(self) -> str:
        return ", ".join(f"{c.key or '?'}[{c.x0:.0f}-{c.x1:.0f}]" for c in self.columns)


# ---------------------------------------------------------------------------
def group_lines(words: Sequence[Word], page: int) -> List[Line]:
    ordered = sorted(words, key=lambda w: ((w.top + w.bottom) / 2, w.x0))
    lines: List[List[Word]] = []
    mids: List[float] = []
    for w in ordered:
        mid = (w.top + w.bottom) / 2
        tol = max(2.0, 0.55 * w.height)
        if lines and abs(mid - mids[-1]) <= tol:
            lines[-1].append(w)
            mids[-1] = (mids[-1] * (len(lines[-1]) - 1) + mid) / len(lines[-1])
        else:
            lines.append([w])
            mids.append(mid)
    return [Line(sorted(ws, key=lambda w: w.x0), page) for ws in lines]


def _cluster(words: Sequence[Word], gap: float, rows_by_word: Dict[int, int]) -> List[List[Word]]:
    cells: List[List[Word]] = []
    for w in sorted(words, key=lambda w: w.x0):
        if cells and w.x0 - max(x.x1 for x in cells[-1]) <= gap:
            cells[-1].append(w)
        else:
            cells.append([w])
    for cell in cells:
        cell.sort(key=lambda w: (rows_by_word[id(w)], w.x0))
    return cells


def _split_cell(cell: List[Word], rows_by_word: Dict[int, int]) -> List[List[Word]]:
    """Split a merged header cell such as "Value Dt Withdrawal Amt." into two labels.

    Splits at the widest internal gap when that gap clearly stands out and both halves are
    different, strongly-identified columns ("amount" is too weak to count).
    """
    if len(cell) < 2 or len({rows_by_word[id(w)] for w in cell}) > 1:
        return [cell]
    gaps = [(cell[i + 1].x0 - cell[i].x1, i) for i in range(len(cell) - 1)]
    ranked = sorted(gaps, reverse=True)
    widest, idx = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if widest < 3.5 or (second and widest < 1.6 * second):
        return [cell]
    left, right = cell[: idx + 1], cell[idx + 1 :]
    k1 = classify_header(" ".join(w.text for w in left))
    k2 = classify_header(" ".join(w.text for w in right))
    strong = lambda k: k is not None and k != "amount"  # noqa: E731
    if strong(k1) and strong(k2) and k1 != k2:
        return _split_cell(left, rows_by_word) + _split_cell(right, rows_by_word)
    return [cell]


def _layout_from_words(words: Sequence[Word], rows_by_word: Dict[int, int], page: int) -> Optional[Layout]:
    med_h = statistics.median(w.height for w in words)
    gap = max(5.0, 0.9 * med_h)
    columns: List[Column] = []
    cells = [part for cell in _cluster(words, gap, rows_by_word) for part in _split_cell(cell, rows_by_word)]
    for cell in cells:
        label = " ".join(w.text for w in cell)
        columns.append(Column(classify_header(label), min(w.x0 for w in cell), max(w.x1 for w in cell), label))
    # a second "date" column is the value date
    seen_date = False
    for c in columns:
        if c.key == "date":
            if seen_date:
                c.key = "value_date"
            seen_date = True
    keys = {c.key for c in columns if c.key}
    core = keys & {"date", "narration", "debit", "credit", "amount", "balance"}
    has_money = bool(keys & {"debit", "credit", "amount"}) or "balance" in keys
    if "date" in keys and has_money and len(core) >= 3:
        return Layout(columns, page)
    return None


def _looks_like_header_continuation(line: Line) -> bool:
    for w in line.words:
        if is_date_token(w.text) or is_amount_token(w.text):
            return False
        if not re.search(r"[A-Za-z]", w.text):
            return False
    return len(line.words) <= 8


def find_header(lines: Sequence[Line], i: int) -> Optional[Tuple[Layout, int]]:
    """Try to read a header starting at ``lines[i]``. Returns (layout, lines_consumed)."""
    first = lines[i]
    rows = {id(w): 0 for w in first.words}
    single = _layout_from_words(first.words, rows, first.page)
    if i + 1 < len(lines):
        second = lines[i + 1]
        close = second.top - first.bottom < 1.6 * first.height
        if close and second.page == first.page and _looks_like_header_continuation(second):
            rows2 = dict(rows)
            rows2.update({id(w): 1 for w in second.words})
            double = _layout_from_words(list(first.words) + list(second.words), rows2, first.page)
            if double and (single is None or double.keys >= single.keys):
                return double, 2
    if single:
        return single, 1
    return None


# ---------------------------------------------------------------------------
def prime_layout(layout: Layout, lines: Sequence[Line], start: int, limit: int = 80) -> None:
    """Look ahead at the data rows to learn where the date text ends.

    Headers are often centred over left-aligned data, so header x-positions alone can
    put the first words of a narration into the date column.
    """
    date_cols = layout.cols(*DATE_KEYS)
    for line in lines[start : start + limit]:
        for w in line.words:
            if is_date_token(w.text):
                near = [c for c in date_cols if c.x0 - 40 <= w.x0 <= c.x1 + 15]
                if near:
                    c = min(near, key=lambda c: abs(c.x0 - w.x0))
                    layout.date_right[c.key] = max(layout.date_right.get(c.key, 0.0), w.x1)


def _merge_suffix_tokens(words: Sequence[Word]) -> List[Word]:
    """'1,000.00' 'Cr' -> '1,000.00Cr' when they sit next to each other."""
    out: List[Word] = []
    for w in words:
        if (
            out
            and w.text.lower().rstrip(".") in ("cr", "dr")
            and is_amount_token(out[-1].text)
            and w.x0 - out[-1].x1 < 1.5 * max(w.height, 4.0)
        ):
            prev = out[-1]
            out[-1] = Word(prev.text + w.text, prev.x0, w.x1, prev.top, w.bottom)
        else:
            out.append(w)
    return out


def _numeric_distance(col: Column, w: Word) -> float:
    return min(abs(w.x1 - col.x1), abs(w.center - col.center), abs(w.x0 - col.x0))


def _left_bound(layout: Layout, col: Column, left_cols: Sequence[Column]) -> float:
    bound = col.x0 - (0.5 * col.width + 4)
    if col.key not in DATE_KEYS and layout.date_right:
        earlier = [d for d in left_cols if d.key in DATE_KEYS and d.x0 < col.x0]
        if earlier:
            d = max(earlier, key=lambda d: d.x0)
            between = [o for o in left_cols if d.x0 < o.x0 < col.x0]
            if not between and d.key in layout.date_right:
                bound = min(bound, layout.date_right[d.key] + 1.5)
    return bound


def assign_words(layout: Layout, words: Sequence[Word]) -> Dict[str, List[Word]]:
    """Distribute the words of one line over the layout's columns."""
    result: Dict[str, List[Word]] = {}
    numeric_cols = layout.cols(*NUMERIC_KEYS)
    date_cols = layout.cols(*DATE_KEYS)
    text_cols = [c for c in layout.columns if c.key not in NUMERIC_KEYS and c.key not in DATE_KEYS]

    for w in _merge_suffix_tokens(words):
        target: Optional[Column] = None

        if numeric_cols and is_amount_token(w.text):
            fitting = [c for c in numeric_cols if w.x1 >= c.x0 - 4 and w.x0 <= c.x1 + 20]
            if fitting:
                target = min(fitting, key=lambda c: _numeric_distance(c, w))

        if target is None and date_cols and is_date_token(w.text):
            near = [c for c in date_cols if c.x0 - 40 <= w.x0 <= c.x1 + 15]
            if near:
                target = min(near, key=lambda c: abs(c.x0 - w.x0))

        if target is None:
            # left-aligned text columns (and split dates such as "05 Apr 2024")
            left_cols = sorted(date_cols + text_cols, key=lambda c: c.x0)
            candidates = [c for c in left_cols if _left_bound(layout, c, left_cols) <= w.x0]
            if candidates:
                target = candidates[-1]
                # inside a numeric column's zone? then it is stray text (e.g. a lone "Dr")
                for nc in numeric_cols:
                    if nc.x0 > target.x0 and nc.x0 - 2 <= w.x0 <= nc.x1 + 4:
                        target = None
                        break
        if target is not None and target.key:
            result.setdefault(target.key, []).append(w)
    return result


def cell_text(assigned: Dict[str, List[Word]], key: str) -> str:
    return " ".join(w.text for w in sorted(assigned.get(key, []), key=lambda w: w.x0)).strip()
