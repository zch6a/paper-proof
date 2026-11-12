# Contributing

Thank you for helping. The most useful contributions are **false alarms and missed problems on real papers**: open an
issue with the arXiv id (or a minimal LaTeX snippet), the line paper-proof reported or missed, and what it should
have said.

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
