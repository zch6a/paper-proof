# Changelog

## 0.2.1 — 2026-11-14

- The Claude Code plugin's manifest (`plugin/.claude-plugin/plugin.json`) says 0.2.1: it had stayed at an older
  version through the last release, so the marketplace showed the old one (found by `repro-score release`).
- A `CITATION.cff`, for GitHub's "Cite this repository".

## 0.2.0

**The paper as a whole** (`--checks consistency`, on by default, offline; LaTeX and PDF):

- Acronyms: one acronym spelled out two different ways (a warning); spelled out again after its first definition;
  used before it is spelled out; spelled out only in the abstract or a caption. The abstract and captions do not
  count as the first definition; files are read in the order `\input` and `\include` put them in. "Low-Rank
  Adaptation (LoRA)" and "Low-Rank Adaptation, or LoRA" are both definitions.
- One term written two ways ("pre-training" and "pretraining", "data set" and "dataset"), with how often each is used.
- British and American spelling mixed in one paper.
- (LaTeX) One symbol given two meanings ("Let $N$ be the number of layers", later "Let $N$ be the batch size").

On the 50 papers of `scripts/papers.txt`: 5 acronyms spelled out two ways, all real (Mamba, RoFormer, InstructGPT,
BERT); 11 papers mixing British and American spelling, all real; terms written two ways in 45 papers, 28 of a sample
of 30 real. `scripts/measure_consistency.py` reproduces the counts.

**For reviewers** (`--review`): on a submitted PDF (or LaTeX), nothing is sent anywhere; the report lists points to
check, with page numbers, and the exit code is 0. `--lookup-references` adds the reference list (its titles and
authors are sent to OpenAlex and Crossref, and the report says so).

**A PDF gets more than its references**: claimed changes ("from A to B, a p% gain") and abstract numbers that appear
nowhere else in the text are checked too, with page numbers; its reference list is left out of the prose checks.

## 0.1.0

First release.

- **References**: looked up by DOI and arXiv id, then by title in Semantic Scholar, OpenAlex, Crossref and arXiv.
  Not found (in at least two databases that answered), mismatched (title, first author, authors, year, an identifier
  pointing to another work), retracted, cited as a preprint but published since, duplicated. A database that does
  not answer makes the result unknown, never "not found". Answers cached on disk for 30 days.
- **LaTeX projects**: only what the text cites is checked, following `\input`, `\include` and `\subfile`; natbib and
  biblatex citation commands; `.bib`, `.bbl` (BibTeX styles and biblatex) or `thebibliography`; comments, `\iffalse`
  and `comment` environments ignored. Undefined citations and uncited entries.
- **The paper against itself** (offline): bold numbers that are not the best, claimed changes recomputed, abstract
  numbers found nowhere in the paper, numbers in sentences that point to a table against that table, average columns
  against their rows, undefined and duplicate labels, unreferenced figures and tables.
- Inputs: a LaTeX project, `.bib`, `.bbl`, a PDF (references), or an arXiv id (its source, fetched and deleted).
- Reports for the terminal, as JSON and as Markdown; a GitHub Action; an Agent Skill.
- Measured on 50 real papers: 7 findings, all real; injected errors found 41/42 (bold), 9/11 (abstract numbers),
  14/18 (text against tables), 6/6 (averages). On 264 real references: 4 mismatches, two of them real errors.
- Hardened after an independent code review: parallel cache writes, interrupted downloads, damaged and oversized
  arXiv archives, network paths in `\input`, a quadratic regex, non-UTF-8 sources.
