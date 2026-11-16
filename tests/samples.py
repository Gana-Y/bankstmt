"""Generate SYNTHETIC statement PDFs that imitate common Indian bank layouts.

All names, numbers and merchants are made up. Used by the test-suite and to create
the demo files in ``examples/``.  Run:  python tests/samples.py examples
"""
from __future__ import annotations

import os
import sys
import textwrap
from datetime import date
from decimal import Decimal as D

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

W, H = A4
FONT, SIZE, LEAD = "Helvetica", 8, 13
W_A = 34   # characters per narration line in layout A (kept inside the column)


def wrap(narr, width):
    return textwrap.wrap(" ".join(narr), width) or [""]


def indian(x: D) -> str:
    """1234567.5 -> 12,34,567.50"""
    s = f"{x:.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return f"{whole}.{frac}"


# ground truth shared by all layouts: (date, narration lines, ref, debit, credit)
TXNS = [
    (date(2024, 4, 1), ["UPI-SWIGGY-SWIGGY@ICICI-ICIC0000001-412345678901-PAYMENT FOR ORDER"], "0000412345678901", D("450.00"), None),
    (date(2024, 4, 2), ["NEFT CR-HDFC0001234-ACME TECHNOLOGIES PVT LTD-SALARY APR", "2024 SAL CREDIT"], "N092401234567", None, D("85000.00")),
    (date(2024, 4, 3), ["ATM WDL-ATM CASH 0123 BENGALURU"], "0000000012345", D("5000.00"), None),
    (date(2024, 4, 5), ["PAYMENT OF RS 500.00 TO ELECTRICITY BESCOM"], "0000555500001", D("1250.50"), None),
    (date(2024, 4, 8), ["UPI/DR/412399887766/ZOMATO/HDFC/zomato@hdfcbank/Food order"], "412399887766", D("389.00"), None),
    (date(2024, 4, 9), ["IMPS-409912345678-RAHUL KUMAR-HDFC-xxxxxx1234-RENT SHARE"], "409912345678", None, D("12000.00")),
    (date(2024, 4, 12), ["ACH D- BAJAJ FINANCE EMI LOAN 12345"], "ACH0012345", D("14500.00"), None),
    (date(2024, 4, 15), ["INT.PD:01-01-2024 TO 31-03-2024"], "", None, D("312.75")),
    (date(2024, 4, 18), ["POS 4567XXXXXXXX1234 AMAZON PAY INDIA"], "0000777788889", D("1,23,456.00".replace(",", "")), None),
    (date(2024, 4, 20), ["UPI-PRIYA SHARMA-PRIYA@OKAXIS-UTIB0000001-412311223344-DINNER SPLIT"], "0000412311223344", None, D("1,50,000.00".replace(",", ""))),
    (date(2024, 4, 22), ["SMS ALERT CHARGES Q1 FY25"], "", D("17.70"), None),
    (date(2024, 4, 25), ["UPI-NETFLIX-NETFLIX@AXISBANK-UTIB0000002-412300000001-MONTHLY PLAN"], "0000412300000001", D("649.00"), None),
    (date(2024, 4, 28), ["NEFT DR-ICIC0000001-RAMESH ENTERPRISES-INVOICE 118"], "N092404280001", D("22000.00"), None),
    (date(2024, 5, 2), ["UPI-UBER INDIA-UBER@YBL-YESB0000001-412300000777-TRIP"], "0000412300000777", D("231.00"), None),
]
OPENING = D("100000.00")


def with_balances(txns, opening=OPENING):
    out, bal = [], opening
    for d, narr, ref, dr, cr in txns:
        bal = bal - (dr or 0) + (cr or 0)
        out.append((d, narr, ref, dr, cr, bal))
    return out


class Pdf:
    def __init__(self, path, password=None):
        kw = {"encrypt": password} if password else {}
        self.c = canvas.Canvas(path, pagesize=A4, **kw)
        self.y = H - 60
        self.page_no = 1

    def text(self, x, s, right=False, bold=False, size=SIZE, centre=False):
        self.c.setFont("Helvetica-Bold" if bold else FONT, size)
        if right:
            self.c.drawRightString(x, self.y, s)
        elif centre:
            self.c.drawCentredString(x, self.y, s)
        else:
            self.c.drawString(x, self.y, s)

    def down(self, n=1):
        self.y -= LEAD * n

    def new_page(self):
        self.c.showPage()
        self.y = H - 60
        self.page_no += 1

    def save(self):
        self.c.save()


