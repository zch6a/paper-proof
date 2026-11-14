"""--fix: a corrected copy of the .bib, against the databases' recorded answers (no network)."""

import json
import shutil
from pathlib import Path

from paper_proof.bib import parse_bib
from paper_proof.check import Verdict
from paper_proof.cli import run
from paper_proof.fix import Fix, apply, plan, venue_kind
from paper_proof.match import Record
from paper_proof.transport import ReplayTransport

FIX = Path(__file__).parent / "fixtures"
ANSWERS = {url: (status, text) for url, (status, text) in json.loads((FIX / "answers.json").read_text(encoding="utf-8")).items()}


def fixed(tmp_path, capsys, *extra):
    bib = tmp_path / "references.bib"
    shutil.copy(FIX / "references.bib", bib)
    code = run([str(bib), "--fix", "--color", "never", *extra], transport=ReplayTransport(dict(ANSWERS)))
    out = tmp_path / "references.fixed.bib"
    return code, bib, out, capsys.readouterr()


def entries(path):
    return {e.key: e for e in parse_bib(path.read_text(encoding="utf-8"))}


def test_a_published_preprint_becomes_the_published_version(tmp_path, capsys):
    _, bib, out, _ = fixed(tmp_path, capsys)
    bert = entries(out)["devlin2018_preprint"]
    assert bert.type == "inproceedings"
    assert "North American Chapter of the Association for Computational Linguistics" in bert.get("booktitle")
    # dated by its DOI's Crossref record, not by the preprint
    assert (bert.get("year"), bert.get("doi")) == ("2019", "10.18653/v1/n19-1423")
    assert (bert.get("eprint"), bert.get("archiveprefix")) == ("1810.04805", "arXiv")  # the arXiv id is kept
    assert not bert.get("journal")


def test_a_year_no_database_can_vouch_for_is_left_and_said(tmp_path, capsys):
    _, _, out, cap = fixed(tmp_path, capsys)
    adam = entries(out)["adam_later_version"]
    assert adam.type == "inproceedings" and adam.get("booktitle") == "International Conference on Learning Representations"
    assert adam.get("year") == "2017"  # Semantic Scholar says 2014 and ICLR has no DOI: not guessed
    assert "the year (2017) is the preprint's: check the venue's year" in cap.out


def test_the_original_is_untouched_and_other_entries_unchanged(tmp_path, capsys):
    _, bib, out, cap = fixed(tmp_path, capsys)
    assert bib.read_bytes() == (FIX / "references.bib").read_bytes()
    before, after = entries(bib), entries(out)
    assert before.keys() == after.keys()
    for key in ("vaswani2017", "invented2023", "wrong_first_author", "kingma2014_wrong_doi", "pytorch_website"):
        assert before[key].fields == after[key].fields and before[key].type == after[key].type
    assert "wrote references.fixed.bib" in cap.out
    assert "left for you (3): invented2023 (not-found), kingma2014_wrong_doi (mismatch), wrong_first_author (mismatch)" in cap.out


def test_a_year_is_corrected_from_the_dois_own_crossref_record(tmp_path, capsys):
    # The title search matched Semantic Scholar's record (2015, the arXiv year); the DOI's Crossref record says
    # CVPR 2016, and that is the year written.
    _, _, out, cap = fixed(tmp_path, capsys)
    assert entries(out)["he2016_wrong_year"].get("year") == "2016"
    assert "he2016_wrong_year (line 18): year 2012 → 2016" in cap.out


def test_the_json_report_stays_json(tmp_path, capsys):
    _, _, out, cap = fixed(tmp_path, capsys, "--format", "json")
    json.loads(cap.out)
    assert "wrote references.fixed.bib" in cap.err and out.exists()


def test_fix_needs_a_bib_and_the_reference_check(tmp_path, capsys):
    bib = tmp_path / "r.bib"
    bib.write_text("@article{a, title={X}}", encoding="utf-8")
    assert run([str(bib), "--fix", "--offline"], transport=ReplayTransport({})) == 2
    assert run([str(bib), "--fix", "--review"], transport=ReplayTransport({})) == 2
    bbl = tmp_path / "p.bbl"
    bbl.write_text("\\begin{thebibliography}{1}\\bibitem{a} A. B. Title. 2020.\\end{thebibliography}", encoding="utf-8")
    assert run([str(bbl), "--fix"], transport=ReplayTransport({})) == 2
    assert "--fix" in capsys.readouterr().err


