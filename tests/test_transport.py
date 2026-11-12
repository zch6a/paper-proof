"""The HTTP transport, without a network: urllib is replaced by a stub."""

import io
import urllib.error

import pytest

from paper_proof import transport as T


class Stub:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, req, timeout):
        self.calls.append(req.full_url)
        outcome = self.outcomes.pop(0) if self.outcomes else self.outcomes_last
        if isinstance(outcome, Exception):
            raise outcome
        status, body = outcome

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        r = R(body.encode())
        r.status = status
        return r


def http_error(code):
    return urllib.error.HTTPError("https://x", code, "err", {}, None)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(T.time, "sleep", lambda s: None)


def test_retries_then_answers(monkeypatch):
    stub = Stub([http_error(503), (200, '{"ok": 1}')])
    monkeypatch.setattr(T.urllib.request, "urlopen", stub)
    r = T.HttpTransport(retries=2).get("https://api.crossref.org/works?q=x")
    assert r.status == 200 and r.json() == {"ok": 1} and len(stub.calls) == 2


def test_404_is_an_answer_and_repeated_429_is_unknown(monkeypatch):
    monkeypatch.setattr(T.urllib.request, "urlopen", Stub([http_error(404)]))
    assert T.HttpTransport().get("https://api.crossref.org/works/10.1/x").status == 404
    monkeypatch.setattr(T.urllib.request, "urlopen", Stub([http_error(429)] * 3))
    with pytest.raises(T.TransportError):
        T.HttpTransport(retries=2).get("https://api.semanticscholar.org/x")


def test_a_host_that_keeps_failing_is_left_alone(monkeypatch):
    stub = Stub([http_error(429)] * 100)
    monkeypatch.setattr(T.urllib.request, "urlopen", stub)
    t = T.HttpTransport(retries=0)
    for _ in range(5):
        with pytest.raises(T.TransportError):
            t.get("https://api.semanticscholar.org/x")
    assert len(stub.calls) == 3  # the 4th and 5th were not sent
    # other hosts are still asked
    monkeypatch.setattr(T.urllib.request, "urlopen", Stub([(200, "{}")]))
    assert t.get("https://api.openalex.org/works").status == 200


def test_keys_and_contact_only_when_set(monkeypatch):
    stub = Stub([(200, "{}"), (200, "{}")])
    monkeypatch.setattr(T.urllib.request, "urlopen", stub)
    monkeypatch.setenv("OPENALEX_API_KEY", "k1")
    t = T.HttpTransport(mailto="a@b.c")
    t.get("https://api.crossref.org/works?x=1")
    t.get("https://api.openalex.org/works?x=1")
    assert stub.calls == ["https://api.crossref.org/works?x=1&mailto=a%40b.c", "https://api.openalex.org/works?x=1&api_key=k1"]
    monkeypatch.delenv("OPENALEX_API_KEY")
    monkeypatch.delenv("PAPER_PROOF_MAILTO", raising=False)
    stub2 = Stub([(200, "{}")])
    monkeypatch.setattr(T.urllib.request, "urlopen", stub2)
    T.HttpTransport().get("https://api.openalex.org/works?x=1")
    assert stub2.calls == ["https://api.openalex.org/works?x=1"]


def test_the_cache_answers_the_second_time(tmp_path):
    class Count:
        n = 0

        def get(self, url):
            Count.n += 1
            return T.Response(200, '{"a": 1}')

    c = T.CachedTransport(Count(), tmp_path)
    assert c.get("https://a/1").json() == {"a": 1} and c.get("https://a/1").json() == {"a": 1}
    assert Count.n == 1
