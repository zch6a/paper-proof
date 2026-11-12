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
    if OTHER_MEANING.search(t.caption):
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
            if _is_best(c.value, [d for _, d in col], want) or (len(group) > 1 and _is_best(c.value, [d for _, d in group], want)):
                continue
            k, d = _better(c.value, group if len(group) > 2 else col, want)
            header = t.header(j) or f"column {j + 1}"
            if want:
                what = f"{_shown(c)} is bold but {_shown(d)} ({t.row_name(k) or 'row ' + str(k + 1)}) is {want}"
            else:
                values = [x.value for _, x in (group if len(group) > 2 else col)]
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
            by_row += len(row) > 2 and _is_best(c.value, row, direction(t.row_name(i)))
            by_col += len(col) > 2 and (_is_best(c.value, col, _want(t, j)) or (len(group) > 1 and _is_best(c.value, group, _want(t, j))))
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
                if _is_best(c.value, col, want):
                    agree += 1
                elif _is_best(c.value, col, "lower" if want == "higher" else "higher"):
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
    """>>> caption_direction("GLUE results. Higher is better for all metrics.")
    'higher'
    """
    hi = re.search(r"higher (?:is|=) better|higher values? (?:is|are) better|\(higher is better\)", caption, re.I)
    lo = re.search(r"lower (?:is|=) better|lower values? (?:is|are) better|\(lower is better\)", caption, re.I)
    return "higher" if hi and not lo else "lower" if lo and not hi else ""


def _shown(c) -> str:
    return f"{c.value:.{c.decimals}f}"


def _bold_not_best_by_row(t: Table) -> list[Finding]:
    out = []
    for i in range(t.header_rows, len(t.rows)):
        row = _row_cells(t, i)
        bolds = [c for c in row if c.bold]
        if len(row) < 3 or len(bolds) != 1:
            continue
        c = bolds[0]
        want = direction(t.row_name(i)) or caption_direction(t.caption)
        if _is_best(c.value, row, want):
            continue
        name = t.row_name(i) or f"row {i + 1}"
        values = [x.value for x in row]
        if want:
            best = max(values) if want == "higher" else min(values)
            what = f"{_shown(c)} is bold but {best:g} in the same row is {want}"
        else:
            what = f"{_shown(c)} is bold but is neither the highest nor the lowest of its row ({min(values):g} to {max(values):g})"
        out.append(Finding("bold-not-best", "warning", t.file, c.line, f"{t.name}, row {name}: {what}"))
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


CHANGE_WORD = re.compile(
    r"improv|increas|reduc|decreas|gain|boost|drop|lower|rais|cut|faster|speed|slower|relative|absolute|better|worse|"
    r"jump|rise|rose|fell|fall|declin|halv|doubl|accelerat|outperform|shrink|grow|grew",
    re.I,
)
WINDOW = 80  # characters between "from A to B" and the claimed change


def _is_year(s: str) -> bool:
    return "." not in s and 1900 <= int(s) <= 2100


def change_claims(text: str, file: str, line_of) -> list[Finding]:
    """`from A to B` with a percentage or a factor right next to it (within one clause, with a word of change)."""
    out = []
    for m in FROM_TO.finditer(text):
        a_s, b_s = m.group(1), m.group(2)
        a, b = float(a_s), float(b_s)
        if a == b or _is_year(a_s) or _is_year(b_s):
            continue
        # the text right around it, not crossing a sentence or a semicolon
        lo = max(m.start() - WINDOW, max(text.rfind(x, 0, m.start()) for x in (". ", ";", "\n\n")) + 1)
        stops = [x for x in (text.find(". ", m.end()), text.find(";", m.end()), text.find("\n\n", m.end())) if x >= 0]
        hi = min([m.end() + WINDOW] + stops)
        start, sentence = lo, text[lo:hi]
        if not CHANGE_WORD.search(sentence):
            continue
        if re.search(r"rang\w*|var(?:y|ies|ying|ied)|spann?\w*|between", text[max(lo, m.start() - 25) : m.start()], re.I):
            continue  # "ranging from 33% to 90%": a range of values, not a change from one to the other
        rest = sentence.replace(m.group(0), " " * len(m.group(0)))
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

