# Security

paper-proof reads LaTeX and BibTeX written by anyone (a co-author, a template, a bibliography copied from the web) and
text returned by public databases. Both are treated as untrusted.

## What it does

- **Runs nothing from the paper.** It reads `.tex`, `.bib` and `.bbl` files as text. It never runs LaTeX, BibTeX,
  shell escapes or anything else from the project, and only follows `\input` / `\include` / `\bibliography` to files
  inside the project's folder. Absolute, drive, UNC (`//host/share`) and `..` names are rejected from their text,
  before any file system call, so a paper cannot make it open a network share.
- **Bounded on hostile input.** An arXiv source is unpacked with a cap on the total (500 MB) and only its source
  files are kept; a damaged archive is an error message. Table spans are capped, and the regular expressions run on
  prose are linear (tested on long runs of blanks).
- **Hostile text stays text.** Titles and keys from the bibliography and from the databases are shown with control
  and bidirectional characters made visible, so they cannot move the terminal's cursor or rewrite its title. In the
  Markdown report, nothing renders: no links, images, HTML or @mentions.
- **Sends little, and only where it says.** The reference checks send titles, DOIs and arXiv ids to Crossref,
  arXiv, Semantic Scholar and OpenAlex (and a DOI to doi.org when Crossref does not know it) over HTTPS, with a
  generic User-Agent; a contact address or an API key only if you set `PAPER_PROOF_MAILTO` or `OPENALEX_API_KEY`.
  `--offline` sends nothing, except fetching the source when the input is an arXiv id.
- **The GitHub Action** needs only `contents: read`, runs the tool at the action's own ref (never code from the
  repository it checks), and passes inputs through environment variables, not into the script's text.
- **One dependency** (pypdf), and the workflows pin their actions to commits and test with a read-only token.

## What it does not protect against

- **A database that is wrong.** A record with a wrong year or a missing author makes a correct reference look
  mismatched. The report links the record, so it can be checked.
- **Relying on it alone.** It finds the problems it knows how to find; a paper it says nothing about is not proven
  correct.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security → Report a vulnerability) rather than a public issue,
with the file that shows the problem.
