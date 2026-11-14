"""Is this record the work the reference cites? Titles, authors and years compared the forgiving way a person would:
case, accents, punctuation and a missing subtitle do not matter; a different title or first author does.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class Record:
    """A work as a bibliographic database describes it."""

    source: str
    title: str
    authors: list[str] = field(default_factory=list)  # family names, in order
    year: int | None = None
    venue: str = ""
    doi: str = ""
    arxiv: str = ""
    url: str = ""
    retracted: bool = False
    kind: str = ""  # e.g. journal-article, proceedings-article, preprint
    # Where the work was published when the record is a preprint (DBLP and OpenAlex know both versions).
    published_in: str = ""
    published_kind: str = ""  # "conference" or "journal", when the database says which


def norm_text(s: str) -> str:
    """Lower case, no accents, no punctuation, single spaces.

    >>> norm_text("Attention Is All You Need!")
    'attention is all you need'
    >>> norm_text("Gödel–Escher: Bach")
    'godel escher bach'
    >>> norm_text("Pre-training") == norm_text("Pretraining")  # hyphenation varies, and PDFs break words with it
    True
    """
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"(?<=[^\W\d_])[-‐](?=[^\W\d_])", "", s)
    s = re.sub(r"[^\w\s]|_", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def title_similarity(a: str, b: str) -> float:
    """1.0 for the same title, also when one side lacks the subtitle or has a trailing period; lower otherwise.

    >>> title_similarity("Deep Residual Learning for Image Recognition", "Deep residual learning for image recognition.")
    1.0
    >>> title_similarity("BERT", "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding")
    1.0
    >>> title_similarity("Attention is all you need", "Attention is not all you need") < 0.92
    True
    """
    x, y = norm_text(a), norm_text(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    # A subtitle left out: the title before the colon (or dash) is the whole of the other one.
    for full, short in ((a, b), (b, a)):
        head = norm_text(re.split(r"\s*[:–—]\s+|\s+-\s+", full, maxsplit=1)[0])
        if head and head == norm_text(short) and len(head) >= 4:
            return 1.0
    # Characters alone are too forgiving: "Attention is not all you need" is 93% the same string as "Attention is
    # all you need" and a different paper. Words decide: an added or missing word counts in full, a misspelt word
    # (80% the same letters) counts as the word.
    xs, ys = x.split(), y.split()
    ys = [next((w for w in xs if SequenceMatcher(None, w, v).ratio() >= 0.8), v) for v in ys]
    return min(SequenceMatcher(None, x, y).ratio(), SequenceMatcher(None, xs, ys).ratio())


SAME_TITLE = 0.92


def title_in(title: str, text: str, share: float = 0.9) -> bool:
    """Whether a title appears, in order and nearly whole, inside a longer printed reference.

    >>> title_in("Attention is All you Need", "A. Vaswani et al. Attention is all you need. In NeurIPS, 2017.")
    True
    >>> title_in("Attention is not all you need", "A. Vaswani et al. Attention is all you need. In NeurIPS, 2017.")
    False
    """
    t, s = norm_text(title).split(), norm_text(text).split()
    if len(t) < 2:
        return False
    sm = SequenceMatcher(None, t, s, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks:
        return False
    matched = sum(b.size for b in blocks)
    # the matched words must sit together in the reference, not be scattered over it
    span = blocks[-1].b + blocks[-1].size - blocks[0].b
    return matched / len(t) >= share and span <= len(t) + 3


# Letters NFKD does not take apart: Søraker, Łukasz, Straße, Æsir.
_LATIN = str.maketrans(
    {"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "đ": "d", "Đ": "D", "ı": "i", "þ": "th"}
)
# A record whose "author" is a group, not a person.
ORGANIZATION = re.compile(
    r"\b(?:workshop|team|consortium|collaboration|group|project|initiative|inc|ltd|lab|laboratory|foundation|committee|community)\b", re.I
)


def _name_words(name: str) -> list[str]:
    return norm_text(name.translate(_LATIN)).split()


def family(name: str) -> str:
    """A family name compared by its last word, without accents or case ('van Beethoven' ~ 'Beethoven').

    >>> family("de la Fontaine") == family("Fontaine"), family("Søraker") == family("Soraker")
    (True, True)
    """
    words = _name_words(name)
    return words[-1] if words else ""


def same_person(cited: str, recorded: str) -> bool:
    """Whether a cited family name belongs to a recorded full name, allowing for compound and particle names and
    for a family name written first or last ('Ben-Zaken' / 'Elad Ben Zaken', 'El-Showk' / 'Sheer El Showk',
    'Ali' / 'Mostofa Ali Patwary'), but not for a different name ('Ham' / 'Jihun Hamm').

    >>> same_person("Zaken", "Elad Ben-Zaken"), same_person("El-Showk", "Sheer El Showk"), same_person("Ali", "Mostofa Ali Patwary")
    (True, True, True)
    >>> same_person("Ham", "Jihun Hamm"), same_person("Smith", "John Smithson")
    (False, False)
    """
    c, r = _name_words(cited), _name_words(recorded)
    if not c or not r:
        return False
    fam = c[-1]
    joined = "".join(r)
    if fam in r or "".join(c) in r:
        return True
    # compounds: the cited name is the end (Ben-Zaken -> benzaken) or several recorded words run together
    return len(fam) >= 4 and (joined.endswith(fam) or "".join(c) == "".join(r[-len(c) :]) or "".join(c) in joined and len("".join(c)) >= 6)


def author_overlap(cited: list[str], found: list[str]) -> tuple[float, bool]:
    """(share of cited family names that the record has, whether the first authors agree).

    >>> author_overlap(["Vaswani", "Shazeer"], ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"])
    (1.0, True)
    >>> author_overlap(["Smith"], ["Vaswani", "Smith"])
    (1.0, False)
    """
    if not cited or not found:
        return 0.0, False
    share = sum(1 for n in cited if any(same_person(n, f) for f in found)) / len(cited)
    return share, same_person(cited[0], found[0])


@dataclass
class Comparison:
    title: float
    authors: float
    first_author: bool
    year_delta: int | None
    problems: list[str]
    notes: list[str] = field(default_factory=list)


def compare(title: str, cited_authors: list[str], year: int | None, rec: Record) -> Comparison:
    """What differs between a reference and a record that is (by title) the same work."""
    t = title_similarity(title, rec.title)
    share, first = author_overlap(cited_authors, rec.authors)
    delta = None if year is None or rec.year is None else year - rec.year
    problems: list[str] = []
    notes: list[str] = []
    if cited_authors and rec.authors:
        if not first and not ORGANIZATION.search(rec.authors[0]) and not ORGANIZATION.search(cited_authors[0]):
            problems.append(f"first author is {rec.authors[0]}, not {cited_authors[0]}")
        missing = [n for n in cited_authors if not any(same_person(n, x) for x in rec.authors)]
        # A record with fewer authors than the citation is often just incomplete (book chapters, old papers), and in
        # a long list one name is usually a spelling variant: report only what is clearly wrong.
        clearly = len(missing) / len(cited_authors) >= 0.2 if len(cited_authors) > 5 else bool(missing)
        if missing and clearly and len(rec.authors) >= len(cited_authors):
            problems.append(f"{'author' if len(missing) == 1 else 'authors'} not on the paper: {', '.join(missing[:4])}")
        elif missing and len(rec.authors) >= len(cited_authors):
            notes.append(f"not found in the record's author list (a spelling variant?): {', '.join(missing[:4])}")
    # One year off is common and fine (an arXiv version, a conference held the year after submission). A later year
    # than the record's is usually a later version, a journal version or a reprint: worth a note, not an error.
    if delta is not None and delta < -1:
        problems.append(f"year is {rec.year}, not {year}")
    elif delta is not None and delta > 1:
        notes.append(f"{rec.source} dates it {rec.year}; cited as {year} (a later version or reprint?)")
    return Comparison(title=t, authors=share, first_author=first, year_delta=delta, problems=problems, notes=notes)
