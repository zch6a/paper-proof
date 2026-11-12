"""BibTeX, read the way BibTeX reads it: nested braces, quoted values, @string macros joined with #, comments.

Only what checking needs is kept: the entry type, its key, its fields, and the line it starts on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# The standard month macros every BibTeX style defines.
MONTHS = {m: str(i) for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


@dataclass
class Entry:
    type: str
    key: str
    fields: dict[str, str] = field(default_factory=dict)
    line: int = 1

    def get(self, name: str) -> str:
        return self.fields.get(name, "")


class BibError(ValueError):
    pass


def parse_bib(text: str) -> list[Entry]:
    """Every entry in a .bib file.

    >>> [e.key for e in parse_bib('@article{a, title={X}} @misc{b, title="Y"}')]
    ['a', 'b']
    >>> parse_bib('@string{nips = "NeurIPS"} @inproceedings{k, booktitle = "Proc. " # nips}')[0].get('booktitle')
    'Proc. NeurIPS'
    """
    entries: list[Entry] = []
    macros: dict[str, str] = dict(MONTHS)
    i = 0
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        m = re.compile(r"@\s*([A-Za-z]+)\s*([{(])").match(text, at)
        if not m:
            i = at + 1
            continue
        kind = m.group(1).lower()
        close = "}" if m.group(2) == "{" else ")"
        body_start = m.end()
        end = _matching(text, body_start, m.group(2), close)
        if end < 0:
            raise BibError(f"line {text.count(chr(10), 0, at) + 1}: @{kind} is never closed")
        body = text[body_start:end]
        line = text.count("\n", 0, at) + 1
        i = end + 1
        if kind in ("comment", "preamble"):
            continue
        if kind == "string":
            for name, value in _fields(body, macros, line):
                macros[name] = value
            continue
        key, _, rest = body.partition(",")
        entry = Entry(type=kind, key=key.strip(), line=line)
        for name, value in _fields(rest, macros, line):
            entry.fields[name] = value
        entries.append(entry)
    return entries


def _matching(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Index of the bracket that closes the one just before `start`. Braces nest inside either kind; an entry
    opened with `(` ends at the `)` outside all braces. A backslash escapes the next character (`\\{`)."""
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0 and close_ch == "}":
                return i
            depth -= 1
        elif c == ")" and close_ch == ")" and depth == 0:
            return i
        i += 1
    return -1


def _fields(body: str, macros: dict[str, str], line: int):
    """(name, value) pairs of `name = value, ...`; a value is {..}, "..", a number, a macro, or joined with #."""
    i, n = 0, len(body)
    while i < n:
        m = re.compile(r"\s*,?\s*([A-Za-z][\w:.+-]*)\s*=\s*").match(body, i)
        if not m:
            break
        name = m.group(1).lower()
        i = m.end()
        parts: list[str] = []
        while i < n:
            c = body[i]
            if c == "{":
                end = _matching(body, i + 1, "{", "}")
                if end < 0:
                    raise BibError(f"entry at line {line}: the value of {name} is never closed")
                parts.append(body[i + 1 : end])
                i = end + 1
            elif c == '"':
                j = i + 1
                depth = 0
                while j < n and not (body[j] == '"' and depth == 0 and body[j - 1] != "\\"):
                    if body[j] == "{":
                        depth += 1
                    elif body[j] == "}":
                        depth -= 1
                    j += 1
                parts.append(body[i + 1 : j])
                i = j + 1
            else:
                w = re.compile(r"[^\s,#}]+").match(body, i)
                if not w:
                    break
                token = w.group(0)
                parts.append(token if token.isdigit() else macros.get(token.lower(), token))
                i = w.end()
            concat = re.compile(r"\s*#\s*").match(body, i)
            if concat:
                i = concat.end()
                continue
            break
        yield name, "".join(parts).strip()


# ---------------------------------------------------------------- LaTeX to plain text

