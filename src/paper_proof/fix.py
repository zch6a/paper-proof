"""A corrected copy of a .bib file: what the check found and can put right without guessing.

Changed: a preprint that has since been published becomes the published version (entry type, venue, year, DOI;
the arXiv id is kept); a year earlier than the work's own year becomes that year; a missing DOI is added when the
record is unmistakably the same work. Everything else in the file stays as it was. Not changed, and
listed for a person: references not found, wrong authors, a different work behind a DOI, retractions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .bib import Entry, parse_bib, plain
from .check import Verdict
from .latex import read_source
from .match import SAME_TITLE, Record, author_overlap, title_similarity
from .transport import Transport, TransportError

CONFERENCE = re.compile(
    r"(?i)\b(?:conference|proceedings|workshop|symposium|congress|findings|meeting|international joint|"
    r"neural information processing systems|neurips|nips|icml|iclr|cvpr|iccv|eccv|acl|emnlp|naacl|eacl|aacl|coling|"
    r"aaai|ijcai|kdd|sigir|siggraph|www|interspeech|icassp|aistats|uai|colt|corl|icra|iros|miccai|wacv|bmvc|chi|uist)\b"
)
JOURNAL = re.compile(r"(?i)\b(?:journal|transactions|letters|review|magazine|nature|science|tacl|jmlr|tmlr|pami)\b")
ARXIVISH = re.compile(r"(?i)arxiv|^corr$")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def venue_kind(name: str, said: str = "") -> str:
    """'conference', 'journal' or '' (cannot tell). The name decides; what the database said breaks a tie.

    >>> venue_kind("Advances in Neural Information Processing Systems"), venue_kind("Transactions on Machine Learning Research")
    ('conference', 'journal')
    >>> venue_kind("Proceedings of the IEEE"), venue_kind("Some Venue"), venue_kind("Some Venue", "journal")
    ('journal', '', 'journal')
    """
    if re.search(r"(?i)^proceedings of the ieee$", name.strip()):
        return "journal"
    journal, conference = bool(JOURNAL.search(name)), bool(CONFERENCE.search(name))
    if journal and not re.search(r"(?i)conference|proceedings|workshop", name):
        return "journal"
    if conference:
        return "conference"
    return said if said in ("conference", "journal") else ""


def published_year(rec: Record) -> int | None:
    """The year of the published version, only when it is certain: from its DOI's Crossref record, or from the
    venue's name ("NAACL 2019"). Semantic Scholar and OpenAlex often give the preprint's year (Adam: 2014, for
    ICLR 2015), so theirs is not used."""
    if rec.source == "crossref" and rec.year:
        return rec.year
    if m := YEAR.search(rec.published_in):
        return int(m.group(0))
    return None


def venue_name(s: str) -> str:
    """A venue as a booktitle or journal: arXiv's journal references carry pages, volumes and places after it.

    >>> venue_name("Proceedings of the SIGDIAL 2017 Conference, pages 201-206, Saarbrücken, Germany, 15-17 August 2017")
    'Proceedings of the SIGDIAL 2017 Conference'
    >>> venue_name("Phys. Rev. Lett. 123, 4567 (2019)"), venue_name("ICLR 2015")
    ('Phys. Rev. Lett.', 'ICLR 2015')
    """
    s = re.sub(r"\s+", " ", s).strip()
    s = re.split(r"(?i),?\s+(?:pages?|pp\.?|vol\.?|volume|no\.|article)\s*\d", s)[0]
    s = re.sub(r"\s+\d+\s*,\s*\d+.*$", "", s)  # "123, 4567 (2019)": volume, page, year
    return s.strip(" ,;")


def _arxiv_doi(doi: str) -> bool:
    return doi.lower().startswith("10.48550/arxiv")


def _bib_value(s: str) -> str:
    return re.sub(r"(?<!\\)([&%#])", r"\\\1", s)


@dataclass
class Fix:
    key: str
    line: int
    type: str = ""  # new entry type, or "" to keep it
    set: dict[str, str] = field(default_factory=dict)
    drop: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)


def plan(e: Entry, v: Verdict, t: Transport | None = None) -> Fix | None:
    """What to change in one entry, given its verdict; None when nothing can be changed safely. With a transport,
    a DOI from Semantic Scholar or OpenAlex is checked against its own Crossref record before it is used."""
    f = Fix(key=e.key, line=e.line)
    if v.status in ("not-found", "retracted", "unknown", "skipped"):
        return None
    year = int(m.group(0)) if (m := YEAR.search(e.get("year"))) else None
    title = plain(e.get("title"))

    pub = v.published
    if pub is not None:
        kind = venue_kind(pub.published_in, pub.published_kind)
        if kind:
            venue = venue_name(pub.published_in)
            journal = e.get("journal")
            if kind == "conference":
                f.type = "inproceedings" if e.type != "inproceedings" else ""
                f.set["booktitle"] = venue
                if journal:
                    f.drop.append("journal")
            else:
                f.type = "article" if e.type != "article" else ""
                f.set["journal"] = venue
                if e.get("booktitle"):
                    f.drop.append("booktitle")
            if ARXIVISH.search(e.get("publisher")):
                f.drop.append("publisher")
            # keep the arXiv id when it was only written in the journal field
            arxiv = re.search(r"(\d{4}\.\d{4,5})", journal) if ARXIVISH.search(journal) else None
            if arxiv and not e.get("eprint"):
                f.set["eprint"] = arxiv.group(1)
                if not e.get("archiveprefix"):
                    f.set["archiveprefix"] = "arXiv"
            py = published_year(pub)
            if py and py != year:
                f.set["year"] = str(py)
            if pub.source == "crossref" and pub.doi and not _arxiv_doi(pub.doi) and not e.get("doi"):
                f.set["doi"] = pub.doi
            what = f"published in {venue}" + (f" ({py})" if py else "")
            f.changes.append(f"preprint → {what}" + ("" if py else f"; the year ({year}) is the preprint's: check the venue's year"))
        else:
            f.changes.append(f"published in {pub.published_in}, but it is unclear whether that is a conference or a journal: left as it was")

    # Only a DOI's own Crossref record dates that version and vouches for the DOI: Semantic Scholar and OpenAlex merge
    # versions, so their year and DOI can be different versions' (ImageNet, 2012, came with the DOI of the 2017
    # Communications of the ACM reprint).
    rec = _crossref_version(v.match, title, t) if pub is None else None
    if (
        rec is not None
        and rec.source == "crossref"
        and "year" not in f.set
        and year
        and rec.year
        and year < rec.year - 1
        and any(p.startswith("year is") for p in v.problems)
    ):
        f.set["year"] = str(rec.year)
        f.changes.append(f"year {year} → {rec.year}")

    if (
        rec is not None
        and rec.source == "crossref"
        and "doi" not in f.set
        and not e.get("doi")
        and rec.doi
        and not _arxiv_doi(rec.doi)
        and v.status == "ok"
        and pub is None
        and title_similarity(title, rec.title) == 1.0
        and year is not None
        and rec.year is not None
        and abs(year - rec.year) <= 1
        and author_overlap([a for a in _family_names(e)], rec.authors)[1]
        and _same_kind(e, rec)
    ):
        f.set["doi"] = rec.doi
        f.changes.append(f"DOI {rec.doi} added")

    if f.set and not f.changes:
        f.changes.append("updated")
    return f if (f.set or f.drop or f.type) else (f if f.changes else None)


def _crossref_version(rec: Record | None, title: str, t: Transport | None) -> Record | None:
    """The matched record as its DOI's Crossref record, or None when that cannot be had."""
    if rec is None or not rec.doi or _arxiv_doi(rec.doi):
        return None
    if rec.source == "crossref":
        return rec
    if t is None:
        return None
    from .sources import crossref_doi

    try:
        found = crossref_doi(t, rec.doi)
    except TransportError:
        return None
    if not found or title_similarity(title or rec.title, found[0].title) < SAME_TITLE:
        return None
    return found[0]


