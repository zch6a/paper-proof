"""An "Avg" column against the mean of its row."""

from __future__ import annotations

import re
from collections import Counter

from ..tables import Table
from .common import Finding, _shown, _tol

# "Avg", "Average", "Mean score", "Avg. ↑": the whole header (not "Avg doc len", "Mean age", "Avg. # turns")
AVERAGE_HEADER = re.compile(
    r"^\W*(?:avg|average|mean)\.?(?:\s*(?:score|acc\.?|accuracy|perf\.?|performance|result|\(?\\?%\)?|↑|\\uparrow))?\W*$", re.I
)


NOT_AVERAGED = re.compile(r"param|size|#|time|flops|macs|memory|speed|throughput|latency|tokens|steps|epochs|gpu|cost|\bn\b", re.I)


def average_rows(t: Table):
    """For each average column j: (j, rows whose average agrees, [(row, avg cell, mean, n) that disagree])."""
    if not t.header_rows or len(t.rows) - t.header_rows < 3:
        return []
    result = []
    ncols = max((len(r) for r in t.rows), default=0)
    last = t.rows[t.header_rows - 1]
    body = [i for i in range(t.header_rows, len(t.rows)) if not t.is_reference(i)]
    for j in range(1, ncols):
        if j >= len(last) or not AVERAGE_HEADER.match(last[j].text):
            continue
        # the columns averaged: numeric in most body rows, before this one, and not sizes or times
        numeric = [
            k
            for k in range(j)
            if sum(1 for i in body if k < len(t.rows[i]) and t.rows[i][k].value is not None) >= 0.8 * len(body)
            and not NOT_AVERAGED.search(t.header(k))
            and not AVERAGE_HEADER.match(last[k].text if k < len(last) else "")
        ]
        if len(numeric) < 2:
            continue
        # Which of the last n numbers each row averages; the table averages one fixed set, so every row is then
        # judged by the n most rows agree on (otherwise some run of a long row averages to almost anything).
        rows = []
        for i in body:
            row = t.rows[i]
            if j >= len(row) or row[j].value is None or any(k >= len(row) or row[k].value is None for k in numeric):
                continue
            cells = [row[k] for k in numeric]
            avg = row[j]
            tol = _tol(avg.decimals) + max(_tol(c.decimals) for c in cells) + 1e-9
            fits = {n for n in range(2, len(cells) + 1) if abs(sum(c.num for c in cells[-n:]) / n - avg.num) <= tol}
            rows.append((i, avg, cells, fits))
        if not rows:
            continue
        votes = Counter(n for *_, fits in rows for n in fits)
        n_best = max(votes, key=lambda n: (votes[n], n)) if votes else len(numeric)
        agree = [i for i, _, _, fits in rows if n_best in fits]
        disagree = [(i, avg, sum(c.num for c in cells[-n_best:]) / n_best, n_best) for i, avg, cells, fits in rows if n_best not in fits]
        result.append((j, agree, disagree))
    return result


def average_columns(t: Table) -> list[Finding]:
    """An "Avg" / "Average" / "Mean" column: in each row, the mean of the numbers before it (all of them, or the
    last few: an average over one group of tasks), allowing for rounding. Reported only for the rows that disagree
    when most rows agree: a table where few rows agree defines its average some other way (weighted, a subset)."""
    out = []
    last = t.rows[t.header_rows - 1] if t.header_rows else []
    for j, agree_rows, disagree in average_rows(t):
        agree = len(agree_rows)
        if agree >= 2 and 0 < len(disagree) <= max(1, (agree + len(disagree)) // 3):
            for i, avg, mean, n in disagree:
                name = t.row_name(i) or f"row {i + 1}"
                msg = (
                    f"{t.name}, row {name}: {last[j].text} is {_shown(avg)}, but the mean of the {n} numbers before it "
                    f"(the ones the other rows average) is {mean:.{max(avg.decimals, 1) + 1}f}"
                )
                out.append(Finding("average", "warning", t.file, avg.line, msg))
    return out
