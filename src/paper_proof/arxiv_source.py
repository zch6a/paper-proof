"""An arXiv paper by its id: its LaTeX source fetched into a temporary folder (deleted afterwards), so any paper on
arXiv can be checked without downloading it by hand. Only .tex, .bib, .bbl, .sty and .cls files are kept, and only
inside the folder (no absolute paths, no `..`, no links).
"""

from __future__ import annotations

import gzip
import io
import re
import tarfile
from pathlib import Path

from .transport import USER_AGENT, TransportError

ID = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)$", re.I)
KEEP = (".tex", ".bib", ".bbl", ".sty", ".cls", ".bst")
MAX_BYTES = 200 * 1024 * 1024  # arXiv's own limit on a source is 50 MB compressed


def is_arxiv_id(s: str) -> bool:
    """>>> is_arxiv_id("2106.09685"), is_arxiv_id("arXiv:2106.09685v2"), is_arxiv_id("hep-th/9901001"), is_arxiv_id("paper/")
    (True, True, True, False)
    """
    return bool(ID.match(s.strip()))


def fetch(arxiv_id: str, into: Path, timeout: float = 60.0) -> Path:
    """Download the source of `arxiv_id` into the folder `into`; returns it. A paper submitted as a PDF only has no
    LaTeX source: that is an error."""
    import urllib.error
    import urllib.request

    aid = ID.match(arxiv_id.strip()).group(1)
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


def extract(data: bytes, into: Path) -> list[Path]:
    """The source files of an arXiv e-print (a gzipped tar, or a single gzipped .tex) written under `into`."""
    into.mkdir(parents=True, exist_ok=True)
    root = into.resolve()
    written = []
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            for m in tf.getmembers():
                name = Path(m.name)
                if not m.isfile() or name.is_absolute() or ".." in name.parts or name.suffix.lower() not in KEEP:
                    continue
                target = (into / name).resolve()
                if root not in target.parents:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                f = tf.extractfile(m)
                if f is not None:
                    target.write_bytes(f.read())
                    written.append(target)
    except tarfile.ReadError:
        text = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
        target = into / "main.tex"
        target.write_bytes(text)
        written.append(target)
    return written
