r"""Checks that need no database: the paper against itself.

- A bold (or underlined) number in a table that is not the best in its column, nor in its group of rows.
- "from A to B, a p% improvement": p recomputed from A and B, as a relative change or in points, within rounding.
- A result in the abstract that appears nowhere else: not in the text, not in a table, and not a difference or a
  relative change between two numbers of the same table column.
- \ref to a label that does not exist (prints as ??), a label defined twice, a table or figure never referred to.

Every finding says where it is (file and line) and what it was compared with, so it can be checked by hand.
"""

from __future__ import annotations

import re

from .checks.averages import AVERAGE_HEADER, NOT_AVERAGED, average_columns, average_rows  # noqa: F401
from .checks.bold import (  # noqa: F401
    OTHER_MEANING,
    _better,
    _bold_not_best_by_row,
    _diagonal,
    _marks_extremes,
    _row_cells,
    _row_oriented,
    _want,
    bold_not_best,
    caption_direction,
)
from .checks.changes import _NUM, _UNIT, CHANGE_WORD, FROM_TO, PERCENT, TIMES, WINDOW, _is_year, change_claims  # noqa: F401
from .checks.common import DELTA_CONTEXT, SEVERITY_ORDER, Finding, _dec, _derived, _interval, _is_best, _sentence, _shown, _table_numbers, _tol  # noqa: F401
from .checks.labels import CONDITIONAL, FLOAT, LABEL, REF, conditional_spans, labels, refs_in  # noqa: F401
from .checks.stale import ABSTRACT, _abstract, abstract_numbers, table_mentions  # noqa: F401
from .tables import find_tables


def check_numbers(texts: dict[str, str]) -> list[Finding]:
    tables = [t for f, text in texts.items() for t in find_tables(text, f)]
    out: list[Finding] = []
    for t in tables:
        out += bold_not_best(t)
        out += average_columns(t)
    for f, text in texts.items():
        # tables and equations blanked out (line breaks kept): their numbers are not claims in prose
        blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
        body = re.sub(r"\\begin\{(tabular\*?|tabularx|longtable|equation\*?|align\*?)\}.*?\\end\{\1\}", blank, text, flags=re.S)
        out += change_claims(body, f, lambda pos, text=text: text.count("\n", 0, pos) + 1)
    out += abstract_numbers(texts, tables)
    out += table_mentions(texts, tables)
    out += labels(texts)
    return sorted(out, key=lambda x: (SEVERITY_ORDER.index(x.severity), x.file, x.line))
