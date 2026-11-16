from datetime import date
from decimal import Decimal as D

import pytest

from bankstmt.categorize import Categorizer
from bankstmt.layout import classify_header
from bankstmt.models import Transaction
from bankstmt.narration import classify_type, extract_counterparty
from bankstmt.values import is_amount_token, is_date_token, parse_amount, parse_date


@pytest.mark.parametrize(
    "text,expected",
    [
        ("01/04/24", date(2024, 4, 1)),
        ("01/04/2024", date(2024, 4, 1)),
        ("01-04-2024", date(2024, 4, 1)),
        ("1 Apr 2024", date(2024, 4, 1)),
        ("01-Apr-24", date(2024, 4, 1)),
        ("01 April 2024", date(2024, 4, 1)),
        ("2024-04-01", date(2024, 4, 1)),
        ("05/04/2024 14:32:11", date(2024, 4, 5)),
        ("31/02/2024", None),
        ("hello", None),
        ("", None),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_date_token():
    assert is_date_token("01/04/24") and is_date_token("01-Apr-2024")
    assert not is_date_token("Apr") and not is_date_token("1,000.00")


@pytest.mark.parametrize(
    "text,value,suffix",
    [
        ("1,23,456.78", D("123456.78"), None),
        ("500.00", D("500.00"), None),
        ("12,345.67Cr", D("12345.67"), "Cr"),
        ("12,345.67 DR", D("12345.67"), "Dr"),
        ("-250.00", D("-250.00"), None),
        ("(250.00)", D("-250.00"), None),
        ("250.00-", D("-250.00"), None),
        ("Rs. 1,000.50", D("1000.50"), None),
        ("₹2,500.00", D("2500.00"), None),
        ("1,00,000", D("100000"), None),
    ],
)
def test_parse_amount(text, value, suffix):
    assert parse_amount(text) == (value, suffix)


def test_reference_numbers_are_not_amounts():
    for t in ["0000412345678901", "412345678901", "N092401234567", "UPI", "2024", "123"]:
        assert not is_amount_token(t), t
        assert parse_amount(t) == (None, None)


@pytest.mark.parametrize(
    "label,key",
    [
        ("Date", "date"), ("Txn Date", "date"), ("Tran Date", "date"), ("Transaction Date", "date"),
        ("Value Dt", "value_date"), ("Value Date", "value_date"),
        ("Narration", "narration"), ("Particulars", "narration"), ("Transaction Remarks", "narration"),
        ("Description", "narration"), ("Transaction Details", "narration"),
        ("Chq./Ref.No.", "ref"), ("Ref No./Cheque No.", "ref"),
        ("Withdrawal Amt.", "debit"), ("Withdrawals (Dr)", "debit"), ("Debit", "debit"),
        ("Deposit Amt.", "credit"), ("Credit", "credit"), ("Deposits", "credit"),
        ("Closing Balance", "balance"), ("Balance (INR)", "balance"),
        ("Amount", "amount"), ("Amount (INR)", "amount"),
        ("Dr/Cr", "dr_cr"), ("Sl No", "serial"),
        ("Branch", None),
    ],
)
def test_header_synonyms(label, key):
    assert classify_header(label) == key


def test_classify_type():
    assert classify_type("UPI-SWIGGY-x@icici") == "UPI"
    assert classify_type("NEFT CR-ACME") == "NEFT"
    assert classify_type("ATM WDL-ATM CASH") == "ATM"
    assert classify_type("ACH D- BAJAJ") == "ACH"
    assert classify_type("INT.PD:01-01-2024") == "INTEREST"
    assert classify_type("random text") == "OTHER"


@pytest.mark.parametrize(
    "narr,typ,name,ref",
    [
        ("UPI-SWIGGY-SWIGGY@ICICI-ICIC0000001-412345678901-PAYMENT", "UPI", "Swiggy", "412345678901"),
        ("UPI/DR/412399887766/ZOMATO/HDFC/zomato@hdfcbank/Food", "UPI", "Zomato", "412399887766"),
        ("UPI-PRIYA SHARMA-PRIYA@OKAXIS-UTIB0000001-4123 11223344-DINNER", "UPI", "Priya Sharma", "412311223344"),
        ("IMPS-409912345678-RAHUL KUMAR-HDFC-xxxxxx1234-RENT", "IMPS", "Rahul Kumar", "409912345678"),
        ("NEFT CR-HDFC0001234-ACME PVT LTD-SALARY", "NEFT", "Acme Pvt Ltd", ""),
        ("ATM WDL-ATM CASH 0123", "ATM", "", ""),
    ],
)
def test_counterparty_extraction(narr, typ, name, ref):
    t = classify_type(narr)
    assert t == typ
    assert extract_counterparty(narr, t) == (name, ref)


def _tx(desc, debit=None, credit=None, typ="UPI", cp=""):
    return Transaction(date=date(2024, 1, 1), description=desc, debit=debit, credit=credit, type=typ, counterparty=cp)


def test_categories_builtin():
    c = Categorizer()
    assert c.categorize(_tx("UPI-SWIGGY-x", debit=D(1), cp="Swiggy")) == "Food & Dining"
    assert c.categorize(_tx("SALARY APR", credit=D(1), typ="NEFT")) == "Salary"
    assert c.categorize(_tx("ATM WDL", debit=D(1), typ="ATM")) == "Cash Withdrawal"
    assert c.categorize(_tx("NEFT-JOHN", debit=D(1), typ="NEFT")) == "Transfers"
    assert c.categorize(_tx("something odd", debit=D(1), typ="OTHER")) == "Uncategorized"


def test_category_rules_respect_direction():
    # "salary" only counts for credits
    assert Categorizer().categorize(_tx("SALARY ADVANCE REPAYMENT", debit=D(1), typ="NEFT")) == "Transfers"


def test_word_boundaries_avoid_false_matches():
    # "OLA" must not match inside "COLA"; "JIO" not inside "JIOMART"? (it is a different brand token)
    assert Categorizer().categorize(_tx("UPI-COCA COLA DISTRIBUTOR", debit=D(1))) != "Travel"


def test_custom_rules_win():
    c = Categorizer({"Pets": ["happy tails"]})
    assert c.categorize(_tx("UPI-HAPPY TAILS VET", debit=D(1))) == "Pets"
