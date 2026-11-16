# Contributing to bankstmt

Thanks for helping! Small PRs are the best PRs.

## Dev setup

```bash
git clone https://github.com/Gana-Y/bankstmt.git
cd bankstmt
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Guidelines

- Add or update tests for every behaviour change.
- Keep the public API small and the docs honest: if something is a heuristic, say so.
- Open an issue first for big changes so we can agree on the approach.

## The most valuable contribution: a layout that fails

Bank PDFs differ a lot. If your statement does not parse:

1. Run `bankstmt inspect your.pdf`. It prints only column names and positions, no personal data.
2. Open an issue with that output and what went wrong (which column is mixed up, which rows are missing).
3. **Never attach a real statement.** If you can, share a redacted or synthetic PDF reproducing the layout.
   `tests/samples.py` shows how to generate one with ReportLab in a few lines.

By contributing you agree that your contribution is released under the MIT License.
