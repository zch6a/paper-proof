"""Reports: for a terminal, as JSON, and as Markdown (for a pull request or a review). Text from the bibliography and
from the databases is untrusted: control characters are shown, never sent to the terminal.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field

from . import __version__
from .check import Verdict
from .numbers import Finding

FINDING_LABEL = {"error": "ERROR", "warning": "WARNING", "note": "note"}
FINDING_COLOR = {"error": "31;1", "warning": "33", "note": "2"}

ORDER = ["not-found", "retracted", "mismatch", "unknown", "skipped", "ok"]
LABEL = {"not-found": "NOT FOUND", "retracted": "RETRACTED", "mismatch": "MISMATCH", "unknown": "UNKNOWN", "skipped": "skipped", "ok": "ok"}
COLOR = {"not-found": "31;1", "retracted": "31;1", "mismatch": "33", "unknown": "36", "skipped": "2", "ok": "32"}


def visible(s: str) -> str:
    """Control and bidi characters as visible escapes.

    >>> visible("a\\x1b[2Jb")
    'a\\\\x1b[2Jb'
    """
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", lambda m: f"\\x{ord(m.group(0)):02x}", s)
    return re.sub(r"[؜‎‏‪-‮⁦-⁩]", lambda m: f"<U+{ord(m.group(0)):04X}>", s)


def use_color(stream=sys.stdout, choice: str = "auto") -> bool:
    """--color always/never decide; otherwise FORCE_COLOR (an explicit request) wins over NO_COLOR, which wins over
    whether the output is a terminal."""
    if choice in ("always", "never"):
        return choice == "always"
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


@dataclass
class Extra:
    """What reading a LaTeX project found besides the references themselves."""

    main: str = ""
    bibliography_from: str = ""
    undefined: list[tuple[str, str, int]] = field(default_factory=list)  # (key, file, line): \cite with no entry
    uncited: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)  # the paper against itself (numbers, labels)
    refs_checked: bool = True
    texts: dict[str, str] = field(default_factory=dict, repr=False)  # the project's sources, never written to a report


def _where(v: Verdict) -> str:
    if v.file and v.line:
        return f" ({v.file}:{v.line})"
    return f" (line {v.line})" if v.line else ""


def summary(verdicts: list[Verdict]) -> dict[str, int]:
    c = Counter(v.status for v in verdicts)
    return {k: c.get(k, 0) for k in ORDER}


def _scope(extra: Extra, n: int) -> str:
    if not extra.refs_checked:
        return f"main file {extra.main}, numbers and labels only (references not checked: offline)"
    if not extra.main:
        return f"{n} reference{'' if n == 1 else 's'}"
    return f"{n} cited reference{'' if n == 1 else 's'} (main file {extra.main}, bibliography from {extra.bibliography_from})"


def text(verdicts: list[Verdict], dups: list[tuple[str, str, str]], source: str, extra: Extra | None = None, color: bool = False) -> str:
    extra = extra or Extra()
    paint = (lambda code, s: f"\x1b[{code}m{s}\x1b[0m") if color else (lambda code, s: s)
    out = [f"paper-proof {__version__} · {visible(source)}: {_scope(extra, len(verdicts))}", ""]
    for key, file, line in extra.undefined:
        out.append(f"{paint('31;1', 'UNDEFINED')} \\cite{{{visible(key)}}} ({visible(file)}:{line}) has no bibliography entry: it prints as [?]")
    for name in extra.missing_files:
        out.append(f"{paint('33', 'MISSING'.ljust(9))} {visible(name)} is used by the project but not in it")
    if extra.undefined or extra.missing_files:
        out.append("")
    if extra.findings:
        out.append("The paper against itself:")
        for f in extra.findings:
            if f.kind != "unreferenced":
                out.append(f"{paint(FINDING_COLOR[f.severity], FINDING_LABEL[f.severity].ljust(9))} {visible(f.file)}:{f.line}  {visible(f.message)}")
        unref = [f for f in extra.findings if f.kind == "unreferenced"]
        if unref:
            names = ", ".join(visible(f.message.split(" ")[1]) for f in unref[:10]) + (f" and {len(unref) - 10} more" if len(unref) > 10 else "")
            out.append(f"{paint(FINDING_COLOR['note'], 'note'.ljust(9))} never referred to in the text: {names}")
        out.append("")
    if verdicts:
        out.append("References:")
    for v in sorted(verdicts, key=lambda v: (ORDER.index(v.status), v.file, v.line)):
        if v.status == "ok" and not v.notes:
            continue
        out.append(f"{paint(COLOR[v.status], LABEL[v.status].ljust(9))} {visible(v.key)}{_where(v)}")
        if v.title:
            out.append(f"          {visible(v.title)[:110]}")
        for p in v.problems:
            out.append(f"          - {visible(p)}")
        if v.closest:
            out.append(f'          closest title found: "{visible(v.closest)[:100]}"')
        for n in v.notes:
            out.append(f"          · {visible(n)}")
        if v.match and v.match.url and v.status != "ok":
            out.append(f"          {visible(v.match.url)}")
        out.append("")
    for a, b, why in dups:
        out.append(f"{paint('33', 'DUPLICATE'.ljust(9))} {visible(a)} and {visible(b)} ({why})")
    if dups:
        out.append("")
    if extra.uncited:
        shown = ", ".join(visible(k) for k in extra.uncited[:12]) + (f" and {len(extra.uncited) - 12} more" if len(extra.uncited) > 12 else "")
        out += [f"Not cited anywhere in the text (not checked): {shown}", ""]
    s = summary(verdicts)
    parts = [f"{n} {LABEL[k] if k not in ('ok', 'skipped') else k}" for k, n in s.items() if n]
    if extra.undefined:
        parts.insert(0, f"{len(extra.undefined)} UNDEFINED")
    fc = Counter(f.severity for f in extra.findings)
    parts = [f"{fc[k]} {FINDING_LABEL[k]}{'S' if k != 'note' and fc[k] > 1 else ''}" for k in ("error", "warning", "note") if fc[k]] + parts
    out.append("Summary: " + (", ".join(parts) or "nothing to report") + (f", {len(dups)} duplicate(s)" if dups else ""))
    if s["unknown"]:
        out.append("Unknown means a database did not answer; run again later (answers are cached).")
    return "\n".join(out)


def to_json(verdicts: list[Verdict], dups: list[tuple[str, str, str]], source: str, extra: Extra | None = None) -> str:
    extra = extra or Extra()
    project = asdict(extra)
    project.pop("texts")
    project.pop("findings")
    project["undefined"] = [{"key": k, "file": f, "line": n} for k, f, n in extra.undefined]
    return json.dumps(
        {
            "tool": "paper-proof",
            "version": __version__,
            "source": source,
            "summary": summary(verdicts) | {"undefined": len(extra.undefined)},
            "references": [v.to_dict() for v in verdicts],
            "duplicates": [{"first": a, "second": b, "why": why} for a, b, why in dups],
            "findings": [f.to_dict() for f in extra.findings],
            "project": project if extra.main else None,
        },
        indent=2,
        ensure_ascii=False,
    )


def _md(s: str) -> str:
    """Text in a Markdown table cell: nothing in it renders (links, autolinked URLs, images, HTML, mentions).

    >>> out = _md("see https://evil.example and www.evil.example [x](y) @someone")
    >>> "://" in out, "www." in out, "[x](y)" in out, "@someone" in out
    (False, False, False, False)
    """
    s = visible(s).replace("\n", " ").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # brackets (links, images), code, emphasis, the table's pipe; parentheses render nothing without brackets
    s = re.sub(r"([\\`*_\[\]|~])", r"\\\1", s)
    # GitHub links bare URLs and www. addresses by itself: a zero-width space breaks the pattern, not the text
    s = s.replace("://", ":​//").replace("www.", "www​.")
    return s.replace("@", "@​")


def _code(s: str) -> str:
    """A code span: nothing inside renders, so only backticks, newlines and the table's | need care."""
    s = visible(s).replace("`", "'").replace("\n", " ").replace("|", "\\|")
    return f"`{s}`"


