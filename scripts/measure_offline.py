"""Run the offline checks on every fetched source tree; print findings per paper."""

import sys
import traceback
from collections import Counter
from pathlib import Path

from paper_proof.latex import find_main, read_project
from paper_proof.numbers import check_numbers
from paper_proof.tables import find_tables

root = Path(sys.argv[1])
kinds = Counter()
for d in sorted(p for p in root.iterdir() if p.is_dir()):
    main = find_main(d)
    if main is None:
        print(f"== {d.name}: no main file")
        continue
    try:
        proj = read_project(main)
        tables = sum(len(find_tables(t, f)) for f, t in proj.texts.items())
        fs = check_numbers(proj.texts)
    except Exception:
        print(f"== {d.name}: CRASH")
        traceback.print_exc()
        continue
    print(
        f"== {d.name}: main {main.relative_to(d)}, {len(proj.texts)} files, {tables} tables, {len(proj.cited)} cited, "
        f"{len(proj.references)} refs ({proj.bibliography_from}), {len(proj.undefined())} undefined, {len(fs)} findings"
    )
    for f in fs:
        kinds[f.kind] += 1
        if f.kind != "unreferenced" or "-v" in sys.argv:
            print(f"   {f.severity:7} {f.kind:16} {f.file}:{f.line}  {f.message[:230]}")
print(kinds)
