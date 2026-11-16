"""Parsing of dates and Indian-formatted amounts."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

# ---- dates -----------------------------------------------------------------
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
DATE_SEARCH = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                                # 2024-04-05
    re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\b"),            # 05/04/2024, 05-04-24
    re.compile(rf"\b(\d{{1,2}})[\s/\-,.]*({_MONTHS})[a-z]*[\s/\-,.]*(\d{{4}}|\d{{2}})\b", re.I),  # 05 Apr 2024, 05-Apr-24
]
# a single PDF "word" that is a complete date
DATE_TOKEN = re.compile(
    rf"^(\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}[/.\-]\d{{1,2}}[/.\-](\d{{4}}|\d{{2}})|\d{{1,2}}[\-/]({_MONTHS})[a-z]*[\-/](\d{{4}}|\d{{2}}))$",
    re.I,
)
_MONTH_NUM = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def _year(y: str) -> int:
    n = int(y)
    return n if len(y) == 4 else 2000 + n


def parse_date(text: str) -> Optional[date]:
    """Parse the first date found in ``text``. Day-first (Indian convention)."""
    if not text:
        return None
    try:
        m = DATE_SEARCH[0].search(text)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = DATE_SEARCH[1].search(text)
        if m:
            return date(_year(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = DATE_SEARCH[2].search(text)
        if m:
            return date(_year(m.group(3)), _MONTH_NUM[m.group(2).lower()[:3]], int(m.group(1)))
    except ValueError:
        return None
    return None


def is_date_token(text: str) -> bool:
    return bool(DATE_TOKEN.match(text))


# ---- amounts ---------------------------------------------------------------
_CURRENCY = re.compile(r"(?i)^(?:₹|rs\.?|inr)\s*")
_AMOUNT = re.compile(r"^\(?-?\d[\d,]*\.\d{1,2}\)?-?$")        # 1,00,000.00  (decimals required)
_AMOUNT_COMMA_INT = re.compile(r"^\(?-?\d{1,3}(?:,\d{2,3})+\)?-?$")  # 1,00,000
_SUFFIX = re.compile(r"(?i)(cr|dr)\.?$")


def split_suffix(text: str) -> Tuple[str, Optional[str]]:
    """'1,234.50Cr' -> ('1,234.50', 'Cr')"""
    t = text.strip()
    m = _SUFFIX.search(t)
    if m and len(t) > len(m.group(0)):
        return t[: m.start()].strip(), m.group(1).capitalize()
    return t, None


def is_amount_token(text: str) -> bool:
    t, _ = split_suffix(_CURRENCY.sub("", text.strip()))
    return bool(_AMOUNT.match(t) or _AMOUNT_COMMA_INT.match(t))


def parse_amount(text: str) -> Tuple[Optional[Decimal], Optional[str]]:
    """Return (value, 'Cr'|'Dr'|None). Negative numbers and (brackets) give a negative value."""
    if not text:
        return None, None
    t, suffix = split_suffix(_CURRENCY.sub("", text.strip()))
    if not (_AMOUNT.match(t) or _AMOUNT_COMMA_INT.match(t)):
        return None, None
    neg = t.startswith("-") or t.endswith("-") or (t.startswith("(") and t.endswith(")"))
    cleaned = t.strip("()-").replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None, None
    return (-value if neg else value), suffix