_ACCENTS = {
    "'": "\u0301",
    "`": "\u0300",
    "^": "\u0302",
    '"': "\u0308",
    "~": "\u0303",
    "=": "\u0304",
    ".": "\u0307",
    "u": "\u0306",
    "v": "\u030c",
    "H": "\u030b",
    "c": "\u0327",
    "k": "\u0328",
    "r": "\u030a",
}
_LETTERS = {"ss": "ß", "o": "ø", "O": "Ø", "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ", "aa": "å", "AA": "Å", "l": "ł", "L": "Ł", "i": "ı", "j": "ȷ"}
_STYLE = re.compile(r"\\(?:emph|textbf|textit|texttt|textsc|textrm|textsf|mathrm|mathbf|mathit|mathcal|text|url|bf|it|em|sc|rm|tt)\b\s*")


def plain(s: str) -> str:
    """A LaTeX field as text: accents applied, styling and braces dropped, spaces normalised.

    >>> plain(r"{G}{\\\"o}del's {\\em Theorem} -- a {N}ew {V}iew")
    "Gödel's Theorem – a New View"
    >>> plain(r"Stra{\\ss}e \\& M\\'{e}t{\\'e}o")
    'Straße & Météo'
    """
    import unicodedata

    s = _STYLE.sub("", s)

    def accent(m: re.Match[str]) -> str:
        mark, letter = m.group(1), m.group(2) or m.group(3) or ""
        letter = {"\\i": "i", "\\j": "j"}.get(letter, letter)
        return unicodedata.normalize("NFC", letter + _ACCENTS[mark]) if letter else ""

    s = re.sub(r"\\([\'`^\"~=.]|[uvHckr](?=[\s{]))\s*(?:\{(\\?[A-Za-z]?)\}|(\\?[A-Za-z]))", accent, s)
    s = re.sub(r"\\(ss|ae|AE|oe|OE|aa|AA|o|O|l|L)\b\s*(?:\{\})?", lambda m: _LETTERS[m.group(1)], s)
    s = s.replace("\\&", "&").replace("\\%", "%").replace("\\_", "_").replace("\\$", "$").replace("\\#", "#")
    s = s.replace("---", "—").replace("--", "–").replace("``", '"').replace("''", '"').replace("~", " ")
    s = re.sub(r"\\[A-Za-z]+\s*", "", s)  # any other command: dropped (its argument stays)
    s = s.replace("{", "").replace("}", "").replace("$", "")
    return re.sub(r"\s+", " ", s).strip()


def authors(field_value: str) -> list[str]:
    """Family names of a BibTeX author list (`and` at brace depth 0; "Last, First" or "First von Last").

    >>> authors(r"Vaswani, Ashish and Noam Shazeer and {Google Brain Team} and others")
    ['Vaswani', 'Shazeer', 'Google Brain Team']
    >>> authors(r"Ludwig van Beethoven and de la Fontaine, Jean")
    ['van Beethoven', 'de la Fontaine']
    """
    names: list[str] = []
    depth, i = 0, 0
    cur: list[str] = []
    s = field_value
    sep = re.compile(r"\s+and\s+", flags=re.I)
    while i < len(s):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        m = sep.match(s, i) if depth == 0 and c.isspace() else None
        if m:
            names.append("".join(cur))
            cur = []
            i = m.end()
            continue
        cur.append(c)
        i += 1
    names.append("".join(cur))
    out = []
    for raw in names:
        raw = raw.strip()
        if not raw or raw.lower() == "others":
            continue
        if raw.startswith("{") and raw.endswith("}") and _matching(raw, 1, "{", "}") == len(raw) - 1:
            out.append(plain(raw))  # an institution, kept whole
            continue
        if "," in _depth0(raw):
            out.append(plain(_depth0_split(raw)[0]))
            continue
        words = plain(raw).split()
        # "von" parts start lower case: everything from the first lower-case word (not the last word) on.
        k = next((j for j, w in enumerate(words[:-1]) if w[:1].islower()), len(words) - 1)
        out.append(" ".join(words[k:]))
    return out


def _depth0(s: str) -> str:
    out, depth = [], 0
    for c in s:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif depth == 0:
            out.append(c)
    return "".join(out)


def _depth0_split(s: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for c in s:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return parts
