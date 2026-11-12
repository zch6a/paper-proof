"""References to labels that do not exist, labels defined twice, figures and tables never referred to."""

from __future__ import annotations

import re

from ..bib import _matching
from .common import Finding

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
    stack: list[int] = []
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
