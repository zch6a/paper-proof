"""Reports: for a terminal, as JSON, and as Markdown (for a pull request or a review). Text from the bibliography and
from the databases is untrusted: control characters are shown, never sent to the terminal.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

from . import __version__
from .check import Verdict

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


def use_color(stream=sys.stdout) -> bool:
    return not os.environ.get("NO_COLOR") and (bool(os.environ.get("FORCE_COLOR")) or (hasattr(stream, "isatty") and stream.isatty()))


def summary(verdicts: list[Verdict]) -> dict[str, int]:
    c = Counter(v.status for v in verdicts)
    return {k: c.get(k, 0) for k in ORDER}


def text(verdicts: list[Verdict], dups: list[tuple[str, str, str]], source: str, color: bool = False) -> str:
    paint = (lambda code, s: f"\x1b[{code}m{s}\x1b[0m") if color else (lambda code, s: s)
    out = [f"paper-proof {__version__} · {visible(source)}: {len(verdicts)} references", ""]
    for v in sorted(verdicts, key=lambda v: (ORDER.index(v.status), v.line)):
        if v.status == "ok" and not v.notes:
            continue
        where = f" (line {v.line})" if v.line else ""
        out.append(f"{paint(COLOR[v.status], LABEL[v.status].ljust(9))} {visible(v.key)}{where}")
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
    s = summary(verdicts)
    parts = [f"{n} {LABEL[k] if k not in ('ok', 'skipped') else k}" for k, n in s.items() if n]
    out.append("Summary: " + ", ".join(parts) + (f", {len(dups)} duplicate(s)" if dups else ""))
    if s["unknown"]:
        out.append("Unknown means a database did not answer; run again later (answers are cached).")
    return "\n".join(out)


def to_json(verdicts: list[Verdict], dups: list[tuple[str, str, str]], source: str) -> str:
    return json.dumps(
        {
            "tool": "paper-proof",
            "version": __version__,
            "source": source,
            "summary": summary(verdicts),
            "references": [v.to_dict() for v in verdicts],
            "duplicates": [{"first": a, "second": b, "why": why} for a, b, why in dups],
        },
        indent=2,
        ensure_ascii=False,
    )


def _md(s: str) -> str:
    """Text in a Markdown table cell: nothing in it renders (links, images, HTML, mentions)."""
    s = visible(s).replace("\n", " ").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"([\\`*_{}\[\]()#+!|~])", r"\\\1", s)
    return s.replace("@", "@​")


def _code(s: str) -> str:
    """A code span: nothing inside renders, so only backticks, newlines and the table's | need care."""
    s = visible(s).replace("`", "'").replace("\n", " ").replace("|", "\\|")
    return f"`{s}`"


def markdown(verdicts: list[Verdict], dups: list[tuple[str, str, str]], source: str) -> str:
    s = summary(verdicts)
    out = [f"### paper-proof: {len(verdicts)} references in {_code(source)}", ""]
    out.append(" · ".join(f"**{n}** {LABEL[k] if k not in ('ok', 'skipped') else k}" for k, n in s.items() if n))
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
