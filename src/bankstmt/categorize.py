"""Rule-based categories. Simple keyword rules, easy to extend with your own JSON file."""
from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Optional, Pattern, Tuple

from .models import Transaction

# (category, applies_to: None | "credit" | "debit", keywords)
BUILTIN_RULES: List[Tuple[str, Optional[str], List[str]]] = [
    ("Salary", "credit", ["salary", "payroll", "sal cr", "salary credit"]),
    ("Interest", None, ["interest", "int pd", "int.pd", "int cr", "int credit", "int paid"]),
    ("Bank Charges", "debit", ["service charge", "processing fee", "sms alert", "annual fee", "amc",
                              "penalty", "min bal", "non maintenance", "atm charges", "debit card fee",
                              "igst", "cgst", "sgst", "gst on", "chrg", "charges"]),
    ("Cash Withdrawal", "debit", ["atm", "nwd", "cash wdl", "cash withdrawal", "self withdrawal"]),
    ("Investments", None, ["zerodha", "groww", "upstox", "kuvera", "mutual fund", "sip", "nps", "ppf",
                           "indian clearing", "coin"]),
    ("Insurance", "debit", ["insurance", "lic of india", "lic premium", "hdfc life", "sbi life", "star health"]),
    ("Loan / EMI", "debit", ["emi", "loan", "bajaj finance"]),
    ("Groceries", "debit", ["bigbasket", "blinkit", "zepto", "dmart", "grofers", "instamart", "reliance fresh",
                            "more retail", "nature's basket", "grocery", "supermarket"]),
    ("Food & Dining", "debit", ["swiggy", "zomato", "dominos", "mcdonald", "kfc", "starbucks", "cafe",
                                "restaurant", "pizza", "burger", "bakery", "hotel"]),
    ("Travel", "debit", ["uber", "ola", "rapido", "irctc", "makemytrip", "redbus", "goibibo", "indigo",
                         "air india", "vistara", "akasa", "yatra", "cleartrip", "fastag", "metro"]),
    ("Fuel", "debit", ["petrol", "diesel", "hpcl", "bpcl", "iocl", "indian oil", "shell", "fuel"]),
    ("Shopping", "debit", ["amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa", "croma",
                           "decathlon", "reliance digital", "lifestyle"]),
    ("Entertainment", "debit", ["netflix", "spotify", "hotstar", "prime video", "bookmyshow", "youtube",
                                "sonyliv", "zee5", "jiocinema", "gaana"]),
    ("Bills & Utilities", "debit", ["electricity", "bescom", "tneb", "msedcl", "airtel", "jio", "vodafone",
                                    "bsnl", "fibernet", "tata play", "broadband", "water board", "recharge",
                                    "dth", "gas bill", "piped gas"]),
    ("Rent & Housing", "debit", ["rent", "nobroker", "housing society", "society maintenance"]),
    ("Health", "debit", ["pharmacy", "apollo", "medplus", "1mg", "pharmeasy", "hospital", "clinic",
                         "diagnostic", "netmeds", "lab"]),
    ("Education", "debit", ["udemy", "coursera", "byju", "unacademy", "school", "college", "tuition"]),
]


def _compile(keyword: str) -> Pattern[str]:
    parts = [re.escape(p) for p in keyword.upper().split()]
    return re.compile(r"(?<![A-Z0-9])" + r"\s+".join(parts) + r"(?![A-Z0-9])")


def load_rules(path: Optional[str]) -> Dict[str, List[str]]:
    """JSON file: {"Category": ["keyword", ...]}. Custom rules win over built-ins."""
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not all(isinstance(v, list) for v in data.values()):
        raise ValueError('rules file must look like {"Category": ["keyword", ...]}')
    return data


class Categorizer:
    def __init__(self, custom: Optional[Dict[str, Iterable[str]]] = None):
        self._rules: List[Tuple[str, Optional[str], List[Pattern[str]]]] = []
        for cat, kws in (custom or {}).items():
            self._rules.append((cat, None, [_compile(k) for k in kws]))
        for cat, side, kws in BUILTIN_RULES:
            self._rules.append((cat, side, [_compile(k) for k in kws]))

    def categorize(self, tx: Transaction) -> str:
        text = f"{tx.description} {tx.counterparty}".upper()
        is_credit = bool(tx.credit) and not tx.debit
        for cat, side, pats in self._rules:
            if side == "credit" and not is_credit:
                continue
            if side == "debit" and is_credit:
                continue
            if any(p.search(text) for p in pats):
                return cat
        if tx.type in ("NEFT", "IMPS", "RTGS"):
            return "Transfers"
        return "Uncategorized"