def _same_kind(e: Entry, rec: Record) -> bool:
    """A conference paper and its journal version often share a title and nearly a year (Group Normalization: ECCV
    2018, IJCV 2019): a DOI is added only when the record is the same kind of publication as the entry.

    >>> conf, jour = Record("crossref", "T", kind="proceedings-article"), Record("crossref", "T", kind="journal-article")
    >>> e = Entry("inproceedings", "k", {"booktitle": "ECCV"})
    >>> _same_kind(e, conf), _same_kind(e, jour), _same_kind(Entry("article", "k", {"journal": "IJCV"}), conf)
    (True, False, False)
    """
    journal = bool(e.get("journal")) and not ARXIVISH.search(e.get("journal"))
    if e.type in ("inproceedings", "conference") or e.get("booktitle"):
        return rec.kind != "journal-article"
    if e.type == "article" and journal:
        return rec.kind not in ("proceedings-article", "book-chapter")
    return True


def _family_names(e: Entry) -> list[str]:
    from .bib import authors

    return authors(e.get("author"))


def apply(text: str, entries: list[Entry], fixes: dict[str, Fix]) -> str:
    """The text with each fix applied to its entry; everything else unchanged."""
    ops: list[tuple[int, int, str]] = []
    for e in entries:
        f = fixes.get(e.key)
        if f is None or not (f.set or f.drop or f.type):
            continue
        if f.type:
            ops.append((e.type_span[0], e.type_span[1], f.type))
        indent = "  "
        if e.spans:
            first = min(s[0] for s in e.spans.values())
            line_start = text.rfind("\n", 0, first) + 1
            if text[line_start:first].strip() == "":
                indent = text[line_start:first] or indent
        for name in f.drop:
            if name not in e.spans:
                continue
            a, _, c = e.spans[name]
            # from the comma before the field, so no comma is left dangling
            j = a
            while j > 0 and text[j - 1] in " \t\r\n":
                j -= 1
            if j > 0 and text[j - 1] == ",":
                j -= 1
            ops.append((j, c, ""))
        # the `=` column, when the entry's fields line theirs up
        width = 0
        if e.spans:
            cols = {text.index("=", a) - a for a, _, _ in e.spans.values()}
            if len(cols) == 1 and len(e.spans) > 1:
                width = cols.pop()
        new = []
        for name, value in f.set.items():
            if name in e.spans and name not in f.drop:
                _, b, c = e.spans[name]
                ops.append((b, c, "{" + _bib_value(value) + "}"))
            else:
                label = name.ljust(width) if width > len(name) else name + " "
                new.append(f"{indent}{label}= {{{_bib_value(value)}}}")
        if new:
            k = e.close
            while k > 0 and text[k - 1] in " \t\r\n":
                k -= 1
            nl = "\r\n" if "\r\n" in text else "\n"
            if text[k - 1] == ",":
                ops.append((k, k, nl + ("," + nl).join(new) + ","))
            else:
                ops.append((k, k, "," + nl + ("," + nl).join(new)))
    for a, b, s in sorted(ops, key=lambda o: (o[0], o[1]), reverse=True):
        text = text[:a] + s + text[b:]
    return text


