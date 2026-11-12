"""PDF title extraction vs the paper's own LaTeX bibliography (offline comparison). PDFs are fetched into a
folder outside this repository (PAPER_PROOF_PDF_DIR, default: a temporary folder) and never committed.

    uv run python scripts/measure_pdf.py SOURCES_DIR 1706.03762 2106.09685 ...
"""

import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from paper_proof.latex import find_main, read_project
from paper_proof.match import title_in, title_similarity
from paper_proof.pdf import references_from_pdf

src = Path(sys.argv[1])
UA = "paper-proof-dev/0.1 (+https://github.com/zch6a/paper-proof)"
total = found = exact = 0
tmp = Path(os.environ.get("PAPER_PROOF_PDF_DIR") or tempfile.mkdtemp(prefix="paper-proof-pdfs-"))
tmp.mkdir(exist_ok=True)
if True:
    for aid in sys.argv[2:]:
        pdf = Path(tmp) / f"{aid}.pdf"
        if not pdf.exists():
            req = urllib.request.Request(f"https://arxiv.org/pdf/{aid}", headers={"User-Agent": UA})
            pdf.write_bytes(urllib.request.urlopen(req, timeout=60).read())
            time.sleep(4)
        tex_refs = read_project(find_main(src / aid)).checked()
        pdf_refs = references_from_pdf(pdf)
        n_ok = n_exact = 0
        misses = []
        for r in tex_refs:
            if not r.title:
                continue
            best = max(pdf_refs, key=lambda p: title_similarity(r.title, p.title), default=None)
            s = title_similarity(r.title, best.title) if best else 0
            in_raw = any(title_in(r.title, p.raw) for p in pdf_refs)
            n_exact += s >= 0.92
            n_ok += s >= 0.92 or in_raw
            if s < 0.92:
                misses.append((r.title[:70], best.title[:70] if best else "", in_raw))
        total += len([r for r in tex_refs if r.title])
        found += n_ok
        exact += n_exact
        print(f"== {aid}: tex {len(tex_refs)} refs, pdf {len(pdf_refs)} entries; title read exactly {n_exact}, findable {n_ok}")
        for m in misses[:8]:
            print(f"   tex: {m[0]}\n   pdf: {m[1]}   (in an entry: {m[2]})")
print(f"TOTAL {total}: exact title {exact}, findable (title or whole entry) {found}")
