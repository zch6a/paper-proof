r"""References from a PDF, for when there is no LaTeX source (a review, a published paper): the text of the
References section, split into entries ([1] ..., 1. ..., or author-year lists), each read for its title, authors,
year, DOI and arXiv id. The whole entry is kept too: when the title cannot be told apart, Crossref matches the entry
as a whole.

Only references are checked in a PDF: tables lose their structure (and bold) in extracted text.
"""

from __future__ import annotations

import re
from pathlib import Path

from .check import Reference, clean_doi
from .latex import DOI, YEAR, clean_title, family_names

HEADING = re.compile(r"^\s*(?:\d+\.?\s*|[IVX]+\.\s*)?(?:references|bibliography|literature cited|works cited|reference list)\s*$", re.I | re.M)
# Where the references end: an appendix or a checklist heading on a line of its own.
END = re.compile(
    r"^\s*(?:appendix\b.*|appendices|supplementary materials?\b.*|neurips paper checklist|checklist|"
    r"[A-H](?:\.\d+)?\s+[A-Z][A-Za-z\-]+(?:\s+[A-Za-z\-]+){0,8})\s*$",
    re.M,
)
# How an entry's last line ends: a period, or a year, an arXiv id or a URL with no period after it.
ENTRY_END = re.compile(r"(?:\.|(?:19|20)\d{2}[a-z]?\)?|\d{4}\.\d{4,5}(?:v\d+)?|https?://\S+)\s*$")
NAME_START = re.compile(r"^(?:[A-Z][\w'’\-]+(?:\s+(?:[A-Z]\.\s*)+)?(?:\s+(?:van|von|de|der|da|di|le|la)\b)?(?:\s+[A-Z][\w'’\-]+)?)(?:,|\s+and\s)")
ABBREVIATIONS = (
    r"(?:vs|Proc|Conf|Int|Intl|Adv|Vol|vol|pp|No|no|Jr|Sr|Dr|St|Univ|Dept|Inc|Ltd|Comput|Assoc|Ling|Mach|Learn|"
    r"Res|Trans|Syst|Neural|Inf|Process|Rev|Lett|Phys|Sci|Eng|Stat|Math|Appl|J|Am|Soc|Ann|Nat)"
)


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def references_section(text: str) -> str:
    """The text after the last "References" heading, up to an appendix heading (if any)."""
    heads = list(HEADING.finditer(text))
    if not heads:
        return ""
    start = heads[-1].end()
    body = text[start:]
    # an appendix heading only counts after a few entries
    for m in END.finditer(body):
        if body[: m.start()].count("\n") >= 6:
            return body[: m.start()]
    return body


def split_entries(section: str) -> list[str]:
    """Entries of a references section: "[12] ...", "12. ...", or author-year entries (a new one starts after a line
    ending with a period, on a line that begins like an author list)."""
    section = re.sub(r"(\w)-\n(\w)", r"\1-\2", section)  # a word broken across lines keeps its hyphen; matching ignores it
    section = re.sub(r"[ \t]+", " ", section)
    bracketed = re.findall(r"^\s*\[(\d+)\]\s", section, re.M)
    if len(bracketed) >= 3:
        parts = re.split(r"^\s*\[\d+\]\s+", section, flags=re.M)
        return [_one_line(p) for p in parts[1:] if p.strip()]
    numbered = re.findall(r"^\s*(\d+)\.\s+[A-Z]", section, re.M)
    if len(numbered) >= 3 and [int(x) for x in numbered[:3]] == [1, 2, 3]:
        parts = re.split(r"^\s*\d+\.\s+(?=[A-Z])", section, flags=re.M)
        return [_one_line(p) for p in parts[1:] if p.strip()]
    entries: list[list[str]] = []
    for line in (x.strip() for x in section.split("\n")):
        if not line:
            continue
        if not entries or (ENTRY_END.search(entries[-1][-1]) and NAME_START.match(line)):
            entries.append([line])
        else:
            entries[-1].append(line)
    return [_one_line(" ".join(e)) for e in entries]


