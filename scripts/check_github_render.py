"""The Markdown report rendered by GitHub itself (gh api markdown, GFM): tables render, and a hostile title makes no
link, image, mention or HTML. Needs gh, signed in. Writes report.md and report.html into OUT_DIR.

    uv run python scripts/check_github_render.py OUT_DIR
"""

import contextlib
import io
import subprocess
import sys
from pathlib import Path

from paper_proof.cli import run
from paper_proof.transport import ReplayTransport

HOSTILE = "See https://evil.example and www.evil.example [click](https://x.example) <img src=x onerror=alert(1)> @octocat **bold** `code` | pipe"


class Down(dict):
    """Every database: no answer (nothing is sent anywhere)."""

    def __contains__(self, url):
        return True

    def __getitem__(self, url):
        return (-1, "")


out = Path(sys.argv[1])
out.mkdir(exist_ok=True)
bib = out / "hostile.bib"
bib.write_text(f"@article{{evil, title={{{HOSTILE}}}, author={{Doe, J.}}, doi={{10.1/x}}, year={{2020}}}}\n", encoding="utf-8")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    run([str(bib), "--format", "md", "--fail-on", "never"], ReplayTransport(Down()))
example = subprocess.run(
    ["uv", "run", "paper-proof", "examples/paper", "--offline", "--format", "md"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    cwd=Path(__file__).resolve().parent.parent,
).stdout
text = buf.getvalue() + "\n\n" + example
(out / "report.md").write_text(text, encoding="utf-8")
html = subprocess.run(["gh", "api", "markdown", "-f", f"text={text}", "-f", "mode=gfm"], capture_output=True, text=True, encoding="utf-8").stdout
(out / "report.html").write_text(html, encoding="utf-8")
checks = {
    "tables render": html.count("<table") >= 2,  # the hostile reference, the example's findings
    "no links": "<a href" not in html,
    "no images": "<img" not in html,
    "no mentions": "user-mention" not in html,
}
for name, ok in checks.items():
    print(("ok  " if ok else "FAIL"), name)
sys.exit(0 if all(checks.values()) else 1)
