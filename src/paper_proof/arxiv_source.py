"""An arXiv paper by its id: its LaTeX source fetched into a temporary folder (deleted afterwards), so any paper on
arXiv can be checked without downloading it by hand. Only .tex, .bib, .bbl, .sty and .cls files are kept, and only
inside the folder (no absolute paths, no `..`, no links).
"""

from __future__ import annotations

import gzip
import io
import re
import tarfile
import zlib
from pathlib import Path

from .transport import USER_AGENT, TransportError

ID = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)$", re.I)
KEEP = (".tex", ".bib", ".bbl", ".sty", ".cls", ".bst")
MAX_BYTES = 200 * 1024 * 1024  # arXiv's own limit on a source is 50 MB compressed


def is_arxiv_id(s: str) -> bool:
    """New-style and old-style ids, with or without a version and the arXiv: prefix.

    >>> is_arxiv_id("2106.09685"), is_arxiv_id("arXiv:2106.09685v2"), is_arxiv_id("hep-th/9901001"), is_arxiv_id("paper/")
    (True, True, True, False)
    """
    return bool(ID.match(s.strip()))


def fetch(arxiv_id: str, into: Path, timeout: float = 60.0) -> Path:
    """Download the source of `arxiv_id` into the folder `into`; returns it. A paper submitted as a PDF only has no
    LaTeX source: that is an error."""
    import urllib.error
    import urllib.request

    m = ID.match(arxiv_id.strip())
    if not m:
        raise ValueError(f"not an arXiv id: {arxiv_id!r}")
    aid = m.group(1)
    req = urllib.request.Request(f"https://arxiv.org/e-print/{aid}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_BYTES + 1)
            kind = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise TransportError(f"arxiv.org: HTTP {e.code} for {aid}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise TransportError(f"arxiv.org: {getattr(e, 'reason', e)}") from e
    if len(data) > MAX_BYTES:
        raise TransportError(f"arxiv.org: the source of {aid} is larger than {MAX_BYTES // 2**20} MB")
    if "pdf" in kind or data[:5] == b"%PDF-":
        raise ValueError(f"{aid} was submitted as a PDF only: there is no LaTeX source to check")
    extract(data, into)
    return into


MAX_UNPACKED = 500 * 1024 * 1024  # all source files together, once decompressed: a bomb stops here


def _copy(src, target: Path, budget: list[int]) -> None:
    with open(target, "wb") as out:
        while chunk := src.read(1 << 20):
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise ValueError(f"the source unpacks to more than {MAX_UNPACKED // 2**20} MB: not extracted")
            out.write(chunk)


def extract(data: bytes, into: Path) -> list[Path]:
    """The source files of an arXiv e-print (a gzipped tar, or a single gzipped .tex) written under `into`. A
    truncated or corrupt archive, or one that unpacks to more than MAX_UNPACKED, is a ValueError."""
    into.mkdir(parents=True, exist_ok=True)
    root = into.resolve()
    written: list[Path] = []
    budget = [MAX_UNPACKED]
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            for m in tf:
                name = Path(m.name)
                if not m.isfile() or name.is_absolute() or name.anchor or ".." in name.parts or name.suffix.lower() not in KEEP:
                    continue
                target = (into / name).resolve()
                if root not in target.parents:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                f = tf.extractfile(m)
                if f is not None:
                    _copy(f, target, budget)
                    written.append(target)
        return written
    except tarfile.ReadError:
        pass  # not a tar: a single (gzipped) file
    except (tarfile.TarError, EOFError, OSError, zlib.error) as e:
        raise ValueError(f"the source archive is damaged ({e.__class__.__name__}): not extracted") from e
    target = into / "main.tex"
    try:
        src = gzip.GzipFile(fileobj=io.BytesIO(data)) if data[:2] == b"\x1f\x8b" else io.BytesIO(data)
        _copy(src, target, budget)
    except (EOFError, OSError, zlib.error) as e:
        raise ValueError(f"the source archive is damaged ({e.__class__.__name__}): not extracted") from e
    return [target]
