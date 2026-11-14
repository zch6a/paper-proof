"""Run the consistency checks on every fetched source tree; print each finding, for reading by hand.

python scripts/measure_consistency.py OUT_DIR        # OUT_DIR from fetch_arxiv_sources.py
"""

import sys
from collections import Counter
from pathlib import Path

from paper_proof.checks.consistency import check_consistency
from paper_proof.latex import find_main, read_project

root = Path(sys.argv[1])
kinds: Counter = Counter()
papers: Counter = Counter()
for d in sorted(p for p in root.iterdir() if p.is_dir()):
    main = find_main(d)
    if main is None:
        continue
    proj = read_project(main)
    fs = check_consistency(proj.texts)
    print(f"== {d.name}: {len(fs)}")
    for f in fs:
        kinds[f.kind] += 1
        papers[f.kind, d.name] += 1
        print(f"   {f.severity:7} {f.kind:26} {f.file}:{f.line}  {f.message[:220]}")
print(kinds)
print("papers with each kind:", Counter(k for k, _ in papers))
