"""Quick numbers: monthly cash-flow and top spending categories."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Tuple

from .models import Statement

ZERO = Decimal("0")


def monthly(stmt: Statement) -> List[Tuple[str, Decimal, Decimal, Decimal, int]]:
    """[(YYYY-MM, money_in, money_out, net, n_transactions)]"""
    data: Dict[str, List[Decimal]] = defaultdict(lambda: [ZERO, ZERO, 0])
    for t in stmt.transactions:
        key = t.date.strftime("%Y-%m")
        data[key][0] += t.credit or ZERO
        data[key][1] += t.debit or ZERO
        data[key][2] += 1
    return [(k, v[0], v[1], v[0] - v[1], v[2]) for k, v in sorted(data.items())]


def top_categories(stmt: Statement, n: int = 8) -> List[Tuple[str, Decimal]]:
    totals: Dict[str, Decimal] = defaultdict(lambda: ZERO)
    for t in stmt.transactions:
        if t.debit:
            totals[t.category or "Uncategorized"] += t.debit
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:n]


def top_counterparties(stmt: Statement, n: int = 5) -> List[Tuple[str, Decimal]]:
    totals: Dict[str, Decimal] = defaultdict(lambda: ZERO)
    for t in stmt.transactions:
        if t.debit and t.counterparty:
            totals[t.counterparty] += t.debit
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:n]


def format_summary(stmt: Statement) -> str:
    period = stmt.period
    lines = []
    lines.append(f"Bank        : {stmt.bank}")
    if period:
        lines.append(f"Period      : {period[0]:%d %b %Y} to {period[1]:%d %b %Y}")
    lines.append(f"Transactions: {len(stmt.transactions)}")
    if stmt.opening_balance is not None:
        lines.append(f"Opening bal : {stmt.opening_balance:>14,.2f}")
    if stmt.closing_balance is not None:
        lines.append(f"Closing bal : {stmt.closing_balance:>14,.2f}")
    lines.append(f"Money in    : {stmt.total_credits:>14,.2f}")
    lines.append(f"Money out   : {stmt.total_debits:>14,.2f}")
    if stmt.checked_rows:
        ok = stmt.checked_rows - stmt.mismatched_rows
        lines.append(f"Balance check: {ok}/{stmt.checked_rows} rows reconcile")
    lines.append("")
    lines.append(f"{'Month':<9}{'In':>14}{'Out':>14}{'Net':>14}{'Txns':>6}")
    for month, cin, cout, net, n in monthly(stmt):
        lines.append(f"{month:<9}{cin:>14,.2f}{cout:>14,.2f}{net:>14,.2f}{n:>6}")
    cats = top_categories(stmt)
    if cats:
        total = stmt.total_debits or Decimal("1")
        lines.append("")
        lines.append("Where the money went")
        for name, amt in cats:
            pct = amt / total * 100
            bar = "█" * max(1, int(pct / 4))
            lines.append(f"  {name:<18}{amt:>12,.2f}  {pct:5.1f}%  {bar}")
    return "\n".join(lines)
