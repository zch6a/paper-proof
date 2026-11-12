"""Fetch the LaTeX sources of arXiv papers into a folder of your choice, for measuring accuracy.
The sources are the authors' work: keep them out of this repository (only their ids are here, in papers.txt).

    python scripts/fetch_arxiv_sources.py OUT_DIR $(cat scripts/papers.txt)

Only .tex/.bib/.bbl/.sty/.cls files are kept; one request every 3 seconds, as arXiv asks.
"""

import gzip
import io
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1])
IDS = sys.argv[2:]
UA = "paper-proof-dev/0.1 (+https://github.com/zch6a/paper-proof)"

for aid in IDS:
    d = OUT / aid.replace("/", "_")
    if d.exists():
        continue
    req = urllib.request.Request(f"https://arxiv.org/e-print/{aid}", headers={"User-Agent": UA})
    try:
        data = urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        print(aid, "failed", e)
        time.sleep(3)
        continue
    d.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            for m in tf.getmembers():
                name = Path(m.name)
                if (
                    m.isfile()
                    and not name.is_absolute()
                    and ".." not in name.parts
                    and name.suffix.lower() in (".tex", ".bib", ".bbl", ".sty", ".cls")
                ):
                    target = d / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tf.extractfile(m).read())
    except tarfile.ReadError:
        (d / "main.tex").write_bytes(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
    print(aid, "ok", len(list(d.rglob("*.tex"))), "tex")
    time.sleep(3)
