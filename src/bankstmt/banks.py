"""Bank name detection (label only; parsing itself is header-driven and bank-agnostic)."""
from __future__ import annotations

import re
from typing import Optional

# most specific first
_BANKS = [
    ("State Bank of India", r"STATE BANK OF INDIA|\bSBI\b"),
    ("HDFC Bank", r"HDFC BANK"),
    ("ICICI Bank", r"ICICI BANK"),
    ("Axis Bank", r"AXIS BANK"),
    ("Kotak Mahindra Bank", r"KOTAK MAHINDRA"),
    ("Punjab National Bank", r"PUNJAB NATIONAL BANK|\bPNB\b"),
    ("Bank of Baroda", r"BANK OF BARODA"),
    ("Canara Bank", r"CANARA BANK"),
    ("Union Bank of India", r"UNION BANK OF INDIA"),
    ("Central Bank of India", r"CENTRAL BANK OF INDIA"),
    ("IDFC FIRST Bank", r"IDFC FIRST"),
    ("Yes Bank", r"YES BANK"),
    ("IndusInd Bank", r"INDUSIND BANK"),
    ("Federal Bank", r"FEDERAL BANK"),
    ("IDBI Bank", r"IDBI BANK"),
    ("RBL Bank", r"RBL BANK"),
    ("Indian Bank", r"INDIAN BANK"),
    ("UCO Bank", r"UCO BANK"),
    ("Karnataka Bank", r"KARNATAKA BANK"),
    ("South Indian Bank", r"SOUTH INDIAN BANK"),
    ("Bandhan Bank", r"BANDHAN BANK"),
    ("AU Small Finance Bank", r"AU SMALL FINANCE"),
    ("Paytm Payments Bank", r"PAYTM PAYMENTS BANK"),
    ("Bank of India", r"(?<!STATE )(?<!UNION )(?<!CENTRAL )BANK OF INDIA"),
]


def detect_bank(text: str) -> Optional[str]:
    upper = text.upper()
    for name, pattern in _BANKS:
        if re.search(pattern, upper):
            return name
    return None
