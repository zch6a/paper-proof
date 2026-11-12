"""Reference checks, against the databases' real answers recorded in fixtures/answers.json (no network)."""

import json
from pathlib import Path

import pytest

from paper_proof.bib import parse_bib
from paper_proof.check import Reference, check_reference, duplicates, reference_from_bib
from paper_proof.transport import ReplayTransport

FIX = Path(__file__).parent / "fixtures"
ANSWERS = {url: (status, text) for url, (status, text) in json.loads((FIX / "answers.json").read_text(encoding="utf-8")).items()}
REFS = {e.key: reference_from_bib(e) for e in parse_bib((FIX / "references.bib").read_text(encoding="utf-8"))}


def verdict(key: str, answers=None):
    return check_reference(REFS[key], ReplayTransport(dict(ANSWERS if answers is None else answers)))


def test_a_correct_reference_is_ok():
    v = verdict("vaswani2017")
    assert v.status == "ok", v.problems
    assert v.match and v.match.year == 2017


def test_an_invented_reference_is_not_found():
    v = verdict("invented2023")
    assert v.status == "not-found"
    assert any("does not exist" in p for p in v.problems)
    assert any("no work with this title" in p for p in v.problems)


def test_wrong_year_wrong_first_author_wrong_doi():
    assert verdict("he2016_wrong_year").problems == ["year is 2015, not 2012"]
    v = verdict("wrong_first_author")
    assert v.status == "mismatch" and any(p.startswith("first author is") and "He, not Simonyan" in p for p in v.problems)
    v = verdict("kingma2014_wrong_doi")
    assert v.status == "mismatch" and any("is a different work" in p for p in v.problems)


def test_a_preprint_that_was_published_says_where():
    v = verdict("devlin2018_preprint")
    assert v.status == "ok"
    assert any("published in" in n and "North American Chapter" in n for n in v.notes)


def test_a_web_page_is_skipped_not_reported():
    assert verdict("pytorch_website").status == "skipped"


def test_a_database_that_does_not_answer_makes_the_result_unknown_not_missing():
    # Every recorded answer replaced by "no answer": nothing can be called missing.
    down = {url: (-1, "") for url in ANSWERS}
    v = verdict("invented2023", down)
    assert v.status == "unknown"
    assert not any("no work with this title" in p for p in v.problems)


def test_reference_from_bib_reads_arxiv_ids_and_dois():
    e = parse_bib(r"""@article{a, title={X}, journal={arXiv preprint arXiv:2101.00001v2}, year={2021}}
@misc{b, title={Y}, eprint={2102.00002}, archivePrefix={arXiv}}
@article{c, title={Z}, doi={https://doi.org/10.1000/ABC.1}, journal={Nature}}""")
    a, b, c = (reference_from_bib(x) for x in e)
    assert (a.arxiv, a.cited_as_preprint) == ("2101.00001", True)
    assert (b.arxiv, b.cited_as_preprint) == ("2102.00002", True)
    assert (c.doi, c.cited_as_preprint) == ("10.1000/abc.1", False)


def test_duplicates():
    refs = [
        Reference("a", "Deep Residual Learning for Image Recognition"),
        Reference("b", "Deep residual learning for image recognition."),
        Reference("c", "Other", doi="10.1/x"),
        Reference("d", "Other 2", doi="10.1/x"),
    ]
    assert duplicates(refs) == [("a", "b", "same title"), ("c", "d", "same DOI")]


def test_one_database_down_still_finds_an_invented_reference():
    # Semantic Scholar answering 429 is common without an API key; OpenAlex, Crossref and arXiv suffice.
    answers = {url: ((-1, "") if "semanticscholar" in url else a) for url, a in ANSWERS.items()}
    v = verdict("invented2023", answers)
    assert v.status == "not-found"
    (msg,) = [p for p in v.problems if p.startswith("no work with this title in")]
    assert "Semantic Scholar" not in msg and "Crossref" in msg and "arXiv" in msg  # only the databases that answered
    assert any(n.startswith("did not answer") for n in v.notes)


def test_identifiers_outside_crossref():
    # arXiv's DOI is an arXiv id; a Zenodo DOI exists although Crossref does not know it
    assert verdict("brown2020_arxiv_doi").status == "ok"
    v = verdict("eval_harness_zenodo")
    assert v.status == "ok" and any("registered outside Crossref" in n for n in v.notes)


def test_a_later_year_is_a_note_not_an_error():
    v = verdict("adam_later_version")
    assert v.status == "ok" and any("cited as 2017" in n for n in v.notes)


def test_a_record_with_fewer_authors_is_not_evidence_against_the_citation():
    from paper_proof.match import Record, compare

    rec = Record(source="x", title="Gradient flow in recurrent nets", authors=["Hochreiter", "Bengio"], year=2001)
    assert compare("Gradient flow in recurrent nets", ["Hochreiter", "Bengio", "Frasconi", "Schmidhuber"], 2001, rec).problems == []
    full = Record(source="x", title="Gradient flow in recurrent nets", authors=["Hochreiter", "Bengio", "Frasconi", "Kolen"], year=2001)
    assert compare("Gradient flow in recurrent nets", ["Hochreiter", "Bengio", "Frasconi", "Schmidhuber"], 2001, full).problems == [
        "author not on the paper: Schmidhuber"
    ]


@pytest.mark.parametrize("key", sorted(REFS))
def test_every_request_was_recorded(key):
    # A request the recording does not have would fail loudly: the tests can never reach the network.
    verdict(key)
