"""Regressions for the bugs a code review found (each with the input that reproduced it). No network."""

import gzip
import http.client
import io
import threading
import time
from pathlib import Path

import pytest

from paper_proof import arxiv_source, latex
from paper_proof import transport as T
from paper_proof.check import Reference, check_reference
from paper_proof.cli import run
from paper_proof.numbers import change_claims, check_numbers
from paper_proof.tables import find_tables
from paper_proof.transport import ReplayTransport

from .test_check import ANSWERS


def test_duplicate_entries_checked_in_parallel_share_one_request_and_never_crash(tmp_path):
    calls = []
    lock = threading.Lock()

    class Slow:
        def get(self, url):
            with lock:
                calls.append(url)
            time.sleep(0.05)
            return T.Response(200, '{"ok": true}')

    c = T.CachedTransport(Slow(), tmp_path)
    threads = [threading.Thread(target=c.get, args=("https://api.crossref.org/works?q=same",)) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(calls) == 1


def test_a_cache_that_cannot_be_written_does_not_stop_the_check(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    c = T.CachedTransport(type("I", (), {"get": lambda self, u: T.Response(200, "{}")})(), blocker / "cache")
    assert c.get("https://a/1").status == 200  # the cache folder cannot exist under a file


def test_only_real_answers_are_cached(tmp_path):
    n = {"calls": 0}

    class BotCheck:
        def get(self, url):
            n["calls"] += 1
            return T.Response(200, "<html>Making sure you're not a bot</html>")

    c = T.CachedTransport(BotCheck(), tmp_path)
    c.get("https://dblp.org/x")
    c.get("https://dblp.org/x")
    assert n["calls"] == 2  # asked again: a bot-check page is not an answer


def test_an_interrupted_body_is_unknown_not_a_crash(monkeypatch):
    def broken(req, timeout):
        raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr(T.urllib.request, "urlopen", broken)
    monkeypatch.setattr(T.time, "sleep", lambda s: None)
    with pytest.raises(T.TransportError):
        T.HttpTransport(retries=1).get("https://api.crossref.org/works/10.1/x")


def test_a_reference_with_only_a_doi():
    v = check_reference(Reference("k", "", doi="10.1109/cvpr.2016.90"), ReplayTransport(dict(ANSWERS)))
    assert v.status == "ok" and "Deep Residual Learning" in v.title


def test_long_blank_runs_take_linear_time():
    text = "Accuracy rose from 5 " + " " * 20000 + " which is good, a 3% gain."
    start = time.perf_counter()
    change_claims(text, "a.tex", lambda pos: 1)
    check_numbers({"a.tex": "Accuracy rose from 5 \\begin{equation}" + "a+" * 3000 + "\\end{equation} which is good."})
    assert time.perf_counter() - start < 1.0


def test_a_huge_multicolumn_span_is_capped():
    start = time.perf_counter()
    (t,) = find_tables(r"\begin{tabular}{c} \multicolumn{3000000}{c}{x} \\ 1 \end{tabular}")
    assert time.perf_counter() - start < 1.0 and max(len(r) for r in t.rows) <= 64


def test_a_latin1_bib_is_read(tmp_path, capsys):
    bib = tmp_path / "refs.bib"
    bib.write_bytes("@misc{k, title={Café}, author={Müller, Hans}}".encode("latin-1"))
    assert run([str(bib), "--format", "json", "--fail-on", "never"], ReplayTransport({})) == 0
    assert "Café" in capsys.readouterr().out


def test_a_damaged_archive_is_an_error_message(tmp_path):
    half = gzip.compress(b"x" * 10000)
    with pytest.raises(ValueError, match="damaged"):
        arxiv_source.extract(half[: len(half) // 2], tmp_path / "a")


def test_a_decompression_bomb_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(arxiv_source, "MAX_UNPACKED", 1_000_000)
    with pytest.raises(ValueError, match="unpacks to more than"):
        arxiv_source.extract(gzip.compress(b"%" * 5_000_000), tmp_path / "b")


def test_network_paths_in_input_are_never_touched(tmp_path, monkeypatch):
    touched = []
    real = Path.resolve

    def spy(self, *a, **k):
        touched.append(str(self))
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "resolve", spy)
    root = tmp_path.resolve()
    for name in ("//attacker.example/share/x", r"\\attacker.example\share\x", "C:/Windows/win", "/etc/passwd", "../outside"):
        assert latex._resolve(root, root, name, ".tex") is None
    assert not any("attacker" in p or "Windows" in p or "passwd" in p or "outside" in p for p in touched)


def test_damaged_arxiv_source_on_the_command_line(capsys):
    def fetcher(aid, into):
        arxiv_source.extract(io.BytesIO(gzip.compress(b"x" * 1000)).getvalue()[:20], into)

    assert run(["2101.00001", "--offline"], ReplayTransport({}), fetcher=fetcher) == 2
    assert "damaged" in capsys.readouterr().err
