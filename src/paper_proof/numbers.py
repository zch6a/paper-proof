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
from dataclasses import asdict, dataclass

from .bib import _matching
from .tables import NUMBER, Table, direction, find_tables


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


# ---------------------------------------------------------------- bold that is not best


def bold_not_best(t: Table) -> list[Finding]:
    out = []
    ncols = max((len(r) for r in t.rows), default=0)
    for j in range(ncols):
        col = t.column(j)
        if len(col) < 2:
            continue
        for mark, attr in (("bold", "bold"), ("underlined", "underline")):
            marked = [(i, c) for i, c in col if getattr(c, attr)]
            if not marked or len(marked) == len(col):
                continue
            want = direction(t.header(j))
            for i, c in marked:
                group = [(k, d) for k, d in col if t.groups[k] == t.groups[i]]
                if attr == "bold":
                    if _is_best(c.value, [d for _, d in col], want) or _is_best(c.value, [d for _, d in group], want):
                        continue
                else:
                    # underlined usually means second best: allow the best and the second best
                    if _is_rank(c.value, [d for _, d in col], want, 2) or _is_rank(c.value, [d for _, d in group], want, 2):
                        continue
                better = _better(c.value, [(k, d) for k, d in col], want)
                k, d = better
                header = t.header(j) or f"column {j + 1}"
                way = {"higher": "higher", "lower": "lower"}.get(want, "better")
                if mark == "underlined":
                    what = f"{c.text} is underlined but is not among the two best"
                else:
                    what = f"{c.text} is bold but {d.text} ({t.row_name(k) or 'row ' + str(k + 1)}) is {way}"
                if not want:
                    what += " (and it is neither the highest nor the lowest)"
                out.append(Finding("bold-not-best", "warning", t.file, c.line, f"{t.name}, {header}: {what}"))
    return out


def _is_best(v: float, cells, want: str) -> bool:
    values = [c.value for c in cells]
    tol = max((_tol(c.decimals) for c in cells), default=0)
    hi, lo = max(values), min(values)
    if want == "higher":
        return v >= hi - tol
    if want == "lower":
        return v <= lo + tol
    return v >= hi - tol or v <= lo + tol


def _is_rank(v: float, cells, want: str, n: int) -> bool:
    values = sorted({c.value for c in cells})
    tol = max((_tol(c.decimals) for c in cells), default=0)
    top_hi, top_lo = values[-n:], values[:n]
    if want == "higher":
        return any(abs(v - x) <= tol for x in top_hi)
    if want == "lower":
        return any(abs(v - x) <= tol for x in top_lo)
    return any(abs(v - x) <= tol for x in top_hi + top_lo)


def _better(v: float, col, want: str):
    if want == "lower":
        return min(col, key=lambda kd: kd[1].value)
    if want == "higher":
        return max(col, key=lambda kd: kd[1].value)
    hi = max(col, key=lambda kd: kd[1].value)
    lo = min(col, key=lambda kd: kd[1].value)
    return hi if abs(hi[1].value - v) <= abs(lo[1].value - v) else lo


# ---------------------------------------------------------------- "from A to B, p%"

_NUM = r"(\d+(?:\.\d+)?)"
FROM_TO = re.compile(r"\bfrom\s+\$?" + _NUM + r"\s*\$?\s*(?:\\?%|points?|pp)?\s+to\s+\$?" + _NUM + r"\s*\$?\s*(?:\\?%|points?|pp)?", re.I)
PERCENT = re.compile(r"(?<![\d.])" + _NUM + r"\s*(?:\\%|%|percent\b)")
POINTS = re.compile(r"(?<![\d.])" + _NUM + r"\s*(?:points?|pp|p\.p\.|absolute)\b", re.I)
TIMES = re.compile(r"(?<![\d.])" + _NUM + r"\s*(?:\\times|×|x\b|-fold|times)", re.I)


