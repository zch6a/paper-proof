"""paper-proof on the command line."""

from __future__ import annotations

import argparse
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import __version__, arxiv_source, report
from .bib import BibError, parse_bib
from .check import Reference, Verdict, check_reference, duplicates, reference_from_bib
from .latex import find_main, parse_bbl, read_project
from .numbers import check_numbers
from .transport import CachedTransport, HttpTransport, ReplayTransport, Transport, TransportError, default_cache_dir

FAIL_LEVELS = {"not-found": {"not-found", "retracted"}, "mismatch": {"not-found", "retracted", "mismatch"}, "never": set()}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="paper-proof",
        description="Check a paper before anyone else does. References: each one exists and matches its bibliography "
        "entry (title, authors, year), is not retracted, and points to the published version when there is one. "
        "Numbers (LaTeX): bold results that are not the best, claimed changes that do not add up, abstract numbers found "
        "nowhere in the paper, references to labels that do not exist.",
    )
    p.add_argument("--version", action="version", version=f"paper-proof {__version__}")
    p.add_argument("bib", metavar="PAPER", help="a LaTeX project folder, its main .tex file, a .bib, a compiled .bbl, or an arXiv id (2106.09685)")
    p.add_argument("--format", choices=["text", "json", "md"], default="text", help="report format (default: text)")
    p.add_argument("--fail-on", choices=list(FAIL_LEVELS), default="not-found", help="exit 1 when there are references this bad (default: not-found)")
    p.add_argument("--jobs", type=int, default=4, help="references checked at once (default 4; each database is still asked politely)")
    p.add_argument("--no-cache", action="store_true", help="ask the databases again instead of using answers cached on disk")
    p.add_argument("--cache-dir", type=Path, default=None, help=f"where answers are cached (default: {default_cache_dir()})")
    p.add_argument("--only", action="append", default=[], help="check only these entry keys (repeatable)")
    p.add_argument(
        "--checks",
        default="refs,numbers",
        help="what to check, comma-separated: refs (references, online), numbers (tables, claimed changes, abstract numbers, "
        "labels: offline, LaTeX only). Default: refs,numbers",
    )
    p.add_argument("--offline", action="store_true", help="same as --checks numbers: the checks send nothing (an arXiv id is still fetched)")
    return p


def run(argv: list[str] | None = None, transport: Transport | None = None, fetcher=None) -> int:
    """`transport` and `fetcher` stand in for the network in tests."""
    args = build_parser().parse_args(argv)
    path = Path(args.bib)
    checks = {"numbers"} if args.offline else {c.strip() for c in args.checks.split(",") if c.strip()}
    if not checks or checks - {"refs", "numbers"}:
        print(f"paper-proof: --checks takes refs and/or numbers, not {args.checks!r}", file=sys.stderr)
        return 2
    if args.jobs < 1:
        print("paper-proof: --jobs must be at least 1", file=sys.stderr)
        return 2
    if not path.exists() and arxiv_source.is_arxiv_id(args.bib):
        # An arXiv id: its source into a temporary folder, checked, then deleted.
        if transport is not None and fetcher is None:
            print("paper-proof: an arXiv id needs the network", file=sys.stderr)
            return 2
        if args.format == "text":
            print(f"fetching the LaTeX source of {args.bib} from arxiv.org (kept in a temporary folder, deleted afterwards)", file=sys.stderr)
        with tempfile.TemporaryDirectory(prefix="paper-proof-") as tmp:
            try:
                (fetcher or arxiv_source.fetch)(args.bib, Path(tmp))
            except (TransportError, ValueError) as e:
                print(f"paper-proof: {e}", file=sys.stderr)
                return 2
            return _check(Path(tmp), args, checks, transport, f"arXiv:{args.bib}")
    return _check(path, args, checks, transport, str(path))


def _check(path: Path, args, checks: set[str], transport: Transport | None, source: str) -> int:
    try:
        refs, extra = load(path, need_refs="refs" in checks)
    except OSError as e:
        print(f"paper-proof: cannot read {path}: {e.strerror or e}", file=sys.stderr)
        return 2
    except (BibError, InputError) as e:
        print(f"paper-proof: {path}: {e}", file=sys.stderr)
        return 2
    if "numbers" in checks and extra.texts:
        extra.findings = check_numbers(extra.texts)
    if "refs" not in checks:
        refs, extra.undefined, extra.uncited = [], [], []
        extra.refs_checked = False
    if args.only:
        refs = [r for r in refs if r.key in set(args.only)]
    if not refs:
        transport = ReplayTransport({})  # nothing to look up: make sure nothing is
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
    if args.format == "json":
        print(report.to_json(verdicts, dups, source, extra))
    elif args.format == "md":
        print(report.markdown(verdicts, dups, source, extra))
    else:
        print(report.text(verdicts, dups, source, extra, color=report.use_color()))
    return 1 if failed(args.fail_on, verdicts, extra) else 0


def failed(level: str, verdicts: list[Verdict], extra: report.Extra) -> bool:
    if level == "never":
        return False
    severities = {"error"} if level == "not-found" else {"error", "warning"}
    return any(v.status in FAIL_LEVELS[level] for v in verdicts) or bool(extra.undefined) or any(f.severity in severities for f in extra.findings)


class InputError(ValueError):
    pass


def load(path: Path, need_refs: bool = True) -> tuple[list[Reference], report.Extra]:
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
        extra.texts = proj.texts
        if not proj.references and need_refs:
            raise InputError(
                "no bibliography found: no \\bibliography{...} or \\addbibresource{...} with an existing .bib file, "
                "no thebibliography environment, and no compiled .bbl next to the main file"
            )
        return proj.checked(), extra
    raise InputError("give a .bib, .bbl or .tex file, or a LaTeX project folder")


def main() -> None:
    sys.exit(run())
