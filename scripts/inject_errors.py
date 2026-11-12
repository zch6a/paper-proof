"""Recall on injected errors, in memory (the sources on disk are not changed):
1. a correct single bold moved to a worse cell of its column (not the best of its group either) -> bold-not-best
   expected on that line;
2. a decimal number of the abstract that also appears in a table changed to a value found nowhere -> abstract-number.

    uv run python scripts/inject_errors.py SOURCES_DIR   (fill it with scripts/fetch_arxiv_sources.py)
"""

import random
import re
import sys
from collections import Counter
from pathlib import Path

import paper_proof.numbers as N
from paper_proof.latex import find_main, read_project
from paper_proof.numbers import _abstract, _is_best, _want, abstract_numbers, bold_not_best
from paper_proof.tables import find_tables

random.seed(0)
root = Path(sys.argv[1])
stats = Counter()
misses = []

for d in sorted(p for p in root.iterdir() if p.is_dir()):
    main = find_main(d)
    if not main:
        continue
    texts = read_project(main).texts
    # ---- 1. move a bold
    for f, text in texts.items():
        for t in find_tables(text, f):
            if bold_not_best(t):
                continue  # already reported: not a clean starting point
            for j in range(max((len(r) for r in t.rows), default=0)):
                col = t.column(j)
                bolds = [(i, c) for i, c in col if c.bold]
                want = _want(t, j)
                if len(col) < 4 or len(bolds) != 1 or not want or not _is_best(bolds[0][1].value, [c for _, c in col], want):
                    continue
                bi, bc = bolds[0]

                groups = {g: [x for k, x in col if t.groups[k] == g] for g in set(t.groups)}
                worse = [
                    (i, c)
                    for i, c in col
                    if not c.bold
                    and not _is_best(c.value, [x for _, x in col], want)
                    and not (len(groups[t.groups[i]]) > 1 and _is_best(c.value, groups[t.groups[i]], want))
                    and abs(c.value - bc.value) > 0.05
                ]
                if not worse:
                    continue
                ti, tc = random.choice(worse)
                lines = text.split("\n")
                bl, tl = bc.line - 1, tc.line - 1
                # unbold the bold cell (first \textbf{...} / {\bf ...} holding its number on its line)
                num_b = re.escape(f"{bc.value:.{bc.decimals}f}")
                new_bl, n1 = re.subn(r"\\textbf\s*\{\s*(" + num_b + r")", r"{\1", lines[bl], count=1)
                if not n1:
                    new_bl, n1 = re.subn(r"\{\s*\\bf(?:series)?\s+(" + num_b + r")", r"{\1", lines[bl], count=1)
                if not n1:
                    continue
                lines[bl] = new_bl
                num_t = f"{tc.value:.{tc.decimals}f}"
                cells = lines[tl].split("&")
                hit = [k for k, cell in enumerate(cells) if re.search(r"(?<![\d.])" + re.escape(num_t) + r"(?![\d])", cell)]
                if len(hit) != 1:
                    continue
                k = hit[0]
                cells[k] = re.sub(r"(?<![\d.])(" + re.escape(num_t) + r")(?![\d])", r"\\textbf{\1}", cells[k], count=1)
                lines[tl] = "&".join(cells)
                mutated = "\n".join(lines)
                stats["bold injected"] += 1
                found = [x for x in find_tables(mutated, f) if x.line == t.line]
                hits = [g for x in found for g in bold_not_best(x) if g.line == tc.line]
                if hits:
                    stats["bold detected"] += 1
                else:
                    x = found[0] if found else None
                    why = (
                        "table lost"
                        if x is None
                        else (
                            f"caption={bool(N.OTHER_MEANING.search(x.caption))} diag={N._diagonal(x)} ext={N._marks_extremes(x)} "
                            f"row={N._row_oriented(x)} hdr={x.header_rows} groups={x.groups[:10]}"
                        )
                    )
                    misses.append(f"bold miss {d.name} {f}:{tc.line} ({bc.value} -> {tc.value}) {t.name} :: {why}")
                break  # one injection per table
    # ---- 2. change an abstract number
    for f, text in texts.items():
        a = _abstract(text)
        if not a:
            continue
        start, abstract = a
        tables = [t for ff, tt in texts.items() for t in find_tables(tt, ff)]
        table_numbers = {f"{c.value:.{c.decimals}f}" for t in tables for r in t.rows for c in r if c.value is not None}
        everything = "\n".join(texts.values())
        for m in re.finditer(r"(?<![\w.\\-])(\d+\.\d)(?![\w.-])", abstract):
            s = m.group(1)
            if s not in table_numbers:
                continue
            v = float(s) + 1.3
            new = f"{v:.1f}"
            if new in everything:
                continue
            mutated = dict(texts)
            pos = start + m.start(1)
            mutated[f] = text[:pos] + new + text[pos + len(s) :]
            if [g for g in abstract_numbers(texts, tables) if s in g.message]:
                continue  # already reported before the change
            stats["abstract injected"] += 1
            if [g for g in abstract_numbers(mutated, tables) if new in g.message]:
                stats["abstract detected"] += 1
            else:
                misses.append(f"abstract miss {d.name}: {s} -> {new}")
        break
    # ---- 3. change a number in a sentence that points to a table (the number is in that table) by a little
    tables = [t for ff, tt in texts.items() for t in find_tables(tt, ff)]
    by_label = {t.label: t for t in tables if t.label}
    everything = "\n".join(texts.values())
    for f, text in texts.items():
        done = 0
        for key, pos in N.refs_in(text):
            if key not in by_label or done >= 3:
                continue
            lo, hi = N._sentence(text, pos)
            nums = {f"{y:.{dd}f}" for y, dd in N._table_numbers(by_label[key]) if dd >= 1}
            for m in re.finditer(r"(?<![\w.\\-])(\d+\.\d+)(?![\w.-])", text[lo:hi]):
                s = m.group(1)
                if s not in nums:
                    continue
                dec = len(s.split(".")[1])
                new = f"{float(s) + 0.3:.{dec}f}"
                if new in everything:
                    continue
                p = lo + m.start(1)
                mutated = dict(texts)
                mutated[f] = text[:p] + new + text[p + len(s) :]
                before = [g for g in N.table_mentions(texts, tables) if g.file == f]
                after = [g for g in N.table_mentions(mutated, tables) if g.file == f and new in g.message]
                if before and any(s in g.message for g in before):
                    continue
                stats["text-vs-table injected"] += 1
                if after:
                    stats["text-vs-table detected"] += 1
                else:
                    misses.append(f"text-vs-table miss {d.name} {f}: {s} -> {new} ({key})")
                done += 1
                break

    # ---- 4. an average cell that agrees with its row changed by 0.5
    for f, text in texts.items():
        for t in find_tables(text, f):
            if N.average_columns(t) or not t.header_rows:
                continue
            # only averages that are plain means in this table: every evaluated row agrees, at least 3 of them
            for j, agree, disagree in N.average_rows(t):
                if disagree or len(agree) < 3:
                    continue
                for i in agree:
                    c = t.rows[i][j] if j < len(t.rows[i]) else None
                    if c is None or c.value is None or c.decimals < 1:
                        continue
                    old = f"{c.value:.{c.decimals}f}"
                    new = f"{c.value + 0.5:.{c.decimals}f}"
                    lines = text.split("\n")
                    if lines[c.line - 1].count(old) != 1:
                        continue
                    lines[c.line - 1] = lines[c.line - 1].replace(old, new)
                    mutated = "\n".join(lines)
                    found = [x for x in find_tables(mutated, f) if x.line == t.line]
                    stats["average injected"] += 1
                    if found and any(g.line == c.line for g in N.average_columns(found[0])):
                        stats["average detected"] += 1
                    else:
                        misses.append(f"average miss {d.name} {f}:{c.line} ({old} -> {new}) {t.name}")
                    break

print(stats)
for x in misses[:40]:
    print(x)