def _dec(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def _interval(f, a: float, ea: float, b: float, eb: float) -> tuple[float, float]:
    vals = [f(x, y) for x in (a - ea, a + ea) for y in (b - eb, b + eb) if x != 0]
    return (min(vals), max(vals)) if vals else (float("-inf"), float("inf"))


def change_claims(text: str, file: str, line_of) -> list[Finding]:
    out = []
    for m in FROM_TO.finditer(text):
        a_s, b_s = m.group(1), m.group(2)
        a, b = float(a_s), float(b_s)
        if a == b:
            continue
        # the sentence around it
        start = max(text.rfind(". ", 0, m.start()), text.rfind("\n\n", 0, m.start())) + 1
        end_candidates = [x for x in (text.find(". ", m.end()), text.find("\n\n", m.end())) if x >= 0]
        end = min(end_candidates) if end_candidates else len(text)
        sentence = text[start:end]
        rest = sentence.replace(m.group(0), " ")
        ea, eb = _tol(_dec(a_s)), _tol(_dec(b_s))
        rel = _interval(lambda x, y: abs(y - x) / abs(x) * 100, a, ea, b, eb)
        pts = (abs(b - a) - ea - eb, abs(b - a) + ea + eb)
        ratio = _interval(lambda x, y: max(x, y) / min(x, y) if min(x, y) > 0 else float("inf"), a, ea, b, eb)
        for p_m in PERCENT.finditer(rest):
            p_s = p_m.group(1)
            p, ep = float(p_s), _tol(_dec(p_s))
            if rel[0] - ep <= p <= rel[1] + ep or pts[0] - ep <= p <= pts[1] + ep:
                continue
            exact_rel = abs(b - a) / a * 100 if a else float("inf")
            out.append(
                Finding(
                    "wrong-change",
                    "warning",
                    file,
                    line_of(start + sentence.find(p_m.group(0))),
                    f"from {a_s} to {b_s} is a {exact_rel:.1f}% relative change ({abs(b - a):.{max(_dec(a_s), _dec(b_s))}f} points), not {p_s}%",
                )
            )
        for t_m in TIMES.finditer(rest):
            r_s = t_m.group(1)
            r, er = float(r_s), _tol(_dec(r_s))
            if ratio[0] - er <= r <= ratio[1] + er:
                continue
            exact = max(a, b) / min(a, b) if min(a, b) > 0 else float("inf")
            where = line_of(start + sentence.find(t_m.group(0)))
            out.append(Finding("wrong-change", "warning", file, where, f"from {a_s} to {b_s} is {exact:.2f}×, not {r_s}×"))
    return out


# ---------------------------------------------------------------- abstract numbers

ABSTRACT = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.S)


def _abstract(text: str) -> tuple[int, str] | None:
    m = ABSTRACT.search(text)
    if m:
        return m.start(1), m.group(1)
    m = re.search(r"\\abstract\s*\{", text)
    if m:
        end = _matching(text, m.end(), "{", "}")
        if end > 0:
            return m.end(), text[m.end() : end]
    return None


def _numbers_in(s: str) -> set[str]:
    return {x.replace(",", "") for x in NUMBER.findall(s)}


def abstract_numbers(texts: dict[str, str], tables: list[Table]) -> list[Finding]:
    found = None
    for file, text in texts.items():
        a = _abstract(text)
        if a:
            found = (file, text, *a)
            break
    if not found:
        return []
    file, text, start, abstract = found
    body = "\n".join(t if f != file else t[:start] + t[start + len(abstract) :] for f, t in texts.items())
    body_numbers = _numbers_in(re.sub(r"\\(?:label|ref|cite\w*|eqref|cref|autoref)\{[^}]*\}", "", body))
    columns = []
    for t in tables:
        for j in range(max((len(r) for r in t.rows), default=0)):
            col = [c for _, c in t.column(j)]
            if col:
                columns.append(col)
    out = []
    for m in re.finditer(r"(?<![\w.\\-])(\d+\.\d+)(?![\w.-])(\s*(?:\\%|%))?", abstract):
        s = m.group(1)
        if s in body_numbers or s.rstrip("0").rstrip(".") in body_numbers:
            continue
        x, ex = float(s), _tol(_dec(s))
        if _derived(x, ex, columns, percent=bool(m.group(2))):
            continue
        line = text.count("\n", 0, start + m.start()) + 1
        out.append(
            Finding(
                "abstract-number",
                "warning",
                file,
                line,
                f"the abstract says {s}{'%' if m.group(2) else ''}, which is not in the text or any table, nor a difference "
                "or relative change between two numbers of one table column (an outdated number?)",
            )
        )
    return out


