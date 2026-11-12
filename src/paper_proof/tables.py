r"""LaTeX tables as data: rows, cells, numbers, which cells are bold, where each cell is in the
source, and which way each column is better (from ↑/↓ marks or the metric's name).

Handles tabular, tabular*, tabularx, longtable and array; \multicolumn and \multirow; booktabs rules and \hline
(a rule in the body starts a new group of rows); ± and parenthesised deltas after a number; %, $, \textbf, \bf,
\mathbf, \boldsymbol, \underline and \ul.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .bib import _matching

ENV = re.compile(r"\\begin\{(tabular\*?|tabularx|tabulary|longtable|array|tblr)\}")
RULE = re.compile(
    r"\\(?:toprule|midrule|bottomrule|hline|specialrule|cmidrule|cline|hdashline|addlinespace|endhead|endfirsthead|endfoot|endlastfoot)\b"
    r"(?:\s*\([^)]*\))?(?:\s*\{[^}]*\})*(?:\s*\[[^\]]*\])?"
)
MAX_SPAN = 64  # \multicolumn{3000000}{c}{x} must not allocate millions of cells
FULL_RULE = re.compile(r"\\(?:toprule|midrule|bottomrule|hline|specialrule|hdashline)\b")
NUMBER = re.compile(r"(?<![\w.])[-−]?\d+(?:,\d{3})*(?:\.\d+)?(?![\w.])")
BOLD = re.compile(r"\\(?:textbf|mathbf|boldsymbol|bm|pmb)\s*\{|\{\s*\\bf(?:series)?\b|\\bf(?:series)?\b|\\cellcolor\{best\}")

LOWER = re.compile(
    r"\b(?:err(?:or)?s?|loss|perplexity|ppl|fid|kid|wer|cer|ter|mse|mae|rmse|nll|bpd|bpc|eer|latency|time|runtime|"
    r"seconds?|ms|hours?|params?|parameters|flops|macs|memory|mem|cost|chamfer|lpips|distance|regret|violations?|"
    r"rank|edit distance|abs ?rel|sq ?rel|ate|rpe)\b",
    re.I,
)
HIGHER = re.compile(
    r"\b(?:acc(?:uracy)?|top-?[15]|bleu|rouge(?:-\w+)?|meteor|chrf|f1|f-?score|auc|auroc|ap|map|ap50|ap75|iou|miou|"
    r"precision|recall|psnr|ssim|ndcg|mrr|hits?@?\d*|pass@?\d*|win ?rate|success|score|em|exact match|r@\d+|"
    r"spearman|pearson|kendall|correlation|reward|return|bertscore|cider|spice|is|inception score|throughput)\b",
    re.I,
)


# Rows that are not competitors: human performance, oracles and upper bounds, statistics of the data itself.
REFERENCE_ROW = re.compile(
    r"\s*(?:human|humans|oracle|upper[- ]?bound|lower[- ]?bound|ground[- ]?truth|gt\b|train(?:ing)?(?: set| data)?$|"
    r"test(?: set| data)?$|val(?:idation)?(?: set)?$|real(?: data| images)?$|reference$|random(?: chance| guess)?$|chance$)",
    re.I,
)
REFERENCE_ANYWHERE = re.compile(r"\bhumans?\b|\boracle\b|upper[- ]?bound|\bforecast|\bexpert performance", re.I)


@dataclass
class Cell:
    raw: str
    text: str  # without formatting
    value: float | None
    decimals: int
    bold: bool
    line: int

    @property
    def num(self) -> float:
        """The value of a cell known to hold a number (Table.column and the row helpers only return those)."""
        assert self.value is not None, "not a number"
        return self.value


@dataclass
class Table:
    file: str
    line: int  # where the tabular begins
    label: str
    caption: str
    rows: list[list[Cell]] = field(default_factory=list)
    groups: list[int] = field(default_factory=list)  # group number of each row (a rule in the body starts a new one)
    header_rows: int = 0

    def column(self, j: int) -> list[tuple[int, Cell]]:
        """The numbers of column j, without header rows and reference rows (human, oracle, train/test statistics)."""
        return [
            (i, r[j]) for i, r in enumerate(self.rows) if i >= self.header_rows and j < len(r) and r[j].value is not None and not self.is_reference(i)
        ]

    def is_reference(self, i: int) -> bool:
        name = self.row_name(i)
        return bool(REFERENCE_ROW.match(name) or REFERENCE_ANYWHERE.search(name))

    def header(self, j: int) -> str:
        return " ".join(r[j].text for r in self.rows[: self.header_rows] if j < len(r)).strip()

    def row_start(self, i: int) -> int:
        """Index of the first cell after the row's name cells."""
        r = self.rows[i]
        return next((j for j, c in enumerate(r) if c.value is not None), len(r))

    def row_name(self, i: int) -> str:
        r = self.rows[i]
        return next((c.text for c in r if c.text and c.value is None), r[0].text if r else "")

    @property
    def name(self) -> str:
        return self.label or (f'"{self.caption[:50]}"' if self.caption else f"table at {self.file}:{self.line}")