def markdown(verdicts: list[Verdict], dups: list[tuple[str, str, str]], source: str, extra: Extra | None = None) -> str:
    extra = extra or Extra()
    s = summary(verdicts)
    out = [f"### paper-proof: {_md(_scope(extra, len(verdicts)))} in {_code(source)}", ""]
    counts = [f"**{n}** {LABEL[k] if k not in ('ok', 'skipped') else k}" for k, n in s.items() if n]
    if extra.undefined:
        counts.insert(0, f"**{len(extra.undefined)}** UNDEFINED")
    out.append(" · ".join(counts))
    if extra.undefined:
        out += [""] + [f"- {_code(chr(92) + 'cite{' + k + '}')} at {_code(f'{f}:{n}')} has no bibliography entry" for k, f, n in extra.undefined]
    if extra.findings:
        out += ["", "| | Where | The paper against itself |", "|---|---|---|"]
        out += [f"| {FINDING_LABEL[f.severity]} | {_code(f'{f.file}:{f.line}')} | {_md(f.message)} |" for f in extra.findings]
    rows = [v for v in sorted(verdicts, key=lambda v: (ORDER.index(v.status), v.line)) if v.status not in ("ok", "skipped") or v.notes]
    if rows:
        out += ["", "| | Reference | What was found |", "|---|---|---|"]
        for v in rows:
            found = "; ".join(v.problems + v.notes) + (f' — closest: "{v.closest}"' if v.closest else "")
            title = v.title if len(v.title) <= 90 else v.title[:89] + "…"
            out.append(f"| {LABEL[v.status]} | {_code(v.key)} {_md(title)} | {_md(found)} |")
    if dups:
        out += [""] + [f"- Duplicate: {_code(a)} and {_code(b)} ({why})" for a, b, why in dups]
    return "\n".join(out)
