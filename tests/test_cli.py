"""The command line, offline: recorded answers stand in for the databases."""

import json
import re
from pathlib import Path

from paper_proof import report
from paper_proof.cli import run
from paper_proof.transport import ReplayTransport

from .test_check import ANSWERS, FIX

BIB = str(FIX / "references.bib")


def replay():
    return ReplayTransport(dict(ANSWERS))


def test_text_report_and_exit_code(capsys):
    assert run([BIB], replay()) == 1  # the invented reference is not found
    out = capsys.readouterr().out
    assert "NOT FOUND" in out and "invented2023" in out
    assert "year is 2015, not 2012" in out
    assert "DUPLICATE" in out
    assert "Summary:" in out


def test_fail_on_levels(capsys):
    assert run([BIB, "--fail-on", "never"], replay()) == 0
    assert run([BIB, "--only", "vaswani2017", "--fail-on", "mismatch"], replay()) == 0
    assert run([BIB, "--only", "he2016_wrong_year", "--fail-on", "mismatch"], replay()) == 1
    assert run([BIB, "--only", "he2016_wrong_year"], replay()) == 0


def test_json_report(capsys):
    run([BIB, "--format", "json"], replay())
    data = json.loads(capsys.readouterr().out)
    assert data["tool"] == "paper-proof"
    assert data["summary"]["not-found"] == 1
    keys = {r["key"]: r for r in data["references"]}
    assert keys["he2016_wrong_year"]["status"] == "mismatch"
    assert data["duplicates"][0]["why"] == "same title"


def test_markdown_report_renders_nothing_from_the_bibliography(capsys, tmp_path: Path):
    bib = tmp_path / "x.bib"
    bib.write_text("@misc{evil, title={[click](https://evil.example) <img src=x> @someone}}", encoding="utf-8")
    run([str(bib), "--format", "md"], ReplayTransport({}))
    out = capsys.readouterr().out
    assert re.search(r"(?<!\\)\]\(", out) is None  # no link
    assert "<" not in out  # no HTML
    assert "@someone" not in out  # no mention


def test_bad_input_exits_2(capsys, tmp_path: Path):
    assert run([str(tmp_path / "missing.bib")], replay()) == 2
    bad = tmp_path / "bad.bib"
    bad.write_text("@article{a, title={unclosed", encoding="utf-8")
    assert run([str(bad)], replay()) == 2
    assert "line 1" in capsys.readouterr().err


def test_colour_choice(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert not report.use_color()
    assert report.use_color(choice="always")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert report.use_color() and not report.use_color(choice="never")
    run([BIB, "--only", "invented2023", "--color", "always"], replay())
    assert "\x1b[31;1m" in capsys.readouterr().out


def test_terminal_output_cannot_carry_escape_sequences():
    assert "\x1b" not in report.visible("title \x1b]0;pwned\x07 end")
