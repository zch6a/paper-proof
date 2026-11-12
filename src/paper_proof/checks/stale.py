"""Numbers in the abstract, and in sentences that point to a table, that the tables do not show."""

from __future__ import annotations

import re

from ..bib import _matching
from ..tables import NUMBER, Table
from .common import DELTA_CONTEXT, Finding, _dec, _derived, _sentence, _table_numbers, _tol
from .labels import refs_in

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
    body = re.sub(r"\\(?:label|ref|cite\w*|eqref|cref|autoref)\{[^}]*\}", "", body)
    shown = [(float(x.replace(",", "")), _dec(x.replace(",", ""))) for x in NUMBER.findall(body.replace("−", "-"))]
    columns = []
    for t in tables:
        for j in range(max((len(r) for r in t.rows), default=0)):
            col = [c for _, c in t.column(j)]
            if col:
                columns.append(col)
    out = []
    for m in re.finditer(r"(?<![\w.\\-])(\d+\.\d+)(?![\w.-])(\s*(?:\\%|%))?", abstract):
        s = m.group(1)
        x, ex = float(s), _tol(_dec(s))
        # the same number in the body, or a more precise one that rounds to it (28.43 in a table, 28.4 in the abstract)
        if any(abs(abs(y) - x) <= ex and d >= _dec(s) for y, d in shown):
            continue
        # a difference or a relative change is only expected where the abstract talks about one
        before = re.split(r"[.;,]\s", abstract[max(0, m.start() - 30) : m.start()])[-1]
        context = before + " " + re.split(r"[.;,]\s", abstract[m.end() : m.end() + 25])[0]
        unit = "percent" if m.group(2) else "times" if re.match(r"\s*(?:\$?\\times|×|x\b|-fold|times)", abstract[m.end() :]) else "plain"
        if DELTA_CONTEXT.search(context) and _derived(x, ex, columns, unit):
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


def table_mentions(texts: dict[str, str], tables: list[Table]) -> list[Finding]:
    """A sentence that points to a table ("Table~\\ref{tab:main}") and quotes a decimal number: the number is in that
    table (allowing for rounding), or, where the sentence talks about a gain, a difference or relative change between
    two numbers of one of its columns."""
    by_label = {t.label: t for t in tables if t.label}
    if not by_label:
        return []
    all_numbers = [n for t in tables for n in _table_numbers(t)]
    out = []
    for file, text in texts.items():
        seen: set[tuple[int, int]] = set()
        for key, pos in refs_in(text):
            if key not in by_label:
                continue
            span = _sentence(text, pos)
            if span in seen:
                continue
            seen.add(span)
            sentence = text[span[0] : span[1]]
            cited = [by_label[k] for k, _ in refs_in(sentence) if k in by_label]
            if "\\begin{tabular" in sentence or "\\begin{table" in sentence:
                continue
            shown = [n for t in cited for n in _table_numbers(t)]
            anywhere = all_numbers
            columns = [col for t in cited for j in range(max((len(r) for r in t.rows), default=0)) if (col := [c for _, c in t.column(j)])]
            columns += [
                row for t in cited for i in range(t.header_rows, len(t.rows)) if len(row := [c for c in t.rows[i] if c.value is not None]) > 1
            ]
            clean = re.sub(r"\\(?:label|ref|cite\w*|eqref|cref|Cref|autoref|includegraphics)(?:\[[^\]]*\])?\{[^}]*\}", " ", sentence)
            missing = []
            for m in re.finditer(r"(?<![\w.\\-])(\d+\.\d+)(?![\w.-])(\s*(?:\\%|%))?", clean):
                s = m.group(1)
                x, ex = float(s), _tol(_dec(s))
                if any(abs(abs(y) - x) <= ex and d >= _dec(s) for y, d in shown):
                    continue
                around = clean[max(0, m.start() - 30) : m.end() + 25]
                unit = "percent" if m.group(2) else "times" if re.match(r"\s*(?:\$?\\times|×|x\b|-fold|times)", clean[m.end() :]) else "plain"
                if DELTA_CONTEXT.search(around) and _derived(x, ex, columns, unit):
                    continue
                if any(abs(abs(y) - x) <= ex and d >= _dec(s) for y, d in anywhere):
                    continue  # quoted from another table of the paper
                # A stale or mistyped result sits next to the right one: report only a number with a near neighbour in
                # the cited table (same precision, within 5%), and name it. A number unlike anything in the table is
                # most likely about something else (a step time, a setting) and is left alone.
                near = [y for y, d in shown if d == _dec(s) and y != x and abs(y - x) <= 0.05 * max(abs(x), 1e-9)]
                if near:
                    closest = min(near, key=lambda y: abs(y - x))
                    missing.append((s + ("%" if m.group(2) else ""), f"{closest:.{_dec(s)}f}"))
            if missing:
                names = ", ".join(dict.fromkeys(t.label for t in cited))
                at = span[0] + max(0, sentence.find(missing[0][0].rstrip("%")))
                said = ", ".join(f"{a} (the table has {b})" for a, b in missing)
                out.append(
                    Finding(
                        "text-vs-table",
                        "warning",
                        file,
                        text.count("\n", 0, at) + 1,
                        f"this sentence points to {names} and says {said}: a number the table does not show, "
                        "nor as a difference or relative change of two of its numbers",
                    )
                )
    return out
