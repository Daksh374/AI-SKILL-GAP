"""Tavily client behaviour with a mocked HTTP transport (tests only — the app never simulates responses)."""
import asyncio

import httpx
import pytest

from backend.app.config import get_settings
from backend.app.services import resources as res_mod
from backend.app.services import tavily_client
from backend.app.services.tavily_client import normalize_url, tavily_search


@pytest.fixture
def tavily_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("TAVILY_MAX_RETRIES", "2")
    get_settings.cache_clear()
    tavily_client._semaphore = None
    monkeypatch.setattr(tavily_client.asyncio, "sleep", _no_sleep)
    yield
    get_settings.cache_clear()


async def _no_sleep(*_a, **_k):
    return None


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


def test_not_configured_returns_status_without_results():
    get_settings.cache_clear()
    out = run(tavily_search("anything"))
    assert out.status == "not_configured" and out.results == []


def test_success_dedupes_and_records_retrieval(tavily_key):
    def handler(req):
        assert req.headers["authorization"] == "Bearer tvly-test"
        return httpx.Response(200, json={"results": [
            {"title": "A", "url": "https://www.example.com/a/?utm_source=x", "content": "alpha"},
            {"title": "A dup", "url": "https://example.com/a", "content": "alpha again"},
            {"title": "B", "url": "https://example.com/b", "content": "beta"},
            {"title": "", "url": "https://example.com/no-title", "content": "dropped"},
        ], "answer": "summary"})
    out = run(tavily_search("q-success", client=_client(handler), use_cache=False))
    assert out.status == "ok" and [r.title for r in out.results] == ["A", "B"]
    assert out.answer == "summary" and out.retrieved_at is not None
    assert all(r.retrieved_at == out.retrieved_at and r.query == "q-success" for r in out.results)


def test_retries_on_429_then_succeeds(tavily_key):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"results": [{"title": "ok", "url": "https://x.org", "content": ""}]})
    out = run(tavily_search("q-retry", client=_client(handler), use_cache=False))
    assert calls["n"] == 2 and out.status == "ok"


def test_gives_up_after_retries(tavily_key):
    def handler(req):
        raise httpx.ConnectTimeout("boom")
    out = run(tavily_search("q-timeout", client=_client(handler), use_cache=False))
    assert out.status == "error" and "3 attempts" in out.message and out.results == []


def test_auth_error_not_retried(tavily_key):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, json={"detail": "bad key"})
    out = run(tavily_search("q-auth", client=_client(handler), use_cache=False))
    assert calls["n"] == 1 and out.status == "error"


def test_empty_results(tavily_key):
    out = run(tavily_search("q-empty", client=_client(lambda r: httpx.Response(200, json={"results": []})), use_cache=False))
    assert out.status == "empty" and out.results == []


def test_cache_hit_avoids_network(tavily_key):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"results": [{"title": "c", "url": "https://c.org", "content": ""}]})
    first = run(tavily_search("q-cache-unique", client=_client(handler)))
    second = run(tavily_search("q-cache-unique", client=_client(handler)))
    assert calls["n"] == 1 and not first.cached and second.cached
    assert second.results[0].url == "https://c.org"


def test_normalize_url_keeps_youtube_video_id():
    assert normalize_url("https://www.youtube.com/watch?v=abc&t=10s") == "https://youtube.com/watch?v=abc"
    assert normalize_url("https://m.youtube.com/watch?v=abc") == "https://youtube.com/watch?v=abc"


def test_resource_filters_and_free_flag(tavily_key, monkeypatch):
    def handler(req):
        body = req.content.decode()
        if "youtube" in body:
            return httpx.Response(200, json={"results": [
                {"title": "Docker Tutorial - YouTube", "url": "https://www.youtube.com/watch?v=1", "content": "learn docker"},
                {"title": "Channel page", "url": "https://www.youtube.com/@somechannel", "content": ""},
                {"title": "Official Music Video", "url": "https://www.youtube.com/watch?v=2", "content": "a song"},
            ]})
        return httpx.Response(200, json={"results": [
            {"title": "Docker Basics | Coursera", "url": "https://www.coursera.org/learn/docker-basics",
             "content": "Offered by IBM. Enroll for free. Learn containers."},
            {"title": "Docker Deep Dive | Coursera", "url": "https://www.coursera.org/learn/containers", "content": "Paid course."},
            {"title": "Introduction to Ancient Egypt | Coursera", "url": "https://www.coursera.org/learn/egypt", "content": "History."},
            {"title": "What is Docker? | Coursera", "url": "https://www.coursera.org/articles/what-is-docker", "content": "article"},
        ]})

    real = tavily_client.tavily_search

    async def patched(query, **kw):
        kw["client"] = _client(handler)
        kw["use_cache"] = False
        return await real(query, **kw)
    monkeypatch.setattr(res_mod, "tavily_search", patched)

    out = run(res_mod.find_resources_for_skill("Docker"))
    assert [r.url for r in out.youtube] == ["https://www.youtube.com/watch?v=1"]
    assert out.youtube[0].title == "Docker Tutorial" and out.youtube[0].channel is None
    urls = [r.url for r in out.coursera]
    assert urls == ["https://www.coursera.org/learn/docker-basics", "https://www.coursera.org/learn/containers"]
    assert out.coursera[0].free_mentioned and "free" in out.coursera[0].free_evidence.lower()
    assert out.coursera[0].provider == "IBM"
    assert not out.coursera[1].free_mentioned


def test_search_term_disambiguates():
    assert res_mod.search_term("R") == "R programming"
    assert res_mod.search_term("Go") == "Golang"
    assert res_mod.search_term("Docker") == "Docker"


def test_free_trial_is_not_free():
    assert res_mod._FREE.search("Start your 7-day free trial today") is None
    assert res_mod._FREE.search("You can audit this course at no cost") is not None


def test_title_mentions_rank_first():
    from datetime import datetime, timezone
    from backend.app.schemas import SourceItem
    now = datetime.now(timezone.utc)
    mk = lambda t, sn: SourceItem(title=t, url=f"https://x.org/{t}", snippet=sn, domain="x.org", retrieved_at=now, query="q")
    items = [mk("Mastering C#", "also covers Docker"), mk("Intro to Docker", ""), mk("Egypt", "history")]
    assert [i.title for i in res_mod.rank_by_relevance("Docker", items)] == ["Intro to Docker", "Mastering C#"]