def fixed_path(bib: Path) -> Path:
    return bib.with_name(bib.stem + ".fixed.bib")


def write_fixed(bib: Path, verdicts: list[Verdict], t: Transport | None = None) -> tuple[Path | None, list[Fix], list[Verdict]]:
    """Writes <name>.fixed.bib next to `bib` when something changed. Returns (written file or None, the fixes,
    the verdicts left for a person)."""
    text = read_source(bib)
    entries = parse_bib(text)
    by_key = {v.key: v for v in verdicts}
    fixes: dict[str, Fix] = {}
    for e in entries:
        v = by_key.get(e.key)
        if v is None:
            continue
        f = plan(e, v, t)
        if f is not None:
            fixes[e.key] = f
    left = [v for v in verdicts if v.status in ("not-found", "retracted", "mismatch") and not (fixes.get(v.key) and _fully_fixed(v, fixes[v.key]))]
    changed = {k: f for k, f in fixes.items() if f.set or f.drop or f.type}
    if not changed:
        return None, list(fixes.values()), left
    out = fixed_path(bib)
    out.write_text(apply(text, entries, changed), encoding="utf-8", newline="")
    return out, list(fixes.values()), left


def _fully_fixed(v: Verdict, f: Fix) -> bool:
    """Whether every problem of a verdict was a year the fix corrected."""
    return bool(v.problems) and all(p.startswith("year is") for p in v.problems) and "year" in f.set
