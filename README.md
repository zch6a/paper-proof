<div align="center">

# paper-proof

**Check your paper before reviewers do.** Every cited reference exists and matches its entry; bold results really
are the best; "from 27.3 to 28.9, a 9.5% gain" adds up; the numbers in the abstract are the ones in your tables; no
`\ref` prints as **??**. On your LaTeX project, any arXiv paper by its id, or a PDF, in one command, with the file
and line of everything it finds.

<a href="https://github.com/zch6a/paper-proof/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/zch6a/paper-proof/actions/workflows/ci.yml/badge.svg"></a>
<img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
<img alt="No AI" src="https://img.shields.io/badge/AI-none-blue">
<a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-blue"></a>

**English** · [简体中文](README.zh-CN.md)

</div>

---

Reviewers find the embarrassing mistakes: a citation to a paper that does not exist (a common slip of AI writing
assistants), a year off by one, a bold number that is not the best in its column, an abstract that still quotes the
result of an earlier run. paper-proof finds them first. This is its real output on
[the example paper](examples/paper/main.tex):

<p align="center"><img src="docs/demo.png" alt="paper-proof's output on the example paper: an undefined label, a stale abstract number, a wrong percentage, a misplaced bold, an invented and a mistyped reference" width="900"></p>

<details>
<summary>The same, offline, as text</summary>

```text
$ paper-proof examples/paper --offline
paper-proof 0.1.0 · examples/paper: main file main.tex, numbers, labels and citations (references not looked up: offline)

The paper against itself:
ERROR     main.tex:23  reference to tab:ablaton, which is never defined: it prints as ??
WARNING   main.tex:15  the abstract says 29.1, which is not in the text or any table, nor a difference or relative change between two numbers of one table column (an outdated number?)
WARNING   main.tex:15  the abstract says 1.8, which is not in the text or any table, nor a difference or relative change between two numbers of one table column (an outdated number?)
WARNING   main.tex:26  from 27.3 to 28.9 is a 5.9% relative change (1.6 points), not 9.5%
WARNING   main.tex:28  this sentence points to tab:main and says 29.2 (the table has 28.9): a number the table does not show, nor as a difference or relative change of two of its numbers
WARNING   main.tex:41  tab:main, BLEU \uparrow: 28.1 is bold but 28.9 (SMA-large (ours)) is higher
note      never referred to in the text: tab:ablation

Not cited anywhere in the text (not checked): unused2020

Summary: 1 ERROR, 5 WARNINGS, 1 note
```

</details>

## It finds these in famous papers

Run on the arXiv sources of 50 well-known papers (Transformer, BERT, GPT-3, LoRA, CLIP, Llama 2, DINOv2, ...),
paper-proof reports 7 problems. **We checked each one by hand against the source: all 7 are real.**

