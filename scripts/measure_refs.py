"""Reference checks on real papers (online, cached): how many references come out not-found or mismatched, so each
one can be looked at by hand.

    uv run python scripts/measure_refs.py SOURCES_DIR ID [ID ...] > refs-report.txt
"""

import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from paper_proof.check import check_reference
from paper_proof.latex import find_main, read_project
from paper_proof.transport import CachedTransport, HttpTransport, default_cache_dir

root = Path(sys.argv[1])
t = CachedTransport(HttpTransport(), default_cache_dir())
total = Counter()
for aid in sys.argv[2:]:
    main = find_main(root / aid)
    proj = read_project(main)
    refs = proj.checked()
    with ThreadPoolExecutor(4) as pool:
        verdicts = list(pool.map(lambda r: check_reference(r, t), refs))
    c = Counter(v.status for v in verdicts)
    total.update(c)
    print(f"== {aid} ({proj.bibliography_from}): {len(refs)} references, {dict(c)}", flush=True)
    for v in verdicts:
        if v.status in ("not-found", "mismatch", "retracted", "unknown"):
            print(f"   {v.status:9} {v.key}: {v.title[:90]}")
            for p in v.problems:
                print(f"             - {p[:160]}")
            for n in v.notes:
                if not n.startswith("cited as an arXiv preprint"):
                    print(f"             · {n[:160]}")
print("TOTAL", dict(total))
