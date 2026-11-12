""" "from A to B, a p% gain" and "an N× speedup", recomputed from A and B within rounding."""

from __future__ import annotations

import re

from .common import Finding, _dec, _interval, _tol

_NUM = r"(\d+(?:\.\d+)?)"


# No two whitespace quantifiers can match the same spaces (a long run of blanks must not cost quadratic time).
_UNIT = r"(?:\s*\$)?(?:\s*(?:\\?%|points?\b|pp\b))?"


FROM_TO = re.compile(r"\bfrom\s+\$?" + _NUM + _UNIT + r"\s+to\s+\$?" + _NUM + _UNIT, re.I)


PERCENT = re.compile(r"(?<![\d.])" + _NUM + r"\s*(?:\\%|%|percent\b)")


TIMES = re.compile(r"(?<![\d.])" + _NUM + r"\s*\$?\s*(?:\\times|×|x\b|-fold|times)", re.I)


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
    claims = list(FROM_TO.finditer(text))
    for n, m in enumerate(claims):
        a_s, b_s = m.group(1), m.group(2)
        a, b = float(a_s), float(b_s)
        if a == b or _is_year(a_s) or _is_year(b_s):
            continue
        # the text right around it, not crossing a sentence or a semicolon
        lo = max(m.start() - WINDOW, max(text.rfind(x, 0, m.start()) for x in (". ", ";", "\n\n")) + 1)
        stops = [x for x in (text.find(". ", m.end()), text.find(";", m.end()), text.find("\n\n", m.end())) if x >= 0]
        hi = min([m.end() + WINDOW] + stops)
        # never reach into the neighbouring "from ... to ..." claims: a change stated after a claim belongs to it
        # ("from A to B, a p% gain"); one stated before it only when there is none after ("a p% gain, from A to B")
        if n + 1 < len(claims):
            hi = min(hi, claims[n + 1].start())
        after = text[m.end() : hi]
        if PERCENT.search(after) or TIMES.search(after):
            lo = m.start()
        elif n > 0:
            lo = max(lo, claims[n - 1].end())
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