REF = re.compile(r"\\(ref|eqref|pageref|autoref|nameref|vref|Vref|cref|Cref|crefrange|Crefrange|cpageref|Cpageref|labelcref|subref)\*?\s*\{([^}]+)\}")
LABEL = re.compile(r"\\label\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
FLOAT = re.compile(r"\\begin\{(figure|table|figure\*|table\*|wrapfigure|wraptable|subfigure|subtable)\}")
# Arguments of these are text that may be used once, several times, or not at all: a label inside one is not a
# plain definition (a figure kept in a macro, two versions behind a toggle).
CONDITIONAL = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand|NewDocumentCommand|RenewDocumentCommand|newenvironment|"
    r"iftoggle|ifthenelse|IfFileExists|ifdefined|ifcsname|ifboolexpr|ifbool|IfBooleanTF|def\s*\\[A-Za-z@]+[^{]*)\*?"
)


def refs_in(text: str):
    """(key, position) of each reference; only the cleveref family takes comma-separated lists."""
    for m in REF.finditer(text):
        keys = m.group(2).split(",") if m.group(1).lower() in ("cref", "crefrange", "cpageref", "labelcref") else [m.group(2)]
        for k in keys:
            k = k.strip()
            if k and "#" not in k:  # #1: a macro's parameter, not a label
                yield k, m.start()


def conditional_spans(text: str) -> list[tuple[int, int]]:
    """Where text sits inside macro definitions or the branches of \\iftoggle, \\ifthenelse, \\if...\\fi."""
    spans = []
    for m in CONDITIONAL.finditer(text):
        i = m.end()
        start = None
        for _ in range(4):  # up to four braced arguments
            mm = re.match(r"\s*(?:\[[^\]]*\])?\s*\{", text[i:])
            if not mm:
                break
            end = _matching(text, i + mm.end(), "{", "}")
            if end < 0:
                break
            start = i + mm.end() if start is None else start
            i = end + 1
        if start is not None:
            spans.append((start, i))
    stack = []
    for m in re.finditer(r"\\(if[a-zA-Z@]*|fi)\b", text):
        name = m.group(1)
        if name in ("ifthenelse", "iftoggle", "ifdefined", "ifcsname", "ifbool", "ifboolexpr"):
            continue
        if name == "fi":
            if stack:
                spans.append((stack.pop(), m.start()))
        else:
            stack.append(m.end())
    return spans


def labels(texts: dict[str, str]) -> list[Finding]:
    defined: dict[str, tuple[str, int, str, bool]] = {}
    out = []
    used = {k for text in texts.values() for k, _ in refs_in(text)}
    for file, text in texts.items():
        floats = [(m.start(), m.group(1).rstrip("*"), text.find(f"\\end{{{m.group(1)}}}", m.start())) for m in FLOAT.finditer(text)]
        spans = conditional_spans(text)
        for m in LABEL.finditer(text):
            k = m.group(1).strip()
            if "#" in k:
                continue
            line = text.count("\n", 0, m.start()) + 1
            kind = next((name for s, name, e in reversed(floats) if s < m.start() < (e if e >= 0 else len(text))), "")
            conditional = any(s <= m.start() < e for s, e in spans)
            if k in defined:
                f0, l0, _, cond0 = defined[k]
                if not conditional and not cond0:
                    if k in used:
                        msg = f"label {k} is also defined at {f0}:{l0}: references to it point to only one of them"
                        out.append(Finding("duplicate-label", "error", file, line, msg))
                    else:
                        msg = f"label {k} is also defined at {f0}:{l0} (nothing refers to it yet)"
                        out.append(Finding("duplicate-label", "note", file, line, msg))
                continue
            defined[k] = (file, line, kind, conditional)
    for file, text in texts.items():
        for k, pos in refs_in(text):
            if k not in defined:
                line = text.count("\n", 0, pos) + 1
                out.append(Finding("undefined-ref", "error", file, line, f"reference to {k}, which is never defined: it prints as ??"))
    for k, (file, line, kind, _) in defined.items():
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
