"""Turn raw narration strings into (type, counterparty, reference)."""
from __future__ import annotations

import re
from typing import Optional, Tuple

_TYPES = [
    ("UPI", re.compile(r"\bUPI\b")),
    ("IMPS", re.compile(r"\bIMPS\b")),
    ("NEFT", re.compile(r"\bNEFT\b")),
    ("RTGS", re.compile(r"\bRTGS\b")),
    ("ATM", re.compile(r"\bATM\b|\bNWD\b|\bCASH\s+(WDL|WITHDRAWAL)\b|\bSELF\s+WITHDRAWAL\b")),
    ("POS", re.compile(r"\bPOS\b|\bPCD\b|\bECOM\b|\bVPS\b")),
    ("ACH", re.compile(r"\bACH\b|\bNACH\b|\bECS\b|\bSI\b")),
    ("CHEQUE", re.compile(r"\bCHQ\b|\bCHEQUE\b|\bCLG\b|\bCLEARING\b")),
    ("INTEREST", re.compile(r"\bINTEREST\b|\bINT\.?\s?(PD|CR|CREDIT|PAID)\b")),
    ("CHARGES", re.compile(r"\bCHARGES?\b|\bCHRG\b|\bCHG\b|\bSMS\s+ALERT\b|\bAMC\b")),
]
_NOT_NAME = {
    "UPI", "DR", "CR", "P2A", "P2M", "P2P", "IMPS", "NEFT", "RTGS", "PAYMENT", "TRANSFER", "FROM", "TO", "BY",
    "PAID", "SENT", "RECEIVED", "UPIAR", "UPIAB", "MOB", "INB", "IB", "TPT", "FUND", "FUNDS", "ACH", "NACH",
}
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_REF12 = re.compile(r"^\d{12}$")
_SPLIT = re.compile(r"[-/]")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def classify_type(description: str) -> str:
    upper = description.upper()
    for name, pattern in _TYPES:
        if pattern.search(upper):
            return name
    return "OTHER"


def _looks_like_name(tok: str) -> bool:
    t = tok.strip()
    if len(t) < 3 or t.upper() in _NOT_NAME:
        return False
    if "@" in t or _IFSC.match(t.upper()):
        return False
    letters = sum(c.isalpha() for c in t)
    return letters >= 3 and letters >= 0.6 * len(t)


def _title(name: str) -> str:
    name = name.strip(" .-")
    return name.title() if name.isupper() else name


def extract_counterparty(description: str, tx_type: str) -> Tuple[str, str]:
    """Best-effort (counterparty, reference). Heuristic: formats differ per bank."""
    # printed narrations are often wrapped in the middle of a number: "4123 45678901"
    text = re.sub(r"(?<=\d) (?=\d)", "", clean(description))
    toks = [t.strip() for t in _SPLIT.split(text) if t.strip()]
    ref = next((t for t in toks if _REF12.match(t)), "")
    if tx_type == "UPI":
        ref_idx = next((i for i, t in enumerate(toks) if _REF12.match(t)), None)
        vpa_idx = next((i for i, t in enumerate(toks) if "@" in t), None)
        # UPI/DR/<ref>/<NAME>/<BANK>/<vpa>/..  : the name follows the reference
        if ref_idx is not None and (vpa_idx is None or ref_idx < vpa_idx):
            for t in toks[ref_idx + 1 : ref_idx + 3]:
                if _looks_like_name(t):
                    return _title(t), ref
        # UPI-<NAME>-<vpa>-<IFSC>-<ref>-..    : the name precedes the VPA
        if vpa_idx is not None:
            if vpa_idx > 0 and _looks_like_name(toks[vpa_idx - 1]):
                return _title(toks[vpa_idx - 1]), ref
            return toks[vpa_idx].split("@")[0], ref
        return "", ref
    if tx_type in ("NEFT", "IMPS", "RTGS"):
        for t in toks[1:]:
            if _looks_like_name(t) and not re.search(r"\d{6,}", t):
                return _title(t), ref
        return "", ref
    return "", ref