def test_a_latex_project_gets_its_bib_fixed(tmp_path, capsys):
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\\cite{devlin2018_preprint}\\bibliography{refs/references}\\end{document}",
        encoding="utf-8",
    )
    (tmp_path / "refs").mkdir()
    shutil.copy(FIX / "references.bib", tmp_path / "refs" / "references.bib")
    run([str(tmp_path), "--fix", "--color", "never"], transport=ReplayTransport(dict(ANSWERS)))
    out = capsys.readouterr().out
    assert "wrote references.fixed.bib next to refs/references.bib: 1 entry changed" in out
    assert entries(tmp_path / "refs" / "references.fixed.bib")["devlin2018_preprint"].type == "inproceedings"


# ---------------------------------------------------------------- rewriting the text


def rewrite(text, key, **kw):
    es = parse_bib(text)
    return apply(text, es, {key: Fix(key=key, line=1, **kw)})


def test_dropping_the_last_or_first_field_leaves_no_dangling_comma():
    t = "@article{k,\n  title = {T},\n  journal = {arXiv preprint}\n}\n"
    assert rewrite(t, "k", drop=["journal"]) == "@article{k,\n  title = {T}\n}\n"
    t = "@article{k,\n  journal = {arXiv},\n  title = {T},\n}\n"
    assert rewrite(t, "k", drop=["journal"]) == "@article{k,\n  title = {T},\n}\n"


def test_new_fields_follow_the_entry_layout():
    t = "@article{k,\n    title   = {T},\n    year    = {2018},\n}\n"
    out = rewrite(t, "k", type="inproceedings", set={"year": "2019", "booktitle": "ICLR & Co"})
    assert out == "@inproceedings{k,\n    title   = {T},\n    year    = {2019},\n    booktitle = {ICLR \\& Co},\n}\n"
    t = '@misc(k, title="T")\r\n'
    assert rewrite(t, "k", set={"doi": "10.1/x"}) == '@misc(k, title="T",\r\n  doi = {10.1/x})\r\n'


def test_only_the_named_entry_changes():
    t = '@string{x = "X"}\n% comment\n@article{a, title={A}, year=2018}\n\n@article{b, title={B}, year=2018}\n'
    out = rewrite(t, "b", set={"year": "2020"})
    assert out == '@string{x = "X"}\n% comment\n@article{a, title={A}, year=2018}\n\n@article{b, title={B}, year={2020}}\n'


def test_what_is_not_changed():
    e = parse_bib("@article{k, title={T}, author={A, B}, year={2018}, journal={arXiv preprint arXiv:2101.00001}}")[0]
    assert plan(e, Verdict("k", "not-found", "T")) is None
    assert plan(e, Verdict("k", "retracted", "T")) is None
    # a venue that may be either is reported, not guessed
    unclear = Record("semanticscholar", "T", published_in="Some Venue")
    f = plan(e, Verdict("k", "ok", "T", published=unclear))
    assert f is not None and not (f.set or f.drop or f.type) and "unclear" in f.changes[0]
    # a year from Semantic Scholar is not trusted for a correction
    v = Verdict("k", "mismatch", "T", problems=["year is 2021, not 2018"], match=Record("semanticscholar", "T", ["A"], 2021))
    assert plan(e, v) is None
    v.match = Record("crossref", "T", ["A"], 2021, doi="10.1/x")
    assert plan(e, v).set == {"year": "2021"}


def test_venue_kinds():
    assert venue_kind("Proceedings of the 2019 Conference of the North American Chapter of the ACL") == "conference"
    assert venue_kind("Findings of the Association for Computational Linguistics: EMNLP 2020") == "conference"
    assert venue_kind("Journal of Machine Learning Research") == "journal"
    assert venue_kind("IEEE Transactions on Pattern Analysis and Machine Intelligence") == "journal"
    assert venue_kind("Nature") == "journal" and venue_kind("Unknown Place") == ""
