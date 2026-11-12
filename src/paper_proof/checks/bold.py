"""Bold numbers that are not the best of their column (or of their row, in tables with models in columns)."""

from __future__ import annotations

import re

from ..tables import Table, direction
from .common import Finding, _is_best, _shown

# Captions that give bold another meaning than "the best": statistical ties, "better than the baseline", per-category.
OTHER_MEANING = re.compile(
    r"significan|confidence|overlap|within (?:one|1|two|2)|\bties?\b|indistinguishable|standard (?:error|deviation)|"
    r"top[- ]?(?:2|3|two|three|k)\b|best (?:two|three)|(?:bold|highlight)\w*[^.]{0,60}(?:better|outperform|exceed|improv|above|beat|surpass)",
    re.I,
)


def bold_not_best(t: Table) -> list[Finding]:
    """A bold number that is the only bold one in its column (within its group of rows), yet is not the best in its
    column, its group, or its row. Several bold numbers in one column are left alone: authors mark ties, the best of
    each category, or every result above a baseline, and the table cannot tell which."""
    if re.search(r"\bbold|boldface|highlight|\\textbf\{\s*(?:numbers|results|values)", t.caption, re.I) and OTHER_MEANING.search(t.caption):
        return []
    headers = " ".join(c.text for r in t.rows[: t.header_rows] for c in r)
    if re.search(r"\\Delta|Δ|\bdiff\b|\bgain\b", headers, re.I):
        return []  # a pairwise comparison: bold marks the winner of each pair, not the best of a column
    if _diagonal(t):
        return []  # one bold per row, moving right: a marked setting (train length = test length), not a best
    if _marks_extremes(t):
        return []  # bold marks the largest values even where lower is better: "notable", not "best"
    if _row_oriented(t):
        return _bold_not_best_by_row(t)
    out = []
    ncols = max((len(r) for r in t.rows), default=0)
    for j in range(ncols):
        col = t.column(j)
        if len(col) < 3:
            continue
        want = _want(t, j)
        bolds = [(i, c) for i, c in col if c.bold]
        if not bolds or len(bolds) == len(col):
            continue
        for i, c in bolds:
            group = [(k, d) for k, d in col if t.groups[k] == t.groups[i]]
            if sum(1 for _, d in group if d.bold) > 1:
                continue
            if len(group) == 1 and len(bolds) > 1:
                continue  # a group of one row, other groups have their own bold: best of each category
            if _is_best(c.num, [d for _, d in col], want) or (len(group) > 1 and _is_best(c.num, [d for _, d in group], want)):
                continue
            k, d = _better(c.num, group if len(group) > 2 else col, want)
            header = t.header(j) or f"column {j + 1}"
            if want:
                what = f"{_shown(c)} is bold but {_shown(d)} ({t.row_name(k) or 'row ' + str(k + 1)}) is {want}"
            else:
                values = [x.num for _, x in (group if len(group) > 2 else col)]
                what = f"{_shown(c)} is bold but is neither the highest nor the lowest (they run from {min(values):g} to {max(values):g})"
            out.append(Finding("bold-not-best", "warning", t.file, c.line, f"{t.name}, {header}: {what}"))
    return out


def _row_cells(t: Table, i: int) -> list:
    return [] if t.is_reference(i) else [d for d in t.rows[i][t.row_start(i) :] if d.value is not None]


def _row_oriented(t: Table) -> bool:
    """Bold marks the best of each row (models in columns, datasets or metrics in rows) more often than of each column."""
    by_row = by_col = 0
    for i, r in enumerate(t.rows[t.header_rows :], t.header_rows):
        for j, c in enumerate(r):
            if not c.bold or c.value is None:
                continue
            row = _row_cells(t, i)
            col = [d for _, d in t.column(j)]
            group = [d for k, d in t.column(j) if t.groups[k] == t.groups[i]]
            by_row += len(row) > 2 and _is_best(c.num, row, direction(t.row_name(i)))
            by_col += len(col) > 2 and (_is_best(c.num, col, _want(t, j)) or (len(group) > 1 and _is_best(c.num, group, _want(t, j))))
    body_rows = len(t.rows) - t.header_rows
    # clearly more often, and in a table big enough to tell
    return body_rows >= 3 and by_row >= 3 and by_row > 2 * by_col


def _marks_extremes(t: Table) -> bool:
    agree = against = 0
    for j in range(max((len(r) for r in t.rows), default=0)):
        want = _want(t, j)
        col = [d for _, d in t.column(j)]
        if not want or len(col) < 3:
            continue
        for c in col:
            if c.bold:
                if _is_best(c.num, col, want):
                    agree += 1
                elif _is_best(c.num, col, "lower" if want == "higher" else "higher"):
                    against += 1
    return against >= 2 and against >= agree


def _diagonal(t: Table) -> bool:
    cells = [(i, j) for i, r in enumerate(t.rows[t.header_rows :]) for j, c in enumerate(r) if c.bold and c.value is not None]
    rows, cols = [i for i, _ in cells], [j for _, j in cells]
    return len(cells) >= 3 and len(set(rows)) == len(cells) and len(set(cols)) == len(cells) and cols == sorted(cols) and rows == sorted(rows)


def _want(t: Table, j: int) -> str:
    """Which way column j is better: its header, else what the caption says for the whole table."""
    return direction(t.header(j)) or caption_direction(t.caption)


def caption_direction(caption: str) -> str:
    """What a caption says about the whole table.

    >>> caption_direction("GLUE results. Higher is better for all metrics.")
    'higher'
    """
    hi = re.search(r"higher (?:is|=) better|higher values? (?:is|are) better|\(higher is better\)", caption, re.I)
    lo = re.search(r"lower (?:is|=) better|lower values? (?:is|are) better|\(lower is better\)", caption, re.I)
    return "higher" if hi and not lo else "lower" if lo and not hi else ""


def _bold_not_best_by_row(t: Table) -> list[Finding]:
    out = []
    for i in range(t.header_rows, len(t.rows)):
        row = _row_cells(t, i)
        bolds = [c for c in row if c.bold]
        if len(row) < 3 or len(bolds) != 1:
            continue
        c = bolds[0]
        want = direction(t.row_name(i)) or caption_direction(t.caption)
        if _is_best(c.num, row, want):
            continue
        name = t.row_name(i) or f"row {i + 1}"
        values = [x.num for x in row]
        if want:
            best = max(values) if want == "higher" else min(values)
            what = f"{_shown(c)} is bold but {best:g} in the same row is {want}"
        else:
            what = f"{_shown(c)} is bold but is neither the highest nor the lowest of its row ({min(values):g} to {max(values):g})"
        out.append(Finding("bold-not-best", "warning", t.file, c.line, f"{t.name}, row {name}: {what}"))
    return out


def _better(v: float, col, want: str):
    if want == "lower":
        return min(col, key=lambda kd: kd[1].num)
    if want == "higher":
        return max(col, key=lambda kd: kd[1].num)
    hi = max(col, key=lambda kd: kd[1].num)
    lo = min(col, key=lambda kd: kd[1].num)
    return hi if abs(hi[1].num - v) <= abs(lo[1].num - v) else lo
