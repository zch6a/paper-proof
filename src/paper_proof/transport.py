"""How requests reach the bibliographic databases: over HTTP (politely, cached on disk), or, in tests, from recorded
answers. The checks only ever see `Transport.get`, so the same code runs online, from the cache, or offline in tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from . import __version__

# Requests carry the tool's name and nothing about the user. Crossref gives better service to requests with a
# contact address; it is used only when the user sets PAPER_PROOF_MAILTO themselves.
USER_AGENT = f"paper-proof/{__version__} (+https://github.com/zch6a/paper-proof)"

# Seconds between two requests to the same host: what each service asks for (arXiv: one request every 3 s).
MIN_INTERVAL = {
    "export.arxiv.org": 3.0,
    "api.semanticscholar.org": 1.1,
    "api.crossref.org": 0.1,
    "api.openalex.org": 0.12,
}


@dataclass
class Response:
    status: int
    text: str

    def json(self):
        return json.loads(self.text)


class TransportError(RuntimeError):
    """The service did not answer (network down, timeout, repeated 5xx or 429): the result is unknown, not 'missing'."""


class Transport(Protocol):
    def get(self, url: str) -> Response: ...


class HttpTransport:
    """urllib with a per-host pause, retries with backoff on 429 and 5xx, and a timeout."""

    def __init__(self, timeout: float = 20.0, retries: int = 3, mailto: str | None = None):
        self.timeout = timeout
        self.retries = retries
        self.mailto = mailto if mailto is not None else os.environ.get("PAPER_PROOF_MAILTO", "")
        self.openalex_key = os.environ.get("OPENALEX_API_KEY", "")
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        # A host that failed this many times in a row is left alone for the rest of the run (Semantic Scholar
        # without a key often answers 429 for minutes): its references become "unknown" quickly, not slowly.
        self.max_failures = 3
        self._failures: dict[str, int] = {}

    def _pace(self, host: str) -> None:
        # Reserve this request's slot under the lock, wait outside it: a pause for arXiv must not hold up OpenAlex.
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._last.get(host, 0.0) + MIN_INTERVAL.get(host, 0.2))
            self._last[host] = slot
        if slot > now:
            time.sleep(slot - now)

    def get(self, url: str) -> Response:
        host = urlsplit(url).hostname or ""
        if self._failures.get(host, 0) >= self.max_failures:
            raise TransportError(f"{host}: not asked again after {self.max_failures} failures in a row")
        try:
            r = self._get(url, host)
        except TransportError:
            with self._lock:
                self._failures[host] = self._failures.get(host, 0) + 1
            raise
        with self._lock:
            self._failures[host] = 0
        return r

    def _get(self, url: str, host: str) -> Response:
        if self.mailto and host == "api.crossref.org":
            url += ("&" if "?" in url else "?") + "mailto=" + urllib.request.quote(self.mailto)
        # OpenAlex answers without a key, within a small daily budget; a free key (set by the user) raises it tenfold.
        if self.openalex_key and host == "api.openalex.org":
            url += ("&" if "?" in url else "?") + "api_key=" + urllib.request.quote(self.openalex_key)
        delay = 2.0
        last_error = ""
        for attempt in range(self.retries + 1):
            self._pace(host)
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml;q=0.9"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read().decode("utf-8", "replace")
                    # 202 is "accepted, not ready" (or a bot-check page): never an answer. Ask again, then give up as unknown.
                    if r.status == 202 and attempt < self.retries:
                        time.sleep(delay)
                        delay *= 2
                        last_error = "HTTP 202 (busy)"
                        continue
                    if r.status == 202:
                        raise TransportError(f"{host}: busy (HTTP 202)")
                    return Response(r.status, body)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return Response(404, "")
                if e.code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {e.code}"
                    if attempt < self.retries:
                        retry_after = e.headers.get("Retry-After", "") if e.headers else ""
                        time.sleep(min(float(retry_after), 60.0) if retry_after.isdigit() else delay)
                        delay *= 2
                        continue
                    break  # busy or broken: the answer is unknown, never "no such work"
                return Response(e.code, e.read().decode("utf-8", "replace") if e.fp else "")
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last_error = str(getattr(e, "reason", e))
                if attempt < self.retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
        raise TransportError(f"{host}: {last_error or 'no answer'}")


class CachedTransport:
    """Answers kept on disk (successful ones and 404s), so a second run is instant and asks nobody again."""

    def __init__(self, inner: Transport, directory: Path, max_age_days: float = 30.0):
        self.inner = inner
        self.dir = directory
        self.max_age = max_age_days * 86400

    def _path(self, url: str) -> Path:
        return self.dir / hashlib.sha256(url.encode()).hexdigest()[:40]

    def get(self, url: str) -> Response:
        p = self._path(url)
        try:
            if time.time() - p.stat().st_mtime < self.max_age:
                data = json.loads(p.read_text(encoding="utf-8"))
                return Response(data["status"], data["text"])
        except (OSError, ValueError, KeyError):
            pass
        r = self.inner.get(url)
        if r.status in (200, 404):
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps({"url": url, "status": r.status, "text": r.text}), encoding="utf-8")
            os.replace(tmp, p)
        return r


class ReplayTransport:
    """Recorded answers by URL, for tests. A URL with no recording is an error: no test can reach the network."""

    def __init__(self, answers: dict[str, tuple[int, str]]):
        self.answers = answers
        self.requested: list[str] = []

    def get(self, url: str) -> Response:
        self.requested.append(url)
        if url not in self.answers:
            raise AssertionError(f"no recorded answer for {url}")
        status, text = self.answers[url]
        if status < 0:
            raise TransportError("recorded: no answer")
        return Response(status, text)


def default_cache_dir() -> Path:
    base = os.environ.get("PAPER_PROOF_CACHE")
    if base:
        return Path(base)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "paper-proof" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "paper-proof"
