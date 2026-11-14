r"""A PDF's text for the checks that read prose: pages joined with form feeds (so a position gives its page), the
reference list blanked (it is checked on its own, and its titles are other people's words), and where the abstract
is.

What a PDF cannot give: tables keep their numbers but lose their rows, columns and bold, so the table checks need
the LaTeX source. Numbers checks on a PDF are therefore the ones that read sentences.
"""

from __future__ import annotations

import re
from pathlib import Path

from .checks.changes import change_claims
from .checks.common import Finding, _dec, _tol
from .pdf import END, HEADING
from .tables import NUMBER


def pdf_pages(path: Path) -> list[str]:
    from pypdf import PdfReader

    return [(p.extract_text() or "") for p in PdfReader(str(path)).pages]


def _blank(s: str) -> str:
    return re.sub(r"[^\n\f]", " ", s)


def prose(pages: list[str]) -> str:
    """The pages joined by form feeds, with the reference list (from the last References heading to an appendix
    heading, or the end) blanked: same length, page breaks kept."""
    text = "\f".join(pages)
    lines = text.replace("\f", "\n")  # a heading at the top of a page starts a line too (same length: positions agree)
    heads = list(HEADING.finditer(lines))
    if not heads:
        return text
    start = heads[-1].start()
    end = len(text)
    for m in END.finditer(lines, heads[-1].end()):
        if lines[heads[-1].end() : m.start()].count("\n") >= 6:
            end = m.start()
            break
    return text[:start] + _blank(text[start:end]) + text[end:]


ABSTRACT_HEAD = re.compile(r"^\s*abstract\b[.:—-]?", re.I | re.M)
INTRO_HEAD = re.compile(r"^\s*(?:1\.?|I\.)?\s*introduction\b", re.I | re.M)


def abstract_span(text: str) -> tuple[int, int] | None:
    """From the "Abstract" heading to the "Introduction" heading, on the first two pages."""
    first = text[: sum(len(p) + 1 for p in text.split("\f")[:2])]
    a = ABSTRACT_HEAD.search(first)
    if not a:
        return None
    i = INTRO_HEAD.search(first, a.end())
    if not i or i.start() - a.end() > 4000:
        return None
    return a.end(), i.start()


def page_of(text: str, pos: int) -> int:
    return text.count("\f", 0, pos) + 1


def pdf_numbers(text: str, file: str) -> list[Finding]:
    """ "from A to B, a p% gain" recomputed; and numbers of the abstract that appear nowhere else in the PDF."""
    out = change_claims(text, file, lambda pos: page_of(text, pos))
    span = abstract_span(text)
    if not span:
        return out
    a, b = span
    abstract, body = text[a:b], text[:a] + " " + text[b:]
    shown = [(float(x.replace(",", "")), _dec(x.replace(",", ""))) for x in NUMBER.findall(body.replace("−", "-"))]
    for m in re.finditer(r"(?<![\w.\\-])(\d+\.\d+)(?![\w.-])", abstract):
        s = m.group(1)
        x, ex = float(s), _tol(_dec(s))
        if any(abs(abs(y) - x) <= ex and d >= _dec(s) for y, d in shown):
            continue
        # the number's own clause: "7.7% point absolute improvement" is a difference; in "41.2 accuracy, 3.1 points
        # over the baseline" only 3.1 is
        before = re.split(r"[.;,]\s", abstract[max(0, m.start() - 40) : m.start()])[-1]
        after = re.split(r"[.;,]\s", abstract[m.end() : m.end() + 40])[0]
        if re.search(
            r"\bby\b|improv|gain|increas|reduc|decreas|\bover\b|outperform|better|higher|lower|points?\b|relative|absolute",
            before + " " + after,
            re.I,
        ):
            continue  # a difference or a relative change: a PDF's tables cannot be read to recompute it
        out.append(
            Finding(
                "abstract-number",
                "warning",
                file,
                page_of(text, a + m.start()),
                f"the abstract says {s}, which appears nowhere else in the PDF's text (an outdated number? a PDF's tables "
                "are read as loose text, so check the tables by hand)",
            )
        )
    return out
