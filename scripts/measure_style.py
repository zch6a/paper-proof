"""Run the style checks on every fetched source tree; print each note, for reading by hand.

python scripts/measure_style.py OUT_DIR        # OUT_DIR from fetch_arxiv_sources.py
"""

import sys
from collections import Counter
from pathlib import Path

from paper_proof.checks.style import check_style
from paper_proof.latex import find_main, read_project

kinds: Counter = Counter()
papers: Counter = Counter()
for d in sorted(p for p in Path(sys.argv[1]).iterdir() if p.is_dir()):
    main = find_main(d)
    if main is None:
        continue
    for f in check_style(read_project(main).texts):
        kinds[f.kind] += 1
        papers[f.kind, d.name] += 1
        print(f"{d.name} {f.kind:16} {f.file}:{f.line}  {f.message[:150]}")
print(kinds)
print("papers with each kind:", Counter(k for k, _ in papers))
