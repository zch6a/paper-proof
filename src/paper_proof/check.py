"""Checking references: each one looked up by its identifiers and by its title, the best match compared with what
the bibliography says, and a verdict that never calls a reference missing when a database did not answer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from . import sources
from .bib import Entry, authors, plain
from .match import SAME_TITLE, Record, compare, norm_text, title_in, title_similarity
from .transport import Transport, TransportError

# Entry types the bibliographic databases index. Others (software, web pages, manuals) are only checked when they
# carry a DOI or an arXiv id: a missing web page in Crossref proves nothing.
INDEXED = {"article", "inproceedings", "conference", "incollection", "inbook", "book", "phdthesis", "mastersthesis", "proceedings"}


@dataclass
class Reference:
    key: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    arxiv: str = ""
    kind: str = ""
    line: int = 0
    cited_as_preprint: bool = False
    file: str = ""
    raw: str = ""  # the reference as printed (from a PDF): matched as a whole when its title cannot be told apart


def clean_doi(s: str) -> str:
    """>>> clean_doi("https://doi.org/10.1109/CVPR.2016.90 ")
    '10.1109/cvpr.2016.90'
    """
    s = s.strip()
    s = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/|^doi:\s*", "", s, flags=re.I)
    return s.lower().rstrip(".")


def reference_from_bib(e: Entry) -> Reference:
    """What a .bib entry claims, in comparable form (arXiv ids found in eprint, journal, url or note)."""
    title = plain(e.get("title"))
    year = int(m.group(0)) if (m := re.search(r"\b(1[5-9]|20)\d{2}\b", e.get("year"))) else None
    venue = plain(e.get("journal") or e.get("booktitle") or e.get("publisher") or e.get("howpublished"))
    arxiv = ""
    # An id counts in `eprint` (when the prefix is arXiv or not given) or where the field says arXiv
    # ("arXiv preprint arXiv:1810.04805", an arxiv.org URL): a bare 2101.00001 elsewhere may be anything.
    eprint_is_arxiv = e.get("archiveprefix").lower() in ("", "arxiv")
    for name in ("eprint", "journal", "url", "note", "howpublished", "arxiv"):
        value = e.get(name)
        m = sources.ARXIV_ID.search(value)
        if m and ((name == "eprint" and eprint_is_arxiv) or name == "arxiv" or "arxiv" in value.lower()):
            arxiv = m.group(1)
            break
    journal = e.get("journal").lower()
    preprint = bool(arxiv) and not e.get("booktitle") and (not journal or "arxiv" in journal or journal == "corr")
    return Reference(
        key=e.key,
        title=title,
        authors=authors(e.get("author")),
        year=year,
        venue=venue,
        doi=clean_doi(e.get("doi")) if e.get("doi") else "",
        arxiv=arxiv,
        kind=e.type,
        line=e.line,
        cited_as_preprint=preprint,
    )


@dataclass
class Verdict:
    key: str
    status: str  # ok | mismatch | not-found | retracted | unknown | skipped
    title: str
    line: int = 0
    file: str = ""
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    match: Record | None = None
    closest: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.match is None:
            d["match"] = None
        return d


Search = Callable[[Transport, str], list[Record]]
# Title searches, most precise first; checking stops at the first database with the same title.
TITLE_SEARCHES: list[tuple[str, Search]] = [
    ("semanticscholar", sources.s2_match),
    ("openalex", sources.openalex_search),
    ("crossref", lambda t, q: sources.crossref_search(t, q)),
    ("arxiv", sources.arxiv_search),
]
DB_NAME = {"semanticscholar": "Semantic Scholar", "openalex": "OpenAlex", "crossref": "Crossref", "arxiv": "arXiv"}
MIN_ANSWERED = 2


def _listing(names: list[str]) -> str:
    """'A', 'A or B', 'A, B or C'.

    >>> _listing(["OpenAlex", "Crossref", "arXiv"])
    'OpenAlex, Crossref or arXiv'
    """
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _best(ref: Reference, records: list[Record]) -> tuple[Record | None, float]:
    best, score = None, 0.0
    for r in records:
        s = title_similarity(ref.title, r.title)
        # Between equally similar titles, the one with more of the cited authors.
        bonus = 0.0
        if ref.authors and r.authors:
            from .match import author_overlap

            bonus = author_overlap(ref.authors, r.authors)[0] * 0.01
        if s + bonus > score:
            best, score = r, s + bonus
    return best, min(score, 1.0) if best else 0.0


def check_reference(ref: Reference, t: Transport) -> Verdict:
    v = Verdict(key=ref.key, status="ok", title=ref.title, line=ref.line, file=ref.file)
    if not ref.title and not ref.doi and not ref.arxiv and not ref.raw:
        v.status = "skipped"
        v.notes.append("no title, DOI or arXiv id to look up")
        return v
    if ref.kind and ref.kind not in INDEXED and not ref.doi and not ref.arxiv:
        v.status = "skipped"
        v.notes.append(f"@{ref.kind} without a DOI or arXiv id: such works are often not in bibliographic databases")
        return v

    errors: list[str] = []
    candidates: list[Record] = []

    # 1. Identifiers: exact lookups, and the identifier must point at the cited title.
    for label, ident, lookup in (("DOI", ref.doi, sources.crossref_doi), ("arXiv id", ref.arxiv, sources.arxiv_id)):
        if not ident:
            continue
        try:
            found = lookup(t, ident)
        except TransportError as e:
            errors.append(str(e))
            continue
        if not found:
            v.problems.append(f"{label} {ident} does not exist")
            continue
        r = found[0]
        if ref.title and title_similarity(ref.title, r.title) < SAME_TITLE:
            v.problems.append(f'{label} {ident} is a different work: "{r.title}"')
        else:
            candidates.append(r)

    # 2. The title, in each database until one has it.
    best, score = _best(ref, candidates)
    answered: list[str] = []
    if ref.title and score < SAME_TITLE:
        for name, search in TITLE_SEARCHES:
            try:
                found = search(t, ref.title)
            except TransportError as e:
                errors.append(str(e))
                continue
            answered.append(name)
            candidates.extend(found)
            best, score = _best(ref, candidates)
            if score >= SAME_TITLE:
                break

    # 2b. A reference read from a PDF, whose title may be cut wrong: the whole entry, matched by Crossref and
    # OpenAlex, and a hit counts only when its title is printed in the entry.
    if ref.raw and score < SAME_TITLE:
        raw_answered = 0
        for search in (sources.crossref_search, sources.openalex_text):
            try:
                found = search(t, ref.raw)
            except TransportError as e:
                errors.append(str(e))
                continue
            raw_answered += 1
            hit = next((r for r in found if r.title and title_in(r.title, ref.raw)), None)
            if hit:
                best, score = hit, 1.0
                v.title = v.title or hit.title
                break
        if score < SAME_TITLE and not ref.title:
            answered += ["crossref", "openalex"][:raw_answered]

    if best is None or score < SAME_TITLE:
        if errors and not candidates:
            v.status = "unknown"
            v.notes.append("could not check: " + "; ".join(sorted(set(errors))))
            return v
        if best is not None and score >= 0.75:
            v.closest = best.title
        # Two databases that answered and do not have it is enough to say so (Semantic Scholar often answers 429
        # without an API key); with fewer, the honest answer is "unknown".
        if errors and len(answered) < MIN_ANSWERED:
            v.status = "unknown"
            v.notes.append("not found in the databases that answered; others did not: " + "; ".join(sorted(set(errors))))
        else:
            v.status = "not-found"
            if errors:
                v.notes.append("did not answer: " + "; ".join(sorted(set(errors))))
        if ref.title or ref.raw:
            names = list(dict.fromkeys(answered)) or [n for n, _ in TITLE_SEARCHES]
            v.problems.append("no work with this title in " + _listing([DB_NAME[n] for n in names]))
        if ref.raw:
            v.notes.append(f"as printed: {ref.raw[:300]}")
        return v

    v.match = best
    cmp = compare(ref.title, ref.authors, ref.year, best)
    v.problems.extend(cmp.problems)

    # 3. Retraction (OpenAlex carries the Retraction Watch data).
    retracted = best.retracted or any(c.retracted and title_similarity(ref.title, c.title) >= SAME_TITLE for c in candidates)
    if not retracted and best.doi and best.source != "openalex":
        try:
            retracted = any(r.retracted for r in sources.openalex_doi(t, best.doi))
        except TransportError:
            v.notes.append("retraction status unknown (OpenAlex did not answer)")
    if retracted:
        v.status = "retracted"
        v.problems.insert(0, "this work has been retracted")
        return v

    # 4. A preprint that has since been published. The arXiv record rarely says so: when the exact lookup was all
    # that ran, ask the databases that know both versions.
    if ref.cited_as_preprint or (ref.venue and "arxiv" in ref.venue.lower()):

        def published_version() -> Record | None:
            for c in candidates:
                if c.published_in and "arxiv" not in c.published_in.lower() and title_similarity(ref.title, c.title) >= SAME_TITLE:
                    return c
            return None

        published = published_version()
        for name, search in TITLE_SEARCHES[:2]:
            if published or any(c.source == name for c in candidates):
                continue
            try:
                candidates.extend(search(t, ref.title))
            except TransportError:
                continue
            published = published_version()
        if published:
            year = f" ({published.year})" if published.year else ""
            v.notes.append(f"cited as an arXiv preprint, but published in {published.published_in}{year}")

    if v.problems:
        v.status = "mismatch"
    return v


def duplicates(refs: list[Reference]) -> list[tuple[str, str, str]]:
    """Pairs of entries for the same work (same DOI, arXiv id or title): (first key, second key, why)."""
    seen: dict[str, str] = {}
    out = []
    for r in refs:
        for kind, value in (("DOI", r.doi), ("arXiv id", r.arxiv), ("title", norm_text(r.title) if len(r.title) > 20 else "")):
            if not value:
                continue
            k = f"{kind}:{value}"
            if k in seen and seen[k] != r.key:
                out.append((seen[k], r.key, f"same {kind}"))
                break
            seen.setdefault(k, r.key)
    return out
