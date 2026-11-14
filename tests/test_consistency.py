"""The paper against itself, as a whole (acronyms, terms, spelling, symbols), on LaTeX and on a PDF's text; and the
review mode, which sends nothing."""

import json
from pathlib import Path

import pytest

from paper_proof.checks.consistency import check_consistency, long_form, reading_order
from paper_proof.cli import run
from paper_proof.pdf_text import abstract_span, pdf_numbers, prose
from paper_proof.transport import Transport


def kinds(findings):
    return [(f.kind, f.line) for f in findings]


def doc(body: str, abstract: str = "") -> str:
    return "\\title{T}\n\\begin{document}\n\\begin{abstract}" + abstract + "\\end{abstract}\n" + body + "\n\\end{document}\n"


@pytest.mark.parametrize(
    "before, acronym, expected",
    [
        ("we use Low-Rank Adaptation", "LoRA", "Low-Rank Adaptation"),
        ("trained with the cross-entropy", "CE", "cross-entropy"),
        ("Bidirectional Encoder Representations from Transformers", "BERT", "Bidirectional Encoder Representations from Transformers"),
        ("the Generative Pre-trained Transformer", "GPT", "Generative Pre-trained Transformer"),
        ("structured state space sequence models", "SSM", "state space sequence models"),  # the S of "state" first
        ("``masked language model''", "MLM", "masked language model"),  # LaTeX quotes are not part of it
        ("we report the results", "RL", None),  # the words do not spell it
    ],
)
def test_what_an_acronym_stands_for(before, acronym, expected):
    assert long_form(before, acronym) == expected


def test_acronyms():
    body = (
        "We study LLMs first.\n"  # 4: used before it is spelled out (line 5)
        "Large language models (LLMs) are big.\n"
        "Again, large language models (LLM) are big.\n"  # 6: spelled out again
        "We use reinforcement learning (RL).\n"
        "Then representation learning (RL) differs.\n"  # 8: two meanings
        "\\begin{figure}\\caption{Outputs of large language models (LLMs).}\\end{figure}\n"  # a caption: on purpose
        "Low-Rank Adaptation, or LoRA, is cheap. LoRA works.\n"
    )
    found = kinds(check_consistency({"main.tex": doc(body, "Large language models (LLMs) and Low-Rank Adaptation (LoRA).")}))
    assert ("acronym-before-definition", 4) in found
    assert ("acronym-again", 6) in found
    assert ("acronym-two-meanings", 8) in found
    assert not any(k == "acronym-again" and line == 9 for k, line in found)  # captions do not count
    assert not any("LoRA" in str(x) for x in found if x[0] == "acronym-before-definition")


def test_an_acronym_spelled_out_only_in_the_abstract():
    (f,) = check_consistency({"main.tex": doc("SMA is fast.", "We introduce sparse mixture adapters (SMA).")})
    assert f.kind == "acronym-only-in-abstract" and f.line == 4


def test_reading_order_follows_input():
    texts = {
        "main.tex": "Intro.\n\\input{sections/method}\nLater, we use the GPU memory (GM) again: GM.\n",
        "sections/method.tex": "We define graphics memory (GM) here.\n",
    }
    assert [s.file for s in reading_order(texts)] == ["main.tex", "sections/method.tex", "main.tex"]
    found = check_consistency(texts)
    # read in order, the definition in method.tex comes before the use in main.tex: no "used before"
    assert not any(f.kind == "acronym-before-definition" for f in found)
    assert any(f.kind == "acronym-two-meanings" for f in found)


def test_terms_written_two_ways():
    body = "Pre-training matters. The pre-training stage, then pretraining again. A data set and a dataset.\n" \
           "The ground truth labels; the ground-truth labels. A trade-off; we trade off speed.\n"  # fmt: skip
    found = check_consistency({"main.tex": doc(body)})
    messages = [f.message for f in found if f.kind == "term-two-ways"]
    assert any('"pretraining" (1×) here, "pre-training" (2×)' in m for m in messages)
    assert any('"data set"' in m for m in messages)
    assert not any("ground" in m or "trade" in m for m in messages)  # noun and adjective, noun and verb


def test_british_and_american_spelling():
    found = check_consistency({"main.tex": doc("We optimize, normalize and analyze. We optimise once.")})
    (f,) = [x for x in found if x.kind == "spelling-mix"]
    assert "British spelling (optimise: 1×)" in f.message
    # "analyses" (the plural of analysis) and "laboratory" are neither
    assert not check_consistency({"main.tex": doc("We normalize. Two analyses. A laboratory. We modeled it.")})


def test_a_symbol_with_two_meanings():
    body = (
        "Let $N$ be the number of layers.\nWe train it.\nLet $N$ be the batch size of each step.\n"
        "Where $d$ is the hidden size; $d$ denotes the hidden dimension.\n"
    )
    found = [f for f in check_consistency({"main.tex": doc(body)}) if f.kind == "symbol-two-meanings"]
    assert len(found) == 1 and found[0].line == 6 and "$N$" in found[0].message  # $d$ means the same twice


PDF_TEXT = (
    "A Paper\nAbstract\nWe reach 41.2 accuracy, 3.1 points over the baseline, with Large language models (LLMs).\n"
    "1 Introduction\nWe use LLMs. Pre-training helps; pretraining helps.\f"
    "Accuracy rises from 20.0 to 30.0, a 20% gain. Large language models (LLMs) again.\f"
    "References\n[1] A. Author. Pre-training of everything. 2020.\n[2] B. Author. Optimisation. 2021.\n[3] C. Author. Title. 2022.\n"
)


def test_a_pdf_text():
    text = prose(PDF_TEXT.split("\f"))
    assert "Optimisation" not in text and text.count("\f") == 2  # the reference list is blanked, pages kept
    a, b = abstract_span(text)
    assert "41.2" in text[a:b] and "Introduction" not in text[a:b]
    numbers = pdf_numbers(text, "p.pdf")
    assert sorted((f.kind, f.line) for f in numbers) == [("abstract-number", 1), ("wrong-change", 2)]
    assert not any("3.1" in f.message for f in numbers)  # "3.1 points over": a difference, not checkable in a PDF
    found = check_consistency({"p.pdf": text}, latex=False, abstract={"p.pdf": (0, b)})
    # the abstract's definition does not count: page 1 uses LLMs before page 2 spells them out
    assert ("acronym-before-definition", 1) in kinds(found) and ("term-two-ways", 1) in kinds(found)
    assert all(" p." in f.message for f in found if "first at" in f.message)  # pages, not lines


class NoNetwork(Transport):
    def get(self, url, params=None, headers=None):  # pragma: no cover - must not be reached
        raise AssertionError(f"review mode sent a request: {url}")


def test_review_mode_sends_nothing(tmp_path, capsys):
    from .test_pdf import make_pdf

    pdf = make_pdf(tmp_path / "sub.pdf", PDF_TEXT.replace("\f", "\n").split("\n"))
    code = run([str(pdf), "--review", "--color", "never"], NoNetwork())
    out = capsys.readouterr().out
    assert code == 0  # a review never "fails"
    assert "review mode: nothing from the paper was sent anywhere" in out and "not a verdict" in out
    assert "sub.pdf p.1" in out
    code = run([str(pdf), "--review", "--format", "json"], NoNetwork())
    assert json.loads(capsys.readouterr().out)["findings"] and code == 0


def test_lookup_references_needs_review(capsys, tmp_path: Path):
    assert run([str(tmp_path / "x.pdf"), "--lookup-references"]) == 2
    assert "--review" in capsys.readouterr().err