def direction(header: str) -> str:
    r"""'higher', 'lower' or '' for a column header.

    >>> direction(r"BLEU $\uparrow$"), direction("FID"), direction("Test error (%)"), direction("Model")
    ('higher', 'lower', 'lower', '')
    """
    if re.search(r"\\uparrow|↑|higher is better|\(\+\)", header, re.I):
        return "higher"
    if re.search(r"\\downarrow|↓|lower is better", header, re.I):
        return "lower"
    lo, hi = LOWER.search(header), HIGHER.search(header)
    if lo and not hi:
        return "lower"
    if hi and not lo:
        return "higher"
    return ""


def _strip_format(s: str) -> str:
    styles = "textbf|mathbf|boldsymbol|bm|pmb|underline|ul|uline|textit|emph|mathrm|text|textrm|textsc|small|scriptsize|footnotesize|tiny"
    s = re.sub(r"\\(?:" + styles + r")\b", "", s)
    s = re.sub(r"\\(?:bf|bfseries|it|itshape|em)\b", "", s)
    s = re.sub(r"\\(?:cellcolor|rowcolor|color|textcolor)(?:\[[^\]]*\])?\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:makecell|shortstack)(?:\[[^\]]*\])?", "", s)
    s = re.sub(r"\\(?:hphantom|phantom|vphantom)\{[^}]*\}", "", s)
    s = s.replace("\\%", "%").replace("$", "").replace("{", "").replace("}", "").replace("~", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_value(raw: str) -> tuple[float | None, int, str]:
    r"""The number a cell shows (before any ± or parenthesised delta), its decimals, and the cell as text.

    >>> parse_value(r"\textbf{75.3}$\pm$0.2")[:2]
    (75.3, 1)
    >>> parse_value(r"28.4 (+1.2)")[:2], parse_value("ResNet-50")[:2], parse_value(r"92.1\%")[:2], parse_value("--")[:2]
    ((28.4, 1), (None, 0), (92.1, 1), (None, 0))
    """
    text = _strip_format(raw)
    # the number, then nothing, or only what decorates a number: ± spread, (delta), %, sub/superscripts, marks
    m = re.match(r"\s*([-−]?\d+(?:,\d{3})*(?:\.\d+)?)", text)
    if not m:
        return None, 0, text
    rest = text[m.end() :].strip()
    if rest and not re.match(r"(?:\\[A-Za-z]+|[(\[±%^_*†‡§¶/]|\+/-|\+|−|-\s*\d)", rest):
        return None, 0, text  # 125.0M, 50 epochs, 3B: not a result
    s = m.group(1).replace("−", "-").replace(",", "")
    return float(s), len(s.split(".")[1]) if "." in s else 0, text


def _split(s: str, sep: str) -> list[tuple[str, int]]:
    """Split at `sep` outside braces (and not escaped), with each piece's offset."""
    out, depth, start, i = [], 0, 0, 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            if sep == "\\\\" and s.startswith("\\\\", i) and depth == 0:
                out.append((s[start:i], start))
                i += 2
                # an optional [2pt] after \\
                m = re.match(r"\s*\[[^\]]*\]", s[i:])
                if m:
                    i += m.end()
                start = i
                continue
            if sep == "\\\\" and s.startswith("\\tabularnewline", i) and depth == 0:
                out.append((s[start:i], start))
                i += len("\\tabularnewline")
                start = i
                continue
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == sep and depth == 0:
            out.append((s[start:i], start))
            start = i + 1
        i += 1
    out.append((s[start:], start))
    return out


def _cells(row: str, offset: int, text: str) -> list[Cell]:
    cells = []
    for raw, off in _split(row, "&"):
        span = 1
        m = re.match(r"\s*\\multicolumn\s*\{(\d+)\}\s*\{[^}]*\}\s*\{", raw)
        if m:
            span = min(int(m.group(1)), MAX_SPAN)
            end = _matching(raw, m.end(), "{", "}")
            raw = raw[m.end() : end if end > 0 else len(raw)]
        m = re.match(r"\s*\\multirow\s*(?:\[[^\]]*\])?\s*\{[^}]*\}\s*(?:\[[^\]]*\])?\s*\{[^}]*\}\s*(?:\[[^\]]*\])?\s*\{", raw)
        if m:
            end = _matching(raw, m.end(), "{", "}")
            raw = raw[m.end() : end if end > 0 else len(raw)]
        value, decimals, plain = parse_value(raw)
        line = text.count("\n", 0, offset + off + len(raw) - len(raw.lstrip())) + 1
        c = Cell(raw.strip(), plain, value, decimals, bool(BOLD.search(raw)), line)
        cells.append(c)
        cells.extend(Cell("", "", None, 0, False, line) for _ in range(span - 1))
    return cells


def find_tables(text: str, file: str = "") -> list[Table]:
    tables = []
    for m in ENV.finditer(text):
        env = m.group(1)
        i = m.end()
        # tabular* and tabularx take a width first; tblr takes options; then the column spec
        for _ in range(2 if env in ("tabular*", "tabularx", "tabulary") else 1):
            mm = re.match(r"\s*(?:\[[^\]]*\])?\s*\{", text[i:])
            if not mm:
                break
            end = _matching(text, i + mm.end(), "{", "}")
            i = end + 1 if end > 0 else i
        close = text.find(f"\\end{{{env}}}", i)
        if close < 0:
            continue
        body = text[i:close]
        # the float around it: label and caption
        start = text.rfind("\\begin{table", 0, m.start())
        stop = text.find("\\end{table", close)
        around = text[start:stop] if start >= 0 and stop >= 0 and text.find("\\end{table", start) >= close else ""
        label = mm.group(1) if (mm := re.search(r"\\label\{([^}]+)\}", around)) else ""
        cap = ""
        if (mm := re.search(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", around)) is not None:
            end = _matching(around, mm.end(), "{", "}")
            cap = _strip_format(around[mm.end() : end]) if end > 0 else ""
        t = Table(file=file, line=text.count("\n", 0, m.start()) + 1, label=label, caption=cap)
        # Each row gets the number of full-width rules above it (\cmidrule and \cline only underline a span).
        rules_above, first_rule_row = 0, None
        for row, off in _split(body, "\\\\"):
            n_rules = sum(1 for r in RULE.finditer(row) if FULL_RULE.match(r.group(0)))
            if n_rules and t.rows:
                rules_above += 1
                if first_rule_row is None:
                    first_rule_row = len(t.rows)
            clean = RULE.sub(lambda r: " " * len(r.group(0)), row)
            if not clean.strip():
                continue
            t.rows.append(_cells(clean, i + off, text))
            t.groups.append(rules_above)
        # The header: the rows above the first rule under content when that rule comes early (headers may hold
        # numbers: lengths, sizes, shots); when it comes late, the table has no rule under its header, and the
        # header is the leading rows without numbers.
        leading = next((k for k, r in enumerate(t.rows) if any(c.value is not None for c in r)), len(t.rows))
        if first_rule_row is not None and (first_rule_row <= 3 or first_rule_row <= leading):
            t.header_rows = first_rule_row
        else:
            t.header_rows = leading if leading < len(t.rows) else 0
        # groups counted from the first body row
        if t.header_rows < len(t.groups):
            first = t.groups[t.header_rows]
            t.groups = [max(0, g - first) for g in t.groups]
        tables.append(t)
    return tables
