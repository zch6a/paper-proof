"""Reference checks on real papers from the answer cache only: no request is sent, and an answer that is not
cached counts as no answer. Re-scores the verdicts after a change to the matching, for free.

    uv run python scripts/measure_refs_cached.py SOURCES_DIR ID [ID ...]
"""

import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from paper_proof.check import check_reference
from paper_proof.latex import find_main, read_project
from paper_proof.transport import CachedTransport, default_cache_dir

root = Path(sys.argv[1])


class _Down:
    def get(self, url):
        from paper_proof.transport import TransportError

        raise TransportError("not in cache")


t = CachedTransport(_Down(), default_cache_dir())
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
                    print(f"             路 {n[:160]}")
print("TOTAL", dict(total))
