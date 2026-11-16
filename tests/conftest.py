import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import samples  # noqa: E402


@pytest.fixture(scope="session")
def pdfs(tmp_path_factory):
    d = tmp_path_factory.mktemp("pdfs")
    out = {}
    for name, fn in [("a", samples.layout_a), ("b", samples.layout_b), ("c", samples.layout_c), ("d", samples.layout_d)]:
        out[name] = str(d / f"{name}.pdf")
        fn(out[name])
    out["protected"] = str(d / "protected.pdf")
    samples.layout_a(out["protected"], password="demo1234")
    out["dropped"] = str(d / "dropped.pdf")
    samples.layout_a(out["dropped"], drop_index=5)
    out["named_hdfc"] = str(d / "hdfc.pdf")
    samples.bank_name_page(out["named_hdfc"], "HDFC BANK LIMITED")
    out["named_sbi"] = str(d / "sbi.pdf")
    samples.bank_name_page(out["named_sbi"], "STATE BANK OF INDIA")
    return out


@pytest.fixture(scope="session")
def truth():
    return samples.with_balances(samples.TXNS)
