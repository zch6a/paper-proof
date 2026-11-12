r"""Reading a LaTeX project: which works the text really cites (\cite and its natbib/biblatex relatives, followed
through \input and \include), where the bibliography is (.bib files, a compiled .bbl, or a thebibliography
environment), and the references themselves in comparable form.

Only what is cited is checked; entries nobody cites and \cite keys with no entry are reported on their own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import sources
from .bib import _matching, parse_bib, plain
from .check import Reference, clean_doi, reference_from_bib

CITE = re.compile(
    r"\\(?:[Cc]ite(?:p|t|alp|alt|author|year|yearpar|num|title|url|date)?|[Pp]arencite|[Tt]extcite|[Aa]utocite|[Ff]ootcite"
    r"|[Ss]martcite|supercite|fullcite|footfullcite|nocite)\*?((?:\s*\[[^\]]*\])*)\s*\{([^}]*)\}"
)
MULTICITE = re.compile(r"\\(?:[Cc]ites|[Pp]arencites|[Tt]extcites|[Aa]utocites|[Ff]ootcites)((?:\s*(?:\[[^\]]*\])*\s*\{[^}]*\})+)")
INPUT = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]+)\}|\\(?:sub)?import\s*\{([^}]*)\}\s*\{([^}]+)\}")
BIBLIOGRAPHY = re.compile(r"\\bibliography\s*\{([^}]+)\}|\\addbibresource\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


def strip_comments(text: str) -> str:
    r"""Comments removed, line breaks kept (so line numbers stay right).

    >>> strip_comments("a % b\nc \\% d % e\n")
    'a \nc \\% d \n'
    """
    return re.sub(r"(?<!\\)((?:\\\\)*)%[^\n]*", r"\1", text)


def strip_dead(text: str) -> str:
    r"""Text that never reaches the PDF blanked out, line breaks kept: \iffalse ... \fi (nested \if...\fi inside
    counted) and comment environments.

    >>> strip_dead("a \\iffalse b \\ifx c\\fi d \\fi e") == "a" + " " * 28 + "e"
    True
    >>> strip_dead("x\n\\begin{comment}\ny\n\\end{comment}\nz")
    'x\n               \n \n             \nz'
    """
    blank = lambda s: re.sub(r"[^\n]", " ", s)  # noqa: E731
    text = re.sub(r"\\begin\{comment\}.*?\\end\{comment\}", lambda m: blank(m.group(0)), text, flags=re.S)
    out, i = [], 0
    for m in re.finditer(r"\\iffalse\b", text):
        if m.start() < i:
            continue
        depth, j = 1, m.end()
        for t in re.finditer(r"\\(if[a-zA-Z@]*|fi)\b", text[m.end() :]):
            if t.group(1) == "fi":
                depth -= 1
            elif t.group(1) not in ("ifthenelse", "iftoggle"):
                depth += 1
            if depth == 0:
                j = m.end() + t.end()
                break
        else:
            j = len(text)
        out.append(text[i : m.start()])
        out.append(blank(text[m.start() : j]))
        i = j
    out.append(text[i:])
    return "".join(out)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


@dataclass
class Project:
    main: Path
    files: list[Path] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)  # file (relative to the main file's folder) -> text without comments
    cited: dict[str, tuple[str, int]] = field(default_factory=dict)  # key -> where it is first cited
    cite_all: bool = False  # \nocite{*}
    bib_files: list[Path] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)  # every entry of the bibliography
    bibliography_from: str = ""  # "bib", "bbl" or "thebibliography"

    def checked(self) -> list[Reference]:
        """The references the text cites (all of them after \nocite{*})."""
        return self.references if self.cite_all or not self.cited else [r for r in self.references if r.key in self.cited]

    def uncited(self) -> list[Reference]:
        return [] if self.cite_all or not self.cited else [r for r in self.references if r.key not in self.cited]

    def undefined(self) -> list[tuple[str, str, int]]:
        """Keys cited in the text with no entry in the bibliography (they print as [?] in the paper)."""
        known = {r.key for r in self.references}
        return [(k, f, n) for k, (f, n) in self.cited.items() if k not in known]


def find_main(directory: Path) -> Path | None:
    """The file with \\documentclass and \\begin{document}; main.tex, paper.tex or ms.tex when there are several."""
    candidates = []
    for p in sorted(directory.rglob("*.tex")):
        try:
            t = strip_comments(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "\\documentclass" in t and "\\begin{document}" in t:
            candidates.append(p)
    for name in ("main.tex", "paper.tex", "ms.tex", "manuscript.tex"):
        for p in candidates:
            if p.name.lower() == name:
                return p
    return min(candidates, key=lambda p: (len(p.relative_to(directory).parts), p.name)) if candidates else None


def _resolve(root: Path, base: Path, name: str, ext: str) -> Path | None:
    """A file named in the project, looked up relative to the main file's folder; never outside the project."""
    name = name.strip()
    for folder in (base, root):
        p = (folder / name).resolve()
        for q in (p, p.with_name(p.name + ext)):
            if q.is_file() and (q == root or root in q.parents):
                return q
    return None