def _one_line(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip()


def reference_from_string(key: str, s: str, number: int = 0) -> Reference:
    """One printed reference read for its parts, in the usual styles:

    >>> r = reference_from_string("1", "Ashish Vaswani, Noam Shazeer, and Niki Parmar. Attention is all you need. "
    ...                                "In NeurIPS, 2017.")
    >>> (r.title, r.authors, r.year)
    ('Attention is all you need', ['Vaswani', 'Shazeer', 'Parmar'], 2017)
    >>> r = reference_from_string("2", "Kaiming He, Xiangyu Zhang, Shaoqing Ren, and Jian Sun. 2016. "
    ...                                "Deep residual learning for image recognition. In CVPR.")
    >>> (r.title, r.year)
    ('Deep residual learning for image recognition', 2016)
    >>> r = reference_from_string("3", "D. P. Kingma and J. Ba, “Adam: A method for stochastic optimization,” in Proc. ICLR, 2015.")
    >>> (r.title, r.authors)
    ('Adam: A method for stochastic optimization', ['Kingma', 'Ba'])
    >>> r = reference_from_string("4", "Vaswani, A., Shazeer, N.: Attention is all you need. In: NIPS (2017)")
    >>> (r.title, r.authors, r.year)
    ('Attention is all you need', ['Vaswani', 'Shazeer'], 2017)
    """
    # PDF text often loses the space after a period: "linear time.arXiv preprint", "2017.In Proceedings"
    s = re.sub(r"(?<=[a-z0-9)])([.?!])(?=(?:arXiv|ArXiv|CoRR|In\b|Proceedings|Advances|URL|https?:|Technical|Preprint)\b)", r"\1 ", s)
    # and adds one before it after an initial: "Y . Bai", "V . Chandrasekaran"
    s = re.sub(r"\b([A-Z]) \.(?=[\s,])", r"\1.", s)
    doi = m.group(0) if (m := DOI.search(s)) else ""
    arx = ""
    if m := re.search(r"arXiv[:\s]*(?:preprint\s+)?(?:arXiv:)?\s*(\d{4}\.\d{4,5})|arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", s, re.I):
        arx = m.group(1) or m.group(2)
    title, authors_part, venue = "", "", ""
    q = re.search(r"[“\"](.+?)[,.]?[”\"]", s)
    if q and len(q.group(1)) > 10:
        title, authors_part, venue = q.group(1), s[: q.start()], s[q.end() :]
    else:
        # LNCS: "Names: Title. In: ..."
        c = re.match(r"^([^:]{3,400}?):\s+(.*)$", s)
        # only when what precedes the colon is one sentence of names ("Vaswani, A., Shazeer, N.:"), not authors and
        # the first half of a title ("D. Kingma and J. Ba. Adam: A method ...")
        if c and re.search(r",|\band\b", c.group(1)) and len(_sentences(c.group(1))) == 1 and not re.search(r"\b(?:19|20)\d{2}\b", c.group(1)[-6:]):
            authors_part, rest = c.group(1), c.group(2)
            segs = _sentences(rest)
            title, venue = (segs[0], " ".join(segs[1:])) if segs else ("", "")
        else:
            segs = [x for x in _sentences(s) if not re.fullmatch(r"\(?(?:19|20)\d{2}[a-z]?\)?", x.strip())]
            if len(segs) >= 2:
                authors_part, title, venue = segs[0], segs[1], " ".join(segs[2:])
            elif segs:
                authors_part = segs[0]
    title = re.sub(r"^\s*In\s*:?\s+.*", "", title)  # "In Proceedings ..." is a venue, not a title
    title = clean_title(title).strip()
    years = YEAR.findall(authors_part) or YEAR.findall(s)
    year = int(years[0] if YEAR.findall(authors_part) else years[-1]) if years else None
    preprint = bool(arx) and bool(re.search(r"arXiv|CoRR", venue, re.I)) and not re.search(r"\bIn\b", venue)
    url_only = bool(re.search(r"https?://", s)) and not doi and not arx and len(title) < 4
    return Reference(
        key=key,
        title=title,
        authors=family_names(authors_part),
        year=year,
        venue=venue[:200],
        doi=clean_doi(doi) if doi else "",
        arxiv=arx,
        kind="misc" if url_only else "",
        line=number,
        cited_as_preprint=preprint,
        raw=s,
    )


def _sentences(s: str) -> list[str]:
    """Split at ". " but not after initials (A. Vaswani) or common abbreviations (et al., Proc.)."""
    protected = re.sub(r"\b([A-Z])\.(?=\s|,|-)", "\\1\x00", s)
    protected = re.sub(r"\b(" + ABBREVIATIONS + r")\.(?=\s)", "\\1\x00", protected)
    # a title may end with ? or ! (kept), then the venue: "Can active memory replace attention? In NeurIPS"
    parts = re.split(r"\.\s+|(?<=[?!])\s+(?=[A-Z])", protected)
    return [p.replace("\x00", ".").strip() for p in parts if p and p.strip()]


def references_from_pdf(path: Path) -> list[Reference]:
    entries = split_entries(references_section(pdf_text(path)))
    return [reference_from_string(f"[{i}]", e, i) for i, e in enumerate(entries, 1)]
