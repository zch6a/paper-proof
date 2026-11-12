"""paper-proof on the command line."""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import __version__, report
from .bib import BibError, parse_bib
from .check import Verdict, check_reference, duplicates, reference_from_bib
from .transport import CachedTransport, HttpTransport, Transport, default_cache_dir

FAIL_LEVELS = {"not-found": {"not-found", "retracted"}, "mismatch": {"not-found", "retracted", "mismatch"}, "never": set()}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="paper-proof",
        description="Check the references of a paper: each one exists and matches its bibliography entry "
        "(title, authors, year), is not retracted, and points to the published version when there is one.",
    )
    p.add_argument("--version", action="version", version=f"paper-proof {__version__}")
    p.add_argument("bib", help="a .bib file")
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
    try:
        entries = parse_bib(path.read_text(encoding="utf-8-sig"))
    except OSError as e:
        print(f"paper-proof: cannot read {path}: {e.strerror or e}", file=sys.stderr)
        return 2
    except BibError as e:
        print(f"paper-proof: {path}: {e}", file=sys.stderr)
        return 2
    if args.only:
        entries = [e for e in entries if e.key in set(args.only)]
    if args.jobs < 1:
        print("paper-proof: --jobs must be at least 1", file=sys.stderr)
        return 2
    if transport is None:
        http = HttpTransport()
        transport = http if args.no_cache else CachedTransport(http, args.cache_dir or default_cache_dir())
    refs = [reference_from_bib(e) for e in entries]
    progress = sys.stderr.isatty() and args.format == "text"
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
        print(report.to_json(verdicts, dups, source))
    elif args.format == "md":
        print(report.markdown(verdicts, dups, source))
    else:
        print(report.text(verdicts, dups, source, color=report.use_color()))
    bad = FAIL_LEVELS[args.fail_on]
    return 1 if any(v.status in bad for v in verdicts) else 0


def main() -> None:
    sys.exit(run())