def read_project(main: Path) -> Project:
    main = main.resolve()
    root = main.parent
    proj = Project(main=main)
    thebibliography: list[tuple[str, Path]] = []
    seen: set[Path] = set()

    def visit(path: Path, depth: int) -> None:
        if path in seen or depth > 20:
            return
        seen.add(path)
        proj.files.append(path)
        text = strip_dead(strip_comments(path.read_text(encoding="utf-8", errors="replace")))
        rel = path.relative_to(root).as_posix()
        proj.texts[rel] = text
        # Citations and \input in the order they appear, so "first cited at" follows the paper's reading order.
        events = [(m.start(), "cite", m) for m in CITE.finditer(text)]
        events += [(m.start(), "multi", m) for m in MULTICITE.finditer(text)]
        events += [(m.start(), "input", m) for m in INPUT.finditer(text)]
        for pos, kind, m in sorted(events, key=lambda e: e[0]):
            if kind == "input":
                name = m.group(1) or (m.group(2) or "") + "/" + m.group(3)
                p = _resolve(root, path.parent, name, ".tex")
                if p is not None:
                    visit(p, depth + 1)
                elif not name.strip().endswith((".bbl", ".sty", ".cls")):
                    proj.missing_files.append(name.strip())
                continue
            groups = [m.group(2)] if kind == "cite" else re.findall(r"\{([^}]*)\}", m.group(1))
            for group in groups:
                for k in group.split(","):
                    k = k.strip()
                    if k == "*":
                        proj.cite_all = True
                    elif k:
                        proj.cited.setdefault(k, (rel, _line(text, pos)))
        for m in BIBLIOGRAPHY.finditer(text):
            for name in (m.group(1) or m.group(2)).split(","):
                p = _resolve(root, path.parent, name, ".bib")
                if p is None:
                    proj.missing_files.append(name.strip() + ("" if name.strip().endswith(".bib") else ".bib"))
                elif p not in proj.bib_files:
                    proj.bib_files.append(p)
        if "\\begin{thebibliography}" in text:
            thebibliography.append((text, path))

    visit(main, 0)

    if proj.bib_files:
        proj.bibliography_from = "bib"
        for p in proj.bib_files:
            for e in parse_bib(p.read_text(encoding="utf-8-sig", errors="replace")):
                r = reference_from_bib(e)
                r.file = p.relative_to(root).as_posix()
                proj.references.append(r)
    elif thebibliography:
        proj.bibliography_from = "thebibliography"
        for text, path in thebibliography:
            proj.references += parse_bbl(text, path.relative_to(root).as_posix())
    else:
        bbl = main.with_suffix(".bbl")
        if bbl.is_file():
            proj.bibliography_from = "bbl"
            proj.references = parse_bbl(bbl.read_text(encoding="utf-8", errors="replace"), bbl.name)
    return proj


# ---------------------------------------------------------------- .bbl and thebibliography

YEAR = re.compile(r"(?<![\d.])((?:19|20)\d{2})(?:[a-z]\b)?(?!\d)")
DOI = re.compile(r"\b10\.\d{4,9}/[^\s{}\\,]+[^\s{}\\,.;]")
QUOTED = re.compile(r"``(.+?)(?:,|\.)?''|“(.+?)[,.]?”|\\enquote\{([^}]*)\}", re.S)
VENUE_WORDS = re.compile(r"\b(?:In |Proceedings|Proc\.|Journal|Conference|Transactions|Trans\.|arXiv|CoRR|Advances in|vol\.|volume|pp\.|pages)", re.I)


def parse_bbl(text: str, filename: str = "") -> list[Reference]:
    """References from a compiled bibliography: BibTeX's \\bibitem list (any style) or biblatex's \\entry records."""
    if "\\entry{" in text and "\\endentry" in text:
        return _biblatex_bbl(text, filename)
    out = []
    items = list(re.finditer(r"\\bibitem\s*(?:\[(?:[^\[\]]|\[[^\]]*\])*\])?\s*\{([^}]+)\}", text))
    for i, m in enumerate(items):
        end = items[i + 1].start() if i + 1 < len(items) else len(text)
        body = text[m.end() : end].split("\\end{thebibliography}")[0]
        out.append(_bibitem(m.group(1).strip(), body, _line(text, m.start()), filename))
    return out


