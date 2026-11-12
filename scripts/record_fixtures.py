"""Record the databases' real answers for the test bibliography, so the tests can replay them without a network.

    uv run python scripts/record_fixtures.py        (asks Crossref, arXiv, Semantic Scholar and OpenAlex once)

The answers are public metadata about published papers; they are stored as returned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from paper_proof.bib import parse_bib  # noqa: E402
from paper_proof.check import check_reference, reference_from_bib  # noqa: E402
from paper_proof.transport import HttpTransport, Response, TransportError  # noqa: E402


class Recording:
    def __init__(self, inner):
        self.inner = inner
        self.answers: dict[str, list] = {}

    def get(self, url: str) -> Response:
        try:
            r = self.inner.get(url)
        except TransportError:
            self.answers[url] = [-1, ""]
            raise
        self.answers[url] = [r.status, r.text]
        return r


def main() -> None:
    bib = ROOT / "tests" / "fixtures" / "references.bib"
    rec = Recording(HttpTransport())
    for e in parse_bib(bib.read_text(encoding="utf-8")):
        v = check_reference(reference_from_bib(e), rec)
        print(f"{v.key:24} {v.status:10} {'; '.join(v.problems + v.notes)[:120]}")
    out = ROOT / "tests" / "fixtures" / "answers.json"
    out.write_text(json.dumps(rec.answers, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(rec.answers)} answers -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