| Paper | Found |
|---|---|
| LoRA ([2106.09685](https://arxiv.org/abs/2106.09685)), GLUE table | QQP column: 91.9 is bold, 92.1 in the same group is higher (the caption says higher is better) |
| DINOv2 ([2304.07193](https://arxiv.org/abs/2304.07193)), data ablation | ADE-20k: 47.7 is bold, "Uncurated data" has 48.5 |
| Chinchilla ([2203.15556](https://arxiv.org/abs/2203.15556)), abstract | says 67.5% on MMLU; the text and the table say 67.6% |
| vLLM ([2309.06180](https://arxiv.org/abs/2309.06180)) | `eq:attention-layer` is defined for two different equations: every reference to it resolves to just one of them |
| LLaVA ([2304.08485](https://arxiv.org/abs/2304.08485)) | `tab:full_example_car_bbox` is defined in the main text and again in the appendix |
| LLaVA-1.5 ([2310.03744](https://arxiv.org/abs/2310.03744)) | two different tables are both `tab:results` |
| BLIP-2 ([2301.12597](https://arxiv.org/abs/2301.12597)) | two figures share `fig:example_limitation` |

None of these changes a paper's conclusions. They are exactly the slips that get past authors and get noticed by
readers, and the kind a tool can rule out before submission.

## What it checks

**The paper against itself** (offline: nothing is sent anywhere)

| | |
|---|---|
| **Bold that is not best** | a bold number that is the only bold one of its column (within its group of rows) but not the best of it. Which way is better comes from ↑/↓, the metric (BLEU, accuracy, FID, perplexity, error, latency, ...) or the caption ("higher is better"). Tables with models in columns are read by row |
| **Claimed changes** | "from A to B, a p% improvement" and "an N× speedup": p and N recomputed from A and B, as a relative change or in points, allowing for rounding |
| **Abstract numbers** | each decimal number in the abstract appears in the text or a table (rounding allowed: 28.43 → 28.4); where the abstract talks about a gain, it may also be a difference or a relative change between two numbers of one table column |
| **Averages** | an "Avg" / "Average" / "Mean" column is the mean of the numbers before it in each row (all of them, or the last few: the set the table's other rows use), allowing for rounding. A table whose rows mostly disagree defines its average another way (weighted) and is left alone |
| **Text against tables** | a sentence that points to a table (`Table~\ref{tab:main}`) and quotes a number: the number is in that table, or a difference or relative change of two of its numbers. Reported only when a cell of the table is within 5% of it (a stale or mistyped result), with that cell |
| **Labels** | `\ref`, `\cref`, `\autoref`... to labels that are never defined (they print as ??); labels defined twice (an error when something refers to them); figures and tables never referred to |
| **Citations** | `\cite` keys with no bibliography entry (they print as [?]); entries nobody cites |

**Each cited reference** (online: title and identifiers go to the databases below)

| | |
|---|---|
| **Exists** | looked up by DOI (Crossref; a DOI Crossref does not hold, such as Zenodo's, is confirmed at doi.org) and arXiv id, then by title in Semantic Scholar, OpenAlex, Crossref and arXiv. Not found in at least two databases that answered: `NOT FOUND`, with the closest title if there is one |
| **Matches** | title, first author, the other authors, the year, and a DOI or arXiv id that points to a different work: `MISMATCH`. A year more than one before the record's is an error; a later one is only a note (a later version, a journal version or a reprint) |
| **Retracted** | the work is marked retracted in OpenAlex: `RETRACTED` |
| **Published since** | cited as an arXiv preprint, but published at a venue: says where, so you can cite the final version |
| **Duplicates** | two entries with the same DOI, arXiv id or title |

Only what the text actually cites is checked: paper-proof follows `\input`, `\include` and `\subfile` from the main
file, reads the `.bib` files of `\bibliography` / `\addbibresource` (or the compiled `.bbl`, or a `thebibliography`
environment, in any BibTeX style or biblatex), ignores comments, `\iffalse` blocks and `comment` environments, and
understands natbib's and biblatex's `\citep`, `\citet`, `\parencite`, `\textcite`, `\autocite`, `\cites`...

## How accurate it is

Measured with the scripts in [`scripts/`](scripts/) on the 50 papers of [`scripts/papers.txt`](scripts/papers.txt)
(the sources are fetched from arXiv for the measurement and never stored here).

- **False alarms.** The first version raised 85 warnings on these papers, nearly all false. Each one was read in the
  source and the rule fixed: ties marked in bold, bold for the best of each category, pairwise tables with a Δ column,
  diagonal bold (the setting tested), bold for the largest value where lower is better, human and oracle rows,
  labels inside macros and `\iftoggle` branches. Now: 7 errors and warnings, 7 real (the table above).
- **Missed problems.** Errors injected into the same 50 papers (in memory) are found: a correct bold moved to a worse
  cell, **41 of 42**; a number of the abstract changed to one that is nowhere in the paper, **9 of 11**; a number in a
  sentence that points to a table moved by 0.3, **14 of 18** (the four missed are values like 0.01, where 0.3 is no
  near neighbour); an average that agrees with its row changed by 0.5, **6 of 6** (only six tables of the 50 papers
  have a plain-mean average column, so this one is a small sample).
- **References.** On the 264 references of five papers (Transformer, LoRA, DPO, LLaMA, Mistral), the first version
  reported 23 mismatches, nearly all false: later versions cited with a later year, compound and transliterated
  names, arXiv and Zenodo DOIs that Crossref does not hold, consortium authors. After the fixes: 4 mismatches, two of
  them real (LoRA cites Jihun Hamm as "Ham"; DPO lists the wrong first author for "Dueling RL"). Recorded answers of
  the databases drive the tests (no test reaches the network).
- **PDFs.** Of the same papers' 372 references read from their PDFs, 323 titles come out exactly and 367 can be
  matched (the whole printed entry is matched when the title cannot be cut out).

What it will get wrong:
- A convention it cannot see. When bold means something other than "best" and the caption does not say so, you get a
  warning to dismiss. paper-proof stays quiet whenever a column has several bold numbers, the caption explains bold
  ("not significantly worse", "better than the baseline"), or the table compares pairs.
- A table it cannot read: one drawn as an image, built by a macro it does not expand, or in a package other than
  tabular / tabularx / longtable.
- A reference that is real but in none of the four databases (a workshop paper, a thesis, a technical report, a book
  chapter): it is `NOT FOUND`, with the closest title. Web pages, software and `@misc` entries without a DOI or arXiv id
  are skipped, not reported.

## Install

paper-proof needs Python 3.10+. With [uv](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/zch6a/paper-proof paper-proof path/to/paper
```

or install it: `uv tool install git+https://github.com/zch6a/paper-proof` (or `pipx install git+https://github.com/zch6a/paper-proof`).

## Use

```bash
paper-proof paper/                 # a LaTeX project folder (the main .tex is found), all checks
paper-proof paper/main.tex         # the main file
paper-proof paper/ --offline       # numbers, labels and citations only: nothing is sent anywhere
paper-proof 2106.09685             # any arXiv paper: its LaTeX source, in a temporary folder deleted afterwards
paper-proof paper.pdf              # a PDF: its references (tables lose their bold in a PDF's text)
paper-proof refs.bib               # just a bibliography
paper-proof paper/ --format json   # every finding with file and line, for scripts
paper-proof paper/ --format md     # a Markdown table, for a pull request or a review
```

| Option | |
|---|---|
| `--checks refs,numbers` | what to check (default both; `--offline` is `--checks numbers`) |
| `--fail-on not-found` | exit 1 for: `not-found` (default: invented or retracted references, undefined citations and labels), `mismatch` (also wrong details and number warnings), `never` |
| `--only KEY` | check only these bibliography keys (repeatable) |
| `--jobs 4` | references checked at once; each database keeps its own pace |
| `--no-cache`, `--cache-dir` | answers are cached for 30 days, so a second run asks nobody again |
| `--color auto` | `always`, `never`; by default colours only on a terminal (`FORCE_COLOR` and `NO_COLOR` are honoured) |

Exit codes: 0 nothing at the `--fail-on` level, 1 something found, 2 the input could not be read.

## On every push (GitHub Action)

For a paper kept in a repository (an Overleaf project synced with GitHub works too):

```yaml
name: paper-proof
on: [push, pull_request]
permissions:
  contents: read
jobs:
  proof:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: zch6a/paper-proof@v0
        with:
          path: paper          # the LaTeX project folder
          # checks: numbers    # offline only
          # fail-on: mismatch  # stricter
```

The report goes to the job summary as a Markdown table; the JSON report is the `report` output. The action needs only
read access, runs nothing from your repository, and caches the databases' answers between runs.

## In your AI agent (Agent Skill)

[`plugin/skills/paper-proof/SKILL.md`](plugin/skills/paper-proof/SKILL.md) teaches Claude Code and other agents that
read Agent Skills when and how to run paper-proof, and how to read its results (an unknown is not an error; a warning
about bold may be a convention, to put to the author as a question). Install the plugin from this repository, or copy
the skill folder into your agent's skills.

## Privacy and politeness

- The number checks are offline. The reference checks send titles, DOIs and arXiv ids, nothing else, to Crossref,
  arXiv, Semantic Scholar and OpenAlex (and a DOI to doi.org when Crossref does not know it), with a generic
  User-Agent, at the pace each service asks for (arXiv: one request every 3 seconds), retrying politely on 429 and
  5xx; a database that keeps failing is left alone for the rest of the run. Given an arXiv id, paper-proof fetches
  that paper's source from arxiv.org, even with `--offline`.
- Answers are cached on disk (30 days), so re-running after an edit asks nobody again.
- Optional: `PAPER_PROOF_MAILTO=you@example.org` gives Crossref a contact address (its "polite pool");
  `OPENALEX_API_KEY` raises OpenAlex's daily budget tenfold. Neither is needed or sent unless you set it.
- DBLP is not used: it now answers scripted requests with a bot check, and paper-proof does not get around those.

## License

MIT
