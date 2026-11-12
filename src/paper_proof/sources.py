"""The bibliographic databases a reference is looked up in, each answer turned into `Record`s.

Crossref (DOIs: journals, proceedings), arXiv (preprints), Semantic Scholar and OpenAlex (almost everything, with
venue and retraction data, and which preprint became which published paper).
Each function returns [] when the database has nothing, and raises TransportError when it did not answer.

Not DBLP: since 2026 it answers scripted requests with a "making sure you're not a bot" challenge page, and getting
past such a page is not something a tool should do. Semantic Scholar and OpenAlex cover what it was used for.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

from .match import Record
from .transport import Transport, TransportError


def _q(s: str) -> str:
    return quote(s, safe="")


def _year(v) -> int | None:
    try:
        y = int(str(v)[:4])
        return y if 1500 < y < 2200 else None
    except (TypeError, ValueError):
        return None


def _json(t: Transport, url: str):
    r = t.get(url)
    if r.status == 404:
        return None
    if r.status != 200:
        raise TransportError(f"{url.split('/')[2]}: HTTP {r.status}")
    try:
        return json.loads(r.text)
    except ValueError as e:
        raise TransportError(f"{url.split('/')[2]}: not JSON") from e


# ---------------------------------------------------------------- Crossref


def _crossref_record(w: dict) -> Record:
    titles = w.get("title") or [""]
    venue = (w.get("container-title") or [""])[0] or (w.get("event") or {}).get("name", "")
    issued = (w.get("issued") or {}).get("date-parts") or [[None]]
    # Retraction status is taken from OpenAlex (`is_retracted`, from the Retraction Watch data): Crossref marks a
    # retraction on the retraction notice, not on the original work, so it is not read here.
    retracted = False
    return Record(
        source="crossref",
        title=titles[0] or "",
        authors=[a.get("family") or a.get("name", "") for a in w.get("author", []) or []],
        year=_year(issued[0][0] if issued and issued[0] else None),
        venue=venue,
        doi=(w.get("DOI") or "").lower(),
        url=w.get("URL", ""),
        retracted=retracted,
        kind=w.get("type", ""),
    )


def crossref_doi(t: Transport, doi: str) -> list[Record]:
    data = _json(t, f"https://api.crossref.org/works/{_q(doi)}")
    return [_crossref_record(data["message"])] if data and "message" in data else []


def crossref_search(t: Transport, title: str, first_author: str = "") -> list[Record]:
    q = f"query.bibliographic={_q(title)}" + (f"&query.author={_q(first_author)}" if first_author else "")
    data = _json(t, f"https://api.crossref.org/works?{q}&rows=5&select=DOI,title,author,issued,container-title,type,URL,event")
    return [_crossref_record(w) for w in ((data or {}).get("message") or {}).get("items", [])]


# ---------------------------------------------------------------- arXiv

_ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
ARXIV_ID = re.compile(r"(?<![\w.])(?:arxiv:\s*)?(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?(?![\w])", re.I)


def _arxiv_records(xml: str) -> list[Record]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise TransportError("export.arxiv.org: not XML") from e
    out = []
    for e in root.findall("a:entry", _ATOM):
        ident = (e.findtext("a:id", "", _ATOM) or "").rsplit("/abs/", 1)[-1]
        title = re.sub(r"\s+", " ", e.findtext("a:title", "", _ATOM) or "").strip()
        if not ident or title == "Error":
            continue
        authors = [re.sub(r"\s+", " ", a.findtext("a:name", "", _ATOM) or "").strip() for a in e.findall("a:author", _ATOM)]
        journal = (e.findtext("arxiv:journal_ref", "", _ATOM) or "").strip()
        out.append(
            Record(
                source="arxiv",
                title=title,
                authors=authors,
                year=_year(e.findtext("a:published", "", _ATOM)),
                venue="arXiv",
                doi=(e.findtext("arxiv:doi", "", _ATOM) or "").lower(),
                arxiv=re.sub(r"v\d+$", "", ident),
                url=f"https://arxiv.org/abs/{re.sub(r'v[0-9]+$', '', ident)}",
                kind="preprint",
                published_in=journal,
            )
        )
    return out


def _arxiv(t: Transport, url: str) -> list[Record]:
    r = t.get(url)
    if r.status != 200:
        raise TransportError(f"export.arxiv.org: HTTP {r.status}")
    return _arxiv_records(r.text)


def arxiv_id(t: Transport, ident: str) -> list[Record]:
    return _arxiv(t, f"https://export.arxiv.org/api/query?id_list={_q(ident)}&max_results=1")


def arxiv_search(t: Transport, title: str) -> list[Record]:
    words = re.sub(r"[^\w\s-]", " ", title).split()
    if not words:
        return []
    phrase = 'ti:"' + " ".join(words) + '"'
    return _arxiv(t, f"https://export.arxiv.org/api/query?search_query={_q(phrase)}&max_results=5")


# ---------------------------------------------------------------- Semantic Scholar

_S2_FIELDS = "title,authors,year,venue,externalIds,publicationVenue,publicationTypes,journal"


def _s2_record(p: dict) -> Record:
    ids = p.get("externalIds") or {}
    venue = p.get("venue") or ((p.get("publicationVenue") or {}).get("name", "")) or ((p.get("journal") or {}).get("name", ""))
    return Record(
        source="semanticscholar",
        title=p.get("title") or "",
        authors=[a.get("name", "") for a in p.get("authors", []) or []],
        year=p.get("year"),
        venue=venue,
        doi=(ids.get("DOI") or "").lower(),
        arxiv=ids.get("ArXiv") or "",
        url=f"https://www.semanticscholar.org/paper/{p['paperId']}" if p.get("paperId") else "",
        kind=",".join(p.get("publicationTypes") or []),
        published_in=venue if venue and venue.lower() not in ("arxiv", "arxiv.org") else "",
    )


def s2_match(t: Transport, title: str) -> list[Record]:
    data = _json(t, f"https://api.semanticscholar.org/graph/v1/paper/search/match?query={_q(title)}&fields={_S2_FIELDS}")
    return [_s2_record(p) for p in (data or {}).get("data", [])]


# ---------------------------------------------------------------- OpenAlex


def _openalex_record(w: dict) -> Record:
    loc = w.get("primary_location") or {}
    source = loc.get("source") or {}
    ids = w.get("ids") or {}
    doi = (w.get("doi") or "").lower().removeprefix("https://doi.org/")
    # A preprint's record may also list the published version among its locations.
    published = ""
    for other in w.get("locations") or []:
        s = (other or {}).get("source") or {}
        if s.get("type") in ("conference", "journal") and s.get("display_name"):
            published = s["display_name"]
            break
    return Record(
        source="openalex",
        title=w.get("title") or w.get("display_name") or "",
        authors=[(a.get("author") or {}).get("display_name", "") for a in w.get("authorships", []) or []],
        year=w.get("publication_year"),
        venue=source.get("display_name") or "",
        doi=doi,
        # arXiv's DOIs (10.48550/arXiv.<id>) carry the arXiv id.
        arxiv=doi[len("10.48550/arxiv.") :] if doi.startswith("10.48550/arxiv.") else "",
        url=ids.get("openalex", ""),
        retracted=bool(w.get("is_retracted")),
        kind=w.get("type") or "",
        published_in=published,
    )


def openalex_search(t: Transport, title: str) -> list[Record]:
    # The title filter, not full-text search: a match has to be in the title.
    clean = re.sub(r"[,|:]", " ", title)
    data = _json(t, f"https://api.openalex.org/works?filter=title.search:{_q(clean)}&per-page=5")
    return [_openalex_record(w) for w in (data or {}).get("results", [])]


def openalex_doi(t: Transport, doi: str) -> list[Record]:
    data = _json(t, f"https://api.openalex.org/works/doi:{_q(doi)}")
    return [_openalex_record(data)] if data else []