def _bibitem(key: str, body: str, line: int, filename: str) -> Reference:
    r"""One \bibitem in any common style: natbib (plainnat, ICML, NeurIPS), ACL, IEEE (quoted titles), plain/alpha.

    >>> r = _bibitem("v", "Ashish Vaswani, Noam Shazeer, and Niki Parmar.\n\\newblock Attention is all you need.\n"
    ...              "\\newblock In \\emph{NeurIPS}, 2017.", 1, "")
    >>> (r.title, r.authors, r.year)
    ('Attention is all you need', ['Vaswani', 'Shazeer', 'Parmar'], 2017)
    >>> r = _bibitem("h", "K.~He, X.~Zhang, S.~Ren, and J.~Sun, ``Deep residual learning for image recognition,'' in "
    ...              "\\emph{CVPR}, 2016, pp. 770--778.", 1, "")
    >>> (r.title, r.authors, r.year)
    ('Deep residual learning for image recognition', ['He', 'Zhang', 'Ren', 'Sun'], 2016)
    """
    raw = re.sub(r"\\natexlab\{[^}]*\}|\\penalty0|\\BIBentry\w*|\\bibinfo\{[^}]*\}", "", body)
    url = re.search(r"\\(?:url|href)\{([^}]*)\}", raw)
    ident_text = raw.replace("\\_", "_")
    raw = re.sub(r"\\href\s*\{[^}]*\}", "", raw)  # \href{target}{text}: the text stays
    doi = m.group(0) if (m := DOI.search(ident_text)) else ""
    arx = ""
    if m := re.search(r"arXiv[:\s]*(?:preprint\s+)?(?:arXiv:)?\s*(\d{4}\.\d{4,5})|arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", ident_text, re.I):
        arx = m.group(1) or m.group(2)
    blocks = [b for b in (plain(x) for x in re.split(r"\\newblock", raw)) if b]
    q = QUOTED.search(raw)
    if q:
        title = plain(next(g for g in q.groups() if g))
        author_part = plain(raw[: q.start()])
        venue = plain(raw[q.end() :])
    elif len(blocks) >= 2:
        title = blocks[1]
        author_part = blocks[0]
        venue = " ".join(blocks[2:])
    else:
        title, author_part, venue = "", blocks[0] if blocks else "", ""
    title = re.sub(r"[.,;:\s]+$", "", title)
    years = YEAR.findall(author_part) or YEAR.findall(plain(raw))
    year = int(years[0] if YEAR.findall(author_part) else years[-1]) if years else None
    names = YEAR.sub("", author_part)
    names = re.sub(r"\(\s*\)|\bet al\.?|\bothers\b|\(eds?\.\)|\beds?\.", "", names)
    families = []
    for part in re.split(r"\s*,\s*and\s+|\s+and\s+|\s*&\s*|\s*,\s*|\s*;\s*", names.strip(" .,")):
        part = part.strip(" .")
        if not part or re.fullmatch(r"(?:[A-Z]\.?\s*-?\s*)+", part):
            continue
        families.append(part.split()[-1])
    preprint = bool(arx) and not re.search(r"\bIn\b", venue) and bool(re.search(r"arXiv|CoRR", venue + " " + title, re.I))
    kind = "misc" if (url and not doi and not arx and not VENUE_WORDS.search(venue)) else ""
    return Reference(
        key=key,
        title=title,
        authors=families,
        year=year,
        venue=venue[:200],
        doi=clean_doi(doi) if doi else "",
        arxiv=arx,
        kind=kind,
        line=line,
        cited_as_preprint=preprint,
        file=filename,
    )


def _field(body: str, name: str) -> str:
    m = re.search(r"\\field\{" + name + r"\}\{", body)
    if not m:
        return ""
    end = _matching(body, m.end(), "{", "}")
    return body[m.end() : end] if end > 0 else ""


def _verb(body: str, name: str) -> str:
    m = re.search(r"\\verb\{" + name + r"\}\s*\\verb\s+(.*?)\s*\\endverb", body, re.S)
    return m.group(1).strip() if m else ""


def _biblatex_bbl(text: str, filename: str) -> list[Reference]:
    out = []
    for m in re.finditer(r"\\entry\{([^}]+)\}\{([^}]+)\}\{[^}]*\}(.*?)\\endentry", text, re.S):
        key, kind, body = m.group(1), m.group(2).lower(), m.group(3)
        families = []
        nm = re.search(r"\\name\{author\}\{\d+\}\{[^}]*\}\{", body)
        if nm:
            end = _matching(body, nm.end(), "{", "}")
            families = [plain(f) for f in re.findall(r"family=\{((?:[^{}]|\{[^{}]*\})*)\}", body[nm.end() : end])]
        year_s = _field(body, "year") or _field(body, "labelyear")
        eprint = _field(body, "eprint") if _field(body, "eprinttype").lower() in ("arxiv", "") else ""
        arx = m2.group(1) if (m2 := sources.ARXIV_ID.search(eprint)) else ""
        journal = _field(body, "journaltitle")
        out.append(
            Reference(
                key=key,
                title=plain(_field(body, "title")),
                authors=families,
                year=int(year_s) if year_s.isdigit() else None,
                venue=plain(journal or _field(body, "booktitle")),
                doi=clean_doi(_verb(body, "doi")) if _verb(body, "doi") else "",
                arxiv=arx,
                kind=kind,
                line=_line(text, m.start()),
                cited_as_preprint=bool(arx) and kind in ("misc", "online", "report", "article") and (not journal or "arxiv" in journal.lower()),
                file=filename,
            )
        )
    return out
