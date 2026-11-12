"""An arXiv id as input: the source archive is unpacked safely and checked (the download itself is stubbed)."""

import gzip
import io
import tarfile

from paper_proof.arxiv_source import extract
from paper_proof.cli import run
from paper_proof.transport import ReplayTransport


def tar(files: dict[str, bytes], extra=None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for info in extra or []:
            tf.addfile(info)
    return buf.getvalue()


def test_only_source_files_inside_the_folder_are_written(tmp_path):
    link = tarfile.TarInfo("evil.tex")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    data = tar({"main.tex": b"x", "sec/a.tex": b"y", "../escape.tex": b"z", "/abs.tex": b"z", "fig.png": b"p", "run.sh": b"s"}, [link])
    out = tmp_path / "src"
    written = extract(data, out)
    assert sorted(p.relative_to(out.resolve()).as_posix() for p in written) == ["main.tex", "sec/a.tex"]
    assert not (tmp_path / "escape.tex").exists()


def test_a_single_gzipped_tex(tmp_path):
    (p,) = extract(gzip.compress(b"\\documentclass{article}"), tmp_path)
    assert p.name == "main.tex" and p.read_bytes().startswith(b"\\documentclass")


def test_an_arxiv_id_is_fetched_checked_and_deleted(capsys):
    paper = rb"""\documentclass{article}\begin{document}
See Table~\ref{tab:missing}.
\end{document}"""
    seen = {}

    def fetcher(aid, into):
        seen["dir"] = into
        extract(tar({"paper.tex": paper}), into)

    code = run(["2101.00001", "--offline"], ReplayTransport({}), fetcher=fetcher)
    out = capsys.readouterr().out
    assert "arXiv:2101.00001" in out and "tab:missing" in out
    assert code == 1
    assert not seen["dir"].exists()  # the temporary folder is gone
