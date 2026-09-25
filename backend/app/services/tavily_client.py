"""Server-side Tavily search client: retries, rate-limit handling, caching and de-duplication.

Never fabricates results: when Tavily is not configured, errors out, or returns nothing, the
returned `SearchOutcome.status` says so and `results` is empty.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from backend.app.config import get_settings
from backend.app.db.database import SearchCacheRecord, SessionLocal
from backend.app.schemas import SearchOutcome, SourceItem

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_semaphore: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().tavily_concurrency)
    return _semaphore


def normalize_url(url: str) -> str:
    """Canonical URL for de-duplication (drops tracking params, www., trailing slash, fragments)."""
    p = urlparse(url.strip())
    host = p.netloc.lower().removeprefix("www.").removeprefix("m.")
    query = ""
    if "youtube.com" in host:
        q = parse_qs(p.query)
        keep = {k: v for k, v in q.items() if k in {"v", "list"}}
        query = urlencode(keep, doseq=True)
    return urlunparse(("https", host, p.path.rstrip("/"), "", query, ""))


def dedupe(items: list[SourceItem]) -> list[SourceItem]:
    seen: set[str] = set()
    out: list[SourceItem] = []
    for it in items:
        key = normalize_url(it.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _cache_key(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _cache_get(key: str, ttl_hours: int) -> tuple[dict, datetime] | None:
    with SessionLocal() as db:
        rec = db.get(SearchCacheRecord, key)
        if rec is None:
            return None
        retrieved = rec.retrieved_at if rec.retrieved_at.tzinfo else rec.retrieved_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - retrieved > timedelta(hours=ttl_hours):
            return None
        return rec.response_json, retrieved


def _cache_put(key: str, query: str, params: dict, response: dict, retrieved_at: datetime) -> None:
    with SessionLocal() as db:
        db.merge(SearchCacheRecord(key=key, query=query, params_json=params, response_json=response, retrieved_at=retrieved_at))
        db.commit()


def _to_outcome(query: str, data: dict, retrieved_at: datetime, cached: bool) -> SearchOutcome:
    results: list[SourceItem] = []
    for r in data.get("results", []) or []:
        url, title = (r.get("url") or "").strip(), (r.get("title") or "").strip()
        if not url.startswith("http") or not title:
            continue
        results.append(SourceItem(
            title=title, url=url, snippet=(r.get("content") or "").strip()[:1200],
            domain=urlparse(url).netloc.lower().removeprefix("www."),
            published_date=r.get("published_date"), retrieved_at=retrieved_at,
            score=r.get("score"), query=query,
        ))
    results = dedupe(results)
    answer = (data.get("answer") or "").strip() or None
    return SearchOutcome(
        query=query, status="ok" if results else "empty",
        message=None if results else "Tavily returned no results for this query.",
        results=results, answer=answer, retrieved_at=retrieved_at, cached=cached,
    )


async def tavily_search(
    query: str,
    *,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    topic: str = "general",
    search_depth: str = "basic",
    include_answer: bool = False,
    time_range: str | None = None,
    use_cache: bool = True,
    client: httpx.AsyncClient | None = None,
) -> SearchOutcome:
    """Tool entrypoint: one Tavily search with retries/backoff, caching and URL de-duplication."""
    settings = get_settings()
    if not settings.tavily_configured:
        return SearchOutcome(query=query, status="not_configured",
                             message="TAVILY_API_KEY is not set on the server, so live web data is unavailable.")

    payload: dict[str, Any] = {"query": query, "max_results": max_results, "topic": topic,
                               "search_depth": search_depth, "include_answer": include_answer}
    if include_domains:
        payload["include_domains"] = include_domains
    if time_range:
        payload["time_range"] = time_range
    key = _cache_key(payload)

    if use_cache:
        hit = await asyncio.to_thread(_cache_get, key, settings.tavily_cache_ttl_hours)
        if hit:
            return _to_outcome(query, hit[0], hit[1], cached=True)

    headers = {"Authorization": f"Bearer {settings.tavily_api_key}", "Content-Type": "application/json"}
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.tavily_timeout_s)
    last_error = "unknown error"
    try:
        async with _sem():
            for attempt in range(settings.tavily_max_retries + 1):
                try:
                    resp = await client.post(TAVILY_URL, json=payload, headers=headers)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = f"network error: {type(exc).__name__}"
                    logger.warning("Tavily %s (attempt %d) for %r", last_error, attempt + 1, query)
                else:
                    if resp.status_code == 200:
                        data = resp.json()
                        retrieved_at = datetime.now(timezone.utc)
                        await asyncio.to_thread(_cache_put, key, query, payload, data, retrieved_at)
                        return _to_outcome(query, data, retrieved_at, cached=False)
                    if resp.status_code in (401, 403):
                        return SearchOutcome(query=query, status="error",
                                             message="Tavily rejected the API key (HTTP %d). Check TAVILY_API_KEY." % resp.status_code)
                    if resp.status_code == 432 or resp.status_code == 433:
                        return SearchOutcome(query=query, status="error",
                                             message=f"Tavily plan/usage limit reached (HTTP {resp.status_code}).")
                    if resp.status_code not in RETRYABLE_STATUS:
                        detail = resp.text[:200]
                        return SearchOutcome(query=query, status="error", message=f"Tavily error HTTP {resp.status_code}: {detail}")
                    last_error = f"HTTP {resp.status_code}"
                    logger.warning("Tavily %s (attempt %d) for %r", last_error, attempt + 1, query)
                    if resp.status_code == 429 and resp.headers.get("retry-after", "").isdigit():
                        await asyncio.sleep(min(float(resp.headers["retry-after"]), 30.0))
                        continue
                if attempt < settings.tavily_max_retries:
                    await asyncio.sleep(min(8.0, 2 ** attempt) + random.uniform(0, 0.5))
    finally:
        if owns_client:
            await client.aclose()
    return SearchOutcome(query=query, status="error",
                         message=f"Tavily search failed after {settings.tavily_max_retries + 1} attempts ({last_error}).")
