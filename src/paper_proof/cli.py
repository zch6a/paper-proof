"""paper-proof on the command line."""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import __version__, report
from .bib import BibError, parse_bib
from .check import Reference, Verdict, check_reference, duplicates, reference_from_bib
from .latex import find_main, parse_bbl, read_project
from .transport import CachedTransport, HttpTransport, Transport, default_cache_dir

FAIL_LEVELS = {"not-found": {"not-found", "retracted"}, "mismatch": {"not-found", "retracted", "mismatch"}, "never": set()}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="paper-proof",
        description="Check the references of a paper: each one exists and matches its bibliography entry "
        "(title, authors, year), is not retracted, and points to the published version when there is one.",
    )
    p.add_argument("--version", action="version", version=f"paper-proof {__version__}")
    p.add_argument("bib", metavar="PAPER", help="a LaTeX project folder, its main .tex file, a .bib, or a compiled .bbl")
    p.add_argument("--format", choices=["text", "json", "md"], default="text", help="report format (default: text)")
    p.add_argument("--fail-on", choices=list(FAIL_LEVELS), default="not-found", help="exit 1 when there are references this bad (default: not-found)")
    p.add_argument("--jobs", type=int, default=4, help="references checked at once (default 4; each database is still asked politely)")
    p.add_argument("--no-cache", action="store_true", help="ask the databases again instead of using answers cached on disk")
    p.add_argument("--cache-dir", type=Path, default=None, help=f"where answers are cached (default: {default_cache_dir()})")
    p.add_argument("--only", action="append", default=[], help="check only these entry keys (repeatable)")
    return p


def run(argv: list[str] | None = None, transport: Transport | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.bib)
    if args.jobs < 1:
        print("paper-proof: --jobs must be at least 1", file=sys.stderr)
        return 2
    try:
        refs, extra = load(path)
    except OSError as e:
        print(f"paper-proof: cannot read {path}: {e.strerror or e}", file=sys.stderr)
        return 2
    except (BibError, InputError) as e:
        print(f"paper-proof: {path}: {e}", file=sys.stderr)
        return 2
    if args.only:
        refs = [r for r in refs if r.key in set(args.only)]
    if transport is None:
        http = HttpTransport()
        transport = http if args.no_cache else CachedTransport(http, args.cache_dir or default_cache_dir())
    progress = sys.stderr.isatty() and args.format == "text" and len(refs) > 1
    verdicts: list[Verdict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for i, v in enumerate(pool.map(lambda r: check_reference(r, transport), refs), 1):
            verdicts.append(v)
            if progress:
                print(f"\rchecking {i}/{len(refs)}", end="", file=sys.stderr, flush=True)
    if progress:
        print("\r" + " " * 30 + "\r", end="", file=sys.stderr)
    dups = duplicates(refs)
    source = str(path)
    if args.format == "json":
        print(report.to_json(verdicts, dups, source, extra))
    elif args.format == "md":
        print(report.markdown(verdicts, dups, source, extra))
    else:
        print(report.text(verdicts, dups, source, extra, color=report.use_color()))
    bad = FAIL_LEVELS[args.fail_on]
    return 1 if any(v.status in bad for v in verdicts) or (extra.undefined and args.fail_on != "never") else 0


class InputError(ValueError):
    pass


def load(path: Path) -> tuple[list[Reference], report.Extra]:
    """The references to check, from a .bib, a .bbl, a .tex file, or a LaTeX project folder."""
    extra = report.Extra()
    if path.is_dir():
        main = find_main(path)
        if main is None:
            raise InputError("no .tex file with \\documentclass and \\begin{document} in this folder")
        path = main
    suffix = path.suffix.lower()
    if suffix == ".bib":
        refs = []
        for e in parse_bib(path.read_text(encoding="utf-8-sig")):
            refs.append(reference_from_bib(e))
        return refs, extra
    if suffix == ".bbl":
        return parse_bbl(path.read_text(encoding="utf-8", errors="replace"), path.name), extra
    if suffix == ".tex":
        proj = read_project(path)
        extra.main = proj.main.name
        extra.bibliography_from = proj.bibliography_from
        extra.undefined = proj.undefined()
        extra.uncited = [r.key for r in proj.uncited()]
        extra.missing_files = proj.missing_files
        if not proj.references:
            raise InputError(
                "no bibliography found: no \\bibliography{...} or \\addbibresource{...} with an existing .bib file, "
                "no thebibliography environment, and no compiled .bbl next to the main file"
            )
        return proj.checked(), extra
    raise InputError("give a .bib, .bbl or .tex file, or a LaTeX project folder")


def main() -> None:
    sys.exit(run())
