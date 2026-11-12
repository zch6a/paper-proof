"""BibTeX as real .bib files write it."""

import pytest

from paper_proof.bib import BibError, authors, parse_bib, plain


def test_entry_forms_and_lines():
    text = """% a comment
@comment{ignored = {x}}
@preamble{"\\newcommand{\\x}{y}"}
@Article(vaswani2017,
  title     = {Attention Is All You Need},
  author    = "Vaswani, Ashish and Shazeer, Noam",
  year      = 2017,
  month     = jun,
  journal   = nips,
)

@inproceedings{he2016, title={Deep Residual Learning for {Image} Recognition}, booktitle={CVPR}, year={2016}}
"""
    entries = parse_bib(text)
    assert [(e.type, e.key, e.line) for e in entries] == [("article", "vaswani2017", 4), ("inproceedings", "he2016", 12)]
    a = entries[0]
    assert a.get("year") == "2017" and a.get("month") == "6"
    assert a.get("journal") == "nips", "an undefined macro is kept as written"
    assert plain(entries[1].get("title")) == "Deep Residual Learning for Image Recognition"


def test_nested_braces_quotes_and_escapes():
    e = parse_bib(r'@misc{k, title = "A {"}quoted{"} word and \{braces\}", note = {50\% {of} it}}')[0]
    assert "quoted" in e.get("title")
    assert e.get("note") == r"50\% {of} it"


def test_unclosed_entry_is_an_error_with_its_line():
    with pytest.raises(BibError, match="line 2"):
        parse_bib("\n@article{a, title = {never closed}")


def test_author_lists():
    assert authors("Kingma, Diederik P. and Ba, Jimmy") == ["Kingma", "Ba"]
    assert authors("D. P. Kingma and J. Ba") == ["Kingma", "Ba"]
    assert authors(r"J{\"u}rgen Schmidhuber") == ["Schmidhuber"]
    assert authors(r"Andr{\'e}s Garc{\'i}a and others") == ["García"]
    assert authors("Sandra AND Bullock") == ["Sandra", "Bullock"], "AND in any case separates"
    assert authors("{Sandra and Bullock}") == ["Sandra and Bullock"], "inside braces it is one name"
    assert authors("") == []
