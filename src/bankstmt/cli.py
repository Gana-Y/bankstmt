"""Command line interface."""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import List, Optional

from . import __version__
from .categorize import load_rules
from .export import to_csv, to_json, to_xlsx
from .layout import find_header, group_lines
from .models import BankstmtError
from .parse import _read_pages, parse_many, parse_pdf
from .summary import format_summary


def _password(args) -> Optional[str]:
    if getattr(args, "ask_password", False):
        return getpass.getpass("PDF password: ")
    return args.password or os.environ.get("BANKSTMT_PASSWORD")


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("files", nargs="+", help="one or more statement PDFs")
    p.add_argument("--password", help="PDF password (or set BANKSTMT_PASSWORD)")
    p.add_argument("--ask-password", action="store_true", help="prompt for the password (keeps it out of shell history)")
    p.add_argument("--bank", help="override the detected bank name")
    p.add_argument("--rules", help='JSON file with extra categories: {"Category": ["keyword", ...]}')
    p.add_argument("--no-categorize", action="store_true", help="skip category guessing")


def _load(args):
    kw = dict(
        password=_password(args),
        bank=args.bank,
        categorize=not args.no_categorize,
        rules=load_rules(args.rules),
    )
    return parse_pdf(args.files[0], **kw) if len(args.files) == 1 else parse_many(args.files, **kw)


def cmd_parse(args) -> int:
    stmt = _load(args)
    fmt = args.format
    out = args.output
    if not fmt:
        ext = os.path.splitext(out)[1].lower() if out else ""
        fmt = {".json": "json", ".xlsx": "xlsx"}.get(ext, "csv")
    if fmt == "xlsx":
        if not out:
            print("--format xlsx needs -o FILE.xlsx", file=sys.stderr)
            return 2
        to_xlsx(stmt, out)
    else:
        text = to_json(stmt, args.date_format) if fmt == "json" else to_csv(stmt, args.date_format)
        if out:
            with open(out, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        else:
            sys.stdout.write(text)
    log = sys.stderr
    print(f"{stmt.bank}: {len(stmt.transactions)} transactions" + (f" -> {out}" if out else ""), file=log)
    if stmt.checked_rows:
        ok = stmt.checked_rows - stmt.mismatched_rows
        print(f"balance check: {ok}/{stmt.checked_rows} rows reconcile", file=log)
    for w in stmt.warnings[:10]:
        print(f"warning: {w}", file=log)
    return 0 if not stmt.mismatched_rows else 3


def cmd_summary(args) -> int:
    print(format_summary(_load(args)))
    return 0


def cmd_inspect(args) -> int:
    """Debug aid: show how the table header was understood. Safe to paste in a bug report."""
    pages = _read_pages(args.files[0], _password(args))
    for page_no, words, _ in pages:
        lines = group_lines(words, page_no)
        found = False
        for i in range(len(lines)):
            hit = find_header(lines, i)
            if hit:
                layout, _n = hit
                print(f"page {page_no}: header columns -> {layout.describe()}")
                found = True
                break
        if not found:
            print(f"page {page_no}: no header (reusing earlier layout) - {len(lines)} text lines")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="bankstmt", description="Indian bank statement PDF -> CSV/JSON/Excel (local only).")
    parser.add_argument("--version", action="version", version=f"bankstmt {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("parse", help="convert statement(s) to CSV/JSON/XLSX")
    _add_common(p)
    p.add_argument("-o", "--output", help="output file (default: CSV to stdout)")
    p.add_argument("-f", "--format", choices=["csv", "json", "xlsx"])
    p.add_argument("--date-format", default="%Y-%m-%d", help="strftime format for dates (default ISO)")
    p.set_defaults(fn=cmd_parse)

    p = sub.add_parser("summary", help="monthly cash-flow and spending by category")
    _add_common(p)
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("inspect", help="show detected table columns (for debugging / bug reports)")
    p.add_argument("files", nargs=1)
    p.add_argument("--password")
    p.add_argument("--ask-password", action="store_true")
    p.set_defaults(fn=cmd_inspect)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except BankstmtError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
