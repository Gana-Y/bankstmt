"""Plain data classes returned by the parser."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional


@dataclass
class Transaction:
    date: date
    description: str
    debit: Optional[Decimal] = None
    credit: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    value_date: Optional[date] = None
    ref_no: str = ""
    type: str = ""
    counterparty: str = ""
    category: str = ""
    page: int = 0
    direction_guessed: bool = False

    @property
    def amount(self) -> Decimal:
        """Signed amount: credits positive, debits negative."""
        return (self.credit or Decimal("0")) - (self.debit or Decimal("0"))


@dataclass
class Statement:
    transactions: List[Transaction] = field(default_factory=list)
    bank: str = "Unknown"
    source: str = ""
    opening_balance: Optional[Decimal] = None
    warnings: List[str] = field(default_factory=list)
    reversed_order: bool = False
    checked_rows: int = 0
    mismatched_rows: int = 0

    @property
    def closing_balance(self) -> Optional[Decimal]:
        for tx in reversed(self.transactions):
            if tx.balance is not None:
                return tx.balance
        return None

    @property
    def period(self):
        if not self.transactions:
            return None
        dates = [t.date for t in self.transactions]
        return min(dates), max(dates)

    @property
    def total_debits(self) -> Decimal:
        return sum((t.debit or Decimal("0") for t in self.transactions), Decimal("0"))

    @property
    def total_credits(self) -> Decimal:
        return sum((t.credit or Decimal("0") for t in self.transactions), Decimal("0"))


class BankstmtError(Exception):
    """Base error."""


class PasswordError(BankstmtError):
    """The PDF is encrypted and the password is missing or wrong."""


class LayoutNotFoundError(BankstmtError):
    """No transaction table header could be recognised in the PDF."""
