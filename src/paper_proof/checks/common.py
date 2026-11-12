"""What the number checks share: findings, rounding tolerances, and recomputing a difference or a change."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass

from ..tables import NUMBER, Table


@dataclass
class Finding:
    kind: str  # bold-not-best | wrong-change | abstract-number | undefined-ref | duplicate-label | unreferenced
    severity: str  # error | warning | note
    file: str
    line: int
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


SEVERITY_ORDER = ["error", "warning", "note"]


def _tol(decimals: int) -> float:
    return 0.5 * 10**-decimals + 1e-9


def _shown(c) -> str:
    return f"{c.num:.{c.decimals}f}"


def _is_best(v: float, cells, want: str) -> bool:
    values = [c.num for c in cells]
    tol = max((_tol(c.decimals) for c in cells), default=0)
    hi, lo = max(values), min(values)
    if want == "higher":
        return v >= hi - tol
    if want == "lower":
        return v <= lo + tol
    return v >= hi - tol or v <= lo + tol


def _dec(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def _interval(f, a: float, ea: float, b: float, eb: float) -> tuple[float, float]:
    vals = [f(x, y) for x in (a - ea, a + ea) for y in (b - eb, b + eb) if x != 0]
    return (min(vals), max(vals)) if vals else (float("-inf"), float("inf"))


DELTA_CONTEXT = re.compile(
    r"\bby\b|improv|gain|increas|boost|outperform|better|higher|lower|reduc|decreas|\bover\b|above|ahead|margin|\+|"
    r"surpass|relative|absolute|points?\b|\bpp\b|faster|speed|fewer|less|more than|times|×|\\times|beat|exceed",
    re.I,
)


def _table_numbers(t: Table) -> list[tuple[float, int]]:
    """Every number a table shows, in any cell (spreads and deltas too) or in its caption."""
    texts = [c.raw for r in t.rows for c in r] + [t.caption]
    return [(float(x.replace(",", "")), _dec(x.replace(",", ""))) for s in texts for x in NUMBER.findall(s.replace("−", "-"))]


def _sentence(text: str, pos: int) -> tuple[int, int]:
    """The sentence around a position: from the previous sentence end (or blank line) to the next, at most 400
    characters each way."""
    lo = max(pos - 400, max(text.rfind(x, 0, pos) for x in (". ", ".\n", "\n\n")) + 1)
    ends = [x for x in (text.find(". ", pos), text.find(".\n", pos), text.find("\n\n", pos)) if x >= 0]
    return lo, min([pos + 400] + ends)


def _derived(x: float, ex: float, columns, unit: str) -> bool:
    """x as a difference (in points), a relative change (only for a percentage) or a ratio (only for "N×") of two
    numbers of one table column. Differences only from columns at least as precise as x: 12 - 10 in a column of
    whole hours says nothing about a claimed 1.8."""
    need = round(-math.log10(ex * 2)) if ex > 0 else 0  # the decimals x is shown with
    for col in columns:
        precise = min((c.decimals for c in col), default=0) >= need
        for c in col:
            for d in col:
                if c is d or c.value is None or d.value is None:
                    continue
                if unit == "times":
                    if c.num > 0 and d.num > 0 and abs(c.num / d.num - x) <= ex + 0.01 * x:
                        return True
                    continue
                if precise and abs(abs(c.num - d.num) - x) <= _tol(c.decimals) + _tol(d.decimals) + ex:
                    return True
                if unit == "percent" and d.num:
                    lo, hi = _interval(lambda u, v: abs(v - u) / abs(u) * 100, d.num, _tol(d.decimals), c.num, _tol(c.decimals))
                    if lo - ex <= x <= hi + ex:
                        return True
    return False
