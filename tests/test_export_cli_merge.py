import csv
import io
import json
import os
import subprocess
import sys
from decimal import Decimal as D

import pytest

from bankstmt import parse_many, parse_pdf
from bankstmt.export import COLUMNS, to_csv, to_json, to_xlsx
from bankstmt.summary import format_summary, monthly, top_categories


def test_csv_shape_and_signs(pdfs):
    stmt = parse_pdf(pdfs["a"])
    rows = list(csv.DictReader(io.StringIO(to_csv(stmt))))
    assert list(rows[0].keys()) == COLUMNS
    assert rows[0]["date"] == "2024-04-01" and rows[0]["amount"] == "-450.00"
    assert rows[1]["amount"] == "85000.00" and rows[1]["category"] == "Salary"
    assert rows[0]["debit"] == "450.00" and rows[0]["credit"] == ""


def test_custom_date_format(pdfs):
    rows = list(csv.DictReader(io.StringIO(to_csv(parse_pdf(pdfs["a"]), "%d/%m/%Y"))))
    assert rows[0]["date"] == "01/04/2024"


def test_json_document(pdfs):
    doc = json.loads(to_json(parse_pdf(pdfs["d"])))
    assert doc["opening_balance"] == "100000.00"
    assert doc["balance_check"]["mismatches"] == 0
    assert len(doc["transactions"]) == 14
    assert doc["period"] == ["2024-04-01", "2024-05-02"]


def test_xlsx_export(pdfs, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "o.xlsx"
    to_xlsx(parse_pdf(pdfs["a"]), str(out))
    ws = openpyxl.load_workbook(out)["Transactions"]
    assert ws.max_row == 15 and ws["E2"].value == 450.0 and ws["A2"].value.year == 2024


def test_summary_numbers(pdfs):
    stmt = parse_pdf(pdfs["a"])
    m = monthly(stmt)
    assert [x[0] for x in m] == ["2024-04", "2024-05"]
    assert sum(x[1] for x in m) == stmt.total_credits == D("85000") + D("12000") + D("312.75") + D("150000")
    cats = dict(top_categories(stmt))
    assert cats["Shopping"] == D("123456.00")
    text = format_summary(stmt)
    assert "Where the money went" in text and "14/14" not in text and "13/13" in text


def test_merge_dedupes_overlapping_statements(pdfs):
    merged = parse_many([pdfs["a"], pdfs["b"], pdfs["c"]])
    assert len(merged.transactions) == 14  # identical content -> duplicates removed
    dates = [t.date for t in merged.transactions]
    assert dates == sorted(dates)


def _run(*args, env=None, **kw):
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    base_env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if env:
        base_env.update(env)
    existing_pp = base_env.get("PYTHONPATH", "")
    base_env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing_pp}" if existing_pp else src_dir
    return subprocess.run([sys.executable, "-m", "bankstmt", *args], capture_output=True, text=True, env=base_env, **kw)


def test_cli_parse_to_file_and_exit_codes(pdfs, tmp_path):
    out = tmp_path / "x.csv"
    r = _run("parse", pdfs["a"], "-o", str(out))
    assert r.returncode == 0 and "14 transactions" in r.stderr
    assert out.read_text().startswith("date,value_date,description")
    r = _run("parse", pdfs["dropped"], "-o", str(tmp_path / "y.csv"))
    assert r.returncode == 3 and "Balance mismatch" in r.stderr   # non-zero so scripts notice


def test_cli_password_env_and_flag(pdfs):
    assert _run("parse", pdfs["protected"]).returncode == 1
    r = _run("parse", pdfs["protected"], "--password", "demo1234")
    assert r.returncode == 0 and r.stdout.count("\n") == 15
    r = _run("parse", pdfs["protected"], env={"BANKSTMT_PASSWORD": "demo1234"})
    assert r.returncode == 0


def test_cli_json_by_extension_and_summary_and_inspect(pdfs, tmp_path):
    out = tmp_path / "x.json"
    assert _run("parse", pdfs["d"], "-o", str(out)).returncode == 0
    assert json.loads(out.read_text())["bank"] == "Unknown"
    s = _run("summary", pdfs["a"])
    assert s.returncode == 0 and "Money in" in s.stdout
    i = _run("inspect", pdfs["a"])
    assert "date[" in i.stdout and "balance[" in i.stdout


def test_cli_custom_rules_file(pdfs, tmp_path):
    rules = tmp_path / "r.json"
    rules.write_text(json.dumps({"Streaming": ["netflix"]}))
    r = _run("parse", pdfs["a"], "--rules", str(rules))
    assert "Streaming" in r.stdout
    r = _run("parse", pdfs["a"], "--no-categorize")
    assert "Streaming" not in r.stdout and "Food & Dining" not in r.stdout


def test_cli_missing_file_is_clean_error(tmp_path):
    r = _run("parse", str(tmp_path / "nope.pdf"))
    assert r.returncode == 1 and "error:" in r.stderr and "Traceback" not in r.stderr