def _derived(x: float, ex: float, columns, percent: bool) -> bool:
    for col in columns:
        for c in col:
            for d in col:
                if c is d or c.value is None or d.value is None:
                    continue
                e = _tol(c.decimals) + _tol(d.decimals)
                diff = abs(c.value - d.value)
                if abs(diff - x) <= e + ex:
                    return True
                if d.value:
                    lo, hi = _interval(lambda u, v: abs(v - u) / abs(u) * 100, d.value, _tol(d.decimals), c.value, _tol(c.decimals))
                    if lo - ex <= x <= hi + ex:
                        return True
                    if c.value > 0 and d.value > 0 and abs(c.value / d.value - x) <= ex + 0.01 * x:
                        return True
    return False


# ---------------------------------------------------------------- labels and references

REF = re.compile(r"\\(?:ref|eqref|pageref|autoref|nameref|vref|Vref|cref|Cref|crefrange|Crefrange|cpageref|labelcref|subref)\*?\s*\{([^}]+)\}")
LABEL = re.compile(r"\\label\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
FLOAT = re.compile(r"\\begin\{(figure|table|figure\*|table\*|wrapfigure|wraptable|subfigure|subtable)\}")


def labels(texts: dict[str, str]) -> list[Finding]:
    defined: dict[str, tuple[str, int, str]] = {}
    out = []
    used: set[str] = set()
    for text in texts.values():
        for m in REF.finditer(text):
            for k in m.group(1).split(","):
                used.add(k.strip())
    for file, text in texts.items():
        floats = [(m.start(), m.group(1).rstrip("*"), text.find(f"\\end{{{m.group(1)}}}", m.start())) for m in FLOAT.finditer(text)]
        for m in LABEL.finditer(text):
            k = m.group(1).strip()
            line = text.count("\n", 0, m.start()) + 1
            kind = next((name for s, name, e in reversed(floats) if s < m.start() < (e if e >= 0 else len(text))), "")
            if k in defined:
                f0, l0, _ = defined[k]
                out.append(Finding("duplicate-label", "error", file, line, f"label {k} is also defined at {f0}:{l0}: references to it are ambiguous"))
                continue
            defined[k] = (file, line, kind)
    for file, text in texts.items():
        for m in REF.finditer(text):
            for k in m.group(1).split(","):
                k = k.strip()
                if k and k not in defined:
                    line = text.count("\n", 0, m.start()) + 1
                    out.append(Finding("undefined-ref", "error", file, line, f"reference to {k}, which is never defined: it prints as ??"))
    for k, (file, line, kind) in defined.items():
        if kind in ("figure", "table", "wrapfigure", "wraptable") and k not in used:
            out.append(Finding("unreferenced", "note", file, line, f"{kind.replace('wrap', '')} {k} is never referred to in the text"))
    return out


# ---------------------------------------------------------------- all together


def check_numbers(texts: dict[str, str]) -> list[Finding]:
    tables = [t for f, text in texts.items() for t in find_tables(text, f)]
    out: list[Finding] = []
    for t in tables:
        out += bold_not_best(t)
    for f, text in texts.items():
        # tables and equations blanked out (line breaks kept): their numbers are not claims in prose
        blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
        body = re.sub(r"\\begin\{(tabular\*?|tabularx|longtable|equation\*?|align\*?)\}.*?\\end\{\1\}", blank, text, flags=re.S)
        out += change_claims(body, f, lambda pos, text=text: text.count("\n", 0, pos) + 1)
    out += abstract_numbers(texts, tables)
    out += labels(texts)
    return sorted(out, key=lambda x: (SEVERITY_ORDER.index(x.severity), x.file, x.line))
