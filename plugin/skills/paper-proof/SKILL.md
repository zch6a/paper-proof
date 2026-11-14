---
name: paper-proof
description: Check a research paper before submission with paper-proof. Finds invented, retracted or wrong references (title, authors, year, DOI checked against Crossref, arXiv, Semantic Scholar and OpenAlex), bold table results that are not the best, claimed improvements that do not add up, abstract numbers found nowhere in the paper, references to labels that do not exist, and inconsistencies across the paper (an acronym spelled out two ways, one term written two ways, British and American spelling mixed, a symbol with two meanings); with --review, points for a reviewer to check in a submitted PDF without sending it anywhere. Use when the user is writing or reviewing a LaTeX paper, asks to check citations or a bibliography, or wants a paper checked before submission or camera-ready.
license: MIT
compatibility: Needs Python 3.10+ and uv. Runs paper-proof with uvx from GitHub (git+https://github.com/zch6a/paper-proof) unless a paper-proof command is installed. The number checks are offline; the reference checks ask public bibliographic databases.
metadata:
  homepage: https://github.com/zch6a/paper-proof
---

# Checking a paper with paper-proof

paper-proof reads a LaTeX project (follows `\input` and `\include`, reads the `.bib`, `.bbl` or `thebibliography`)
and checks it two ways:

- **the paper against itself, offline**: a bold number that is not the best of its column; "from A to B, a p%
  gain" recomputed; a number in the abstract that appears nowhere else (an outdated result); a number in a sentence
  that points to a table but differs slightly from that table's value; an "Avg" column that is not the mean of its
  row; `\ref` to a label that
  does not exist; a label defined twice; a figure or table never referred to.
- **the paper as a whole, offline**: an acronym spelled out two ways, spelled out again, used before it is spelled
  out, or spelled out only in the abstract; one term written two ways ("pre-training" and "pretraining"); British and
  American spelling mixed; a symbol given two meanings (LaTeX).
- **style, through the LaTeX, offline** (notes): a word written twice, "a"/"an", `Figure \ref` without `~`, "Fig." and
  "Figure" mixed, "et al" without its period, straight double quotes, `\cite{a}\cite{b}`. Fixing these is mechanical:
  offer to do it, one edit per note.
- **each cited reference, online**: it exists (by DOI, arXiv id, then title), matches its entry (title, first author,
  authors, year), is not retracted, and points to the published version when it was cited as a preprint.

## Running it

Start offline: nothing leaves the machine.

```bash
uvx --from git+https://github.com/zch6a/paper-proof paper-proof path/to/paper --offline
```

Then the references (they are sent, by title and identifiers only, to Crossref, arXiv, Semantic Scholar and OpenAlex;
answers are cached on disk, so a second run asks nobody again). Tell the user before running this part:

```bash
uvx --from git+https://github.com/zch6a/paper-proof paper-proof path/to/paper
```

**Reviewing someone else's submission** (a PDF the user may not upload anywhere): use `--review`. It sends nothing,
lists points to check with page numbers, and exits 0. Do not add `--lookup-references` unless the user agrees: it
sends the references' titles and authors to OpenAlex and Crossref. Present the points as things for the reviewer
to verify in the paper; never write the review, and never paste the submission's text into another service.

```bash
uvx --from git+https://github.com/zch6a/paper-proof paper-proof submission.pdf --review
```

Use `paper-proof` instead of `uvx --from git+https://github.com/zch6a/paper-proof paper-proof` if it is installed.
`path/to/paper` is the project folder, its main `.tex` file, a `.bib` or a `.bbl`. `--format json` gives every finding
with file and line; `--format md` a table for a pull request or a review.

## Reading the results

- `NOT FOUND`: no database has a work with this title, and at least two answered. Likely invented (a frequent
  error in AI-written bibliographies) or badly mistyped; the closest title found is shown when there is one. Ask the
  user where the reference came from; never invent a replacement.
- `MISMATCH`: the work exists but the entry differs (year, first author, a DOI that points elsewhere). Suggest the
  correction shown, with its link.
- `UNKNOWN`: a database did not answer. Not an error; run again later.
- `RETRACTED`: the cited work was retracted. Tell the user plainly.
- Number warnings name the file, the line and what was compared. They can be conventions the tool cannot see (bold
  for "not significantly worse", for the best of each category): show them to the user as questions, not as
  errors, and let the user decide. Do not edit numbers in a paper yourself.

Exit code 1 means something at the `--fail-on` level was found (default: not-found, retracted, undefined citation or
label); 2 means the input could not be read.
