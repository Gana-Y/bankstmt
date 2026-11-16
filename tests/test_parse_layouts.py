from decimal import Decimal as D

import pytest

from bankstmt import LayoutNotFoundError, PasswordError, parse_pdf


@pytest.mark.parametrize("layout", ["a", "b", "c", "d"])
def test_every_layout_matches_ground_truth(pdfs, truth, layout):
    stmt = parse_pdf(pdfs[layout])
    assert len(stmt.transactions) == len(truth)
    for tx, (d, narr, ref, dr, cr, bal) in zip(stmt.transactions, truth):
        assert tx.date == d
        assert tx.debit == dr, (tx.description, tx.debit, dr)
        assert tx.credit == cr, (tx.description, tx.credit, cr)
        assert tx.balance == bal
        # narration survives wrapping (compare ignoring spaces)
        assert "".join(" ".join(narr).split()) == "".join(tx.description.split())


@pytest.mark.parametrize("layout", ["a", "b", "c", "d"])
def test_running_balance_reconciles(pdfs, layout):
    stmt = parse_pdf(pdfs[layout])
    assert stmt.mismatched_rows == 0
    assert stmt.checked_rows >= 13


def test_newest_first_statement_is_reordered(pdfs):
    stmt = parse_pdf(pdfs["c"])
    assert stmt.reversed_order
    dates = [t.date for t in stmt.transactions]
    assert dates == sorted(dates)


def test_single_amount_column_with_dr_cr(pdfs):
    stmt = parse_pdf(pdfs["c"])
    salary = next(t for t in stmt.transactions if "SALARY" in t.description)
    assert salary.credit == D("85000.00") and salary.debit is None
    assert not any(t.direction_guessed for t in stmt.transactions)


def test_indian_digit_grouping_and_amount_in_narration(pdfs):
    stmt = parse_pdf(pdfs["a"])
    big = next(t for t in stmt.transactions if "AMAZON" in t.description)
    assert big.debit == D("123456.00")  # printed as 1,23,456.00
    # "RS 500.00" inside a narration must not become an amount
    elec = next(t for t in stmt.transactions if "BESCOM" in t.description)
    assert elec.debit == D("1250.50") and "RS 500.00" in elec.description


def test_split_dates_and_value_date(pdfs):
    stmt = parse_pdf(pdfs["b"])  # "1 Apr 2024" is three PDF words
    assert stmt.transactions[0].date.isoformat() == "2024-04-01"
    assert stmt.transactions[0].value_date.isoformat() == "2024-04-01"


def test_table_continues_on_page_without_repeated_header(pdfs):
    stmt = parse_pdf(pdfs["b"])
    assert {t.page for t in stmt.transactions} == {1, 2}


def test_footer_and_summary_are_not_transactions(pdfs):
    for key in ("a", "b", "d"):
        stmt = parse_pdf(pdfs[key])
        assert len(stmt.transactions) == 14
        assert all("SUMMARY" not in t.description.upper() for t in stmt.transactions)
    assert "End of Statement" not in parse_pdf(pdfs["b"]).transactions[-1].description


def test_opening_balance_line(pdfs):
    assert parse_pdf(pdfs["d"]).opening_balance == D("100000.00")


def test_missing_row_is_flagged_by_balance_check(pdfs):
    stmt = parse_pdf(pdfs["dropped"])
    assert len(stmt.transactions) == 13
    assert stmt.mismatched_rows == 1
    assert any("Balance mismatch" in w for w in stmt.warnings)


def test_password_protected(pdfs):
    with pytest.raises(PasswordError, match="password"):
        parse_pdf(pdfs["protected"])
    with pytest.raises(PasswordError, match="Wrong"):
        parse_pdf(pdfs["protected"], password="nope")
    stmt = parse_pdf(pdfs["protected"], password="demo1234")
    assert len(stmt.transactions) == 14


def test_bank_detection(pdfs):
    assert parse_pdf(pdfs["named_hdfc"]).bank == "HDFC Bank"
    assert parse_pdf(pdfs["named_sbi"]).bank == "State Bank of India"
    assert parse_pdf(pdfs["a"]).bank == "Unknown"
    assert parse_pdf(pdfs["a"], bank="My Bank").bank == "My Bank"


def test_non_statement_pdf_gives_helpful_error(tmp_path):
    from reportlab.pdfgen import canvas

    path = str(tmp_path / "x.pdf")
    c = canvas.Canvas(path)
    c.drawString(100, 700, "Just a letter, no table here")
    c.save()
    with pytest.raises(LayoutNotFoundError, match="inspect"):
        parse_pdf(path)


def test_blank_pdf_mentions_scanned(tmp_path):
    from reportlab.pdfgen import canvas

    path = str(tmp_path / "blank.pdf")
    c = canvas.Canvas(path)
    c.showPage()
    c.save()
    with pytest.raises(LayoutNotFoundError, match="scanned"):
        parse_pdf(path)