def _header_block(p, bank_line):
    p.text(40, bank_line, bold=True, size=12)
    p.down(1.3)
    p.text(40, "Statement of Account  -  Sample Customer (SYNTHETIC DATA)")
    p.down()
    p.text(40, "Account No: XXXXXX1234    Period: 01/04/2024 to 02/05/2024")
    p.down(2)


def layout_a(path, password=None, bank_line="SAMPLE BANK LIMITED", per_page=8, drop_index=None):
    """HDFC-like: dd/mm/yy, Chq./Ref.No., Value Dt, Withdrawal Amt., Deposit Amt., Closing Balance."""
    p = Pdf(path, password)
    X = dict(date=40, narr=95, ref=285, vdate=355, dr=455, cr=515, bal=587)  # dr/cr/bal are right edges
    rows = with_balances(TXNS)
    _header_block(p, bank_line)

    def header():
        p.text(X["date"], "Date", bold=True); p.text(X["narr"], "Narration", bold=True)
        p.text(X["ref"], "Chq./Ref.No.", bold=True); p.text(X["vdate"], "Value Dt", bold=True)
        p.text(X["dr"], "Withdrawal Amt.", bold=True, right=True)
        p.text(X["cr"], "Deposit Amt.", bold=True, right=True)
        p.text(X["bal"], "Closing Balance", bold=True, right=True)
        p.down(1.5)

    header()
    count = 0
    for idx, (d, narr, ref, dr, cr, bal) in enumerate(rows):
        if idx == drop_index:   # simulate a row the parser could miss
            continue
        if count and count % per_page == 0:
            p.text(300, f"Page {p.page_no} of 2", centre=True); p.new_page(); header()
        lines = wrap(narr, W_A)
        p.text(X["date"], d.strftime("%d/%m/%y"))
        p.text(X["narr"], lines[0])
        p.text(X["ref"], ref[-14:]); p.text(X["vdate"], d.strftime("%d/%m/%y"))
        if dr: p.text(X["dr"], indian(dr), right=True)
        if cr: p.text(X["cr"], indian(cr), right=True)
        p.text(X["bal"], indian(bal), right=True)
        p.down()
        # wrapped narration
        for ln in lines[1:]:
            p.text(X["narr"], ln); p.down()
        count += 1
    p.down(1)
    p.text(40, "STATEMENT SUMMARY :-", bold=True); p.down()
    p.text(40, "Opening Balance   Dr Count   Cr Count   Debits   Credits   Closing Bal"); p.down()
    p.text(40, "100,000.00   9   5   999,999.99   999,999.99   1.00")
    p.down(2)
    p.text(40, "Generated On: 03/05/2024  This is a computer generated statement.")
    p.save()


MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def layout_b(path, bank_line="SAMPLE GRAMIN BANK"):
    """SBI-like: 'dd Mon yyyy' dates (3 words), two-line header, no repeated header on page 2."""
    p = Pdf(path)
    X = dict(date=35, vdate=95, desc=150, ref=330, dr=445, cr=500, bal=560)
    rows = with_balances(TXNS)
    _header_block(p, bank_line)
    p.text(X["date"], "Txn Date", bold=True); p.text(X["vdate"], "Value Date", bold=True)
    p.text(X["desc"], "Description", bold=True); p.text(X["ref"], "Ref No./", bold=True)
    p.text(X["dr"], "Debit", bold=True, right=True); p.text(X["cr"], "Credit", bold=True, right=True)
    p.text(X["bal"], "Balance", bold=True, right=True)
    p.down()
    p.text(X["ref"], "Cheque No.", bold=True)
    p.down(1.5)
    for i, (d, narr, ref, dr, cr, bal) in enumerate(rows):
        if i == 7:
            p.text(300, "Page 1 of 2", centre=True); p.new_page()
            p.text(40, "Account Statement (contd.)"); p.down(2)
        lines = wrap(narr, 34)
        ds = f"{d.day} {MON[d.month-1]} {d.year}"
        p.text(X["date"], ds); p.text(X["vdate"], ds)
        p.text(X["desc"], lines[0]); p.text(X["ref"], ref[-14:])
        if dr: p.text(X["dr"], indian(dr), right=True)
        if cr: p.text(X["cr"], indian(cr), right=True)
        p.text(X["bal"], indian(bal), right=True)
        p.down()
        for ln in lines[1:]:
            p.text(X["desc"], ln); p.down()
    p.down(1)
    p.text(40, "*** End of Statement ***")
    p.save()


