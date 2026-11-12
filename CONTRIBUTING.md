# Contributing

Thank you for helping. The most useful contributions are **false alarms and missed problems on real papers**: open an
issue with the arXiv id (or a minimal LaTeX snippet), the line paper-proof reported or missed, and what it should
have said.

## Where things are

| | |
|---|---|
| `bib.py`, `latex.py`, `pdf.py`, `arxiv_source.py` | reading the inputs: BibTeX, LaTeX projects (`\input`, citations, `.bbl`), PDFs, arXiv sources |
| `tables.py` | LaTeX tables as data (rows, groups, numbers, bold, which way a column is better) |
| `checks/` | the paper against itself, one module per check (`bold`, `changes`, `stale`, `averages`, `labels`; shared helpers in `common`); `numbers.py` runs them all |
| `transport.py`, `sources.py`, `match.py`, `check.py` | the reference checks: polite HTTP and its cache, the four databases, comparing a reference with a record, the verdict |
| `report.py`, `cli.py` | terminal, JSON and Markdown reports; the command line |

## Development

```bash
uv sync
uv run pytest -q        # never reaches the network: database answers are recorded in tests/fixtures
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

- A new rule for the number checks comes with a test built from the real case that motivated it (a few lines of
  LaTeX are enough), and the measurement still passes: fetch the sources of `scripts/papers.txt` with
  `scripts/fetch_arxiv_sources.py` (into a folder outside this repository), then run `scripts/measure_offline.py`
  (findings on real papers: each must be real) and `scripts/inject_errors.py` (injected errors found).
- A change to the reference checks: record the databases' answers with `scripts/record_fixtures.py` and add the case
  to `tests/fixtures/references.bib`.
- Never commit papers' sources or PDFs: only their ids.
