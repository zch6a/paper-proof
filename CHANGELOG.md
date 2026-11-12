# Changelog

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
  numbers found nowhere in the paper, undefined and duplicate labels, unreferenced figures and tables.
- Reports for the terminal, as JSON and as Markdown; a GitHub Action; an Agent Skill.
- Measured on 50 real papers: 7 findings, all real; injected errors found 41/42 (bold) and 9/11 (abstract numbers).