def layout_c(path, bank_line="EXAMPLE CO-OPERATIVE BANK", newest_first=True):
    """Single Amount column + Dr/Cr column, balance with 'Cr' suffix, centred headers, newest first."""
    p = Pdf(path)
    X = dict(date=40, part=120, amt=440, drcr=468, bal=560)
    rows = with_balances(TXNS)
    if newest_first:
        rows = rows[::-1]
    _header_block(p, bank_line)
    p.text(X["date"] + 20, "Date", bold=True, centre=True)
    p.text(X["part"] + 80, "Particulars", bold=True, centre=True)
    p.text(X["amt"] - 22, "Amount", bold=True, centre=True)
    p.text(X["drcr"] + 8, "Dr/Cr", bold=True, centre=True)
    p.text(X["bal"] - 30, "Balance", bold=True, centre=True)
    p.down(1.5)
    for d, narr, ref, dr, cr, bal in rows:
        lines = wrap(narr, 48)
        p.text(X["date"], f"{d.day:02d}-{MON[d.month-1]}-{d.year}")
        p.text(X["part"], lines[0])
        p.text(X["amt"], indian(dr or cr), right=True)
        p.text(X["drcr"], "Dr" if dr else "Cr")
        p.text(X["bal"], indian(bal) + " Cr", right=True)
        p.down()
        for ln in lines[1:]:
            p.text(X["part"], ln); p.down()
    p.save()


def layout_d(path, bank_line="DEMO PRIVATE BANK"):
    """Bracketed headers, dd-mm-yyyy dates, lakh/crore grouping, Opening Balance line."""
    p = Pdf(path)
    X = dict(date=40, rem=105, dr=430, cr=495, bal=562)
    rows = with_balances(TXNS)
    _header_block(p, bank_line)
    p.text(X["date"], "Tran Date", bold=True); p.text(X["rem"], "Transaction Remarks", bold=True)
    p.text(X["dr"], "Withdrawals (Dr)", bold=True, right=True)
    p.text(X["cr"], "Deposits (Cr)", bold=True, right=True)
    p.text(X["bal"], "Balance (INR)", bold=True, right=True)
    p.down(1.5)
    p.text(X["rem"], "Opening Balance"); p.text(X["bal"], indian(OPENING), right=True); p.down()
    for d, narr, ref, dr, cr, bal in rows:
        lines = wrap(narr, 50)
        p.text(X["date"], d.strftime("%d-%m-%Y")); p.text(X["rem"], lines[0])
        if dr: p.text(X["dr"], indian(dr), right=True)
        if cr: p.text(X["cr"], indian(cr), right=True)
        p.text(X["bal"], indian(bal), right=True)
        p.down()
        for ln in lines[1:]:
            p.text(X["rem"], ln); p.down()
    p.down()
    p.text(40, "Closing Balance"); p.text(X["bal"], indian(rows[-1][-1]), right=True)
    p.save()


def bank_name_page(path, name):
    """A tiny layout-A statement whose letterhead names a real bank (for bank detection tests)."""
    layout_a(path, bank_line=name)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    layout_a(f"{out}/sample_layout_a.pdf")
    layout_b(f"{out}/sample_layout_b.pdf")
    layout_c(f"{out}/sample_layout_c.pdf")
    layout_d(f"{out}/sample_layout_d.pdf")
    layout_a(f"{out}/sample_protected.pdf", password="demo1234")
    print("wrote sample PDFs to", out)
