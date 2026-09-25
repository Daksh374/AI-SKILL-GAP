"""Learning-resource discovery via Tavily (YouTube + Coursera). No YouTube Data API.

Only fields present in Tavily's result metadata are returned. Duration/thumbnail/channel are not
reliably available from Tavily for YouTube watch URLs, so they are left empty rather than guessed.
A Coursera item is flagged `free_mentioned` only when the retrieved snippet/title literally
mentions free access, and the matching text is returned as evidence.

Domain restriction uses Tavily's `include_domains` (the API-level equivalent of `site:`). Putting a
`site:` operator in the query text *as well* was observed to break relevance (unrelated popular
videos came back), so queries are plain text. Every result must also mention the skill in its
title/snippet, otherwise it is dropped rather than shown as a resource; results naming the skill
in the title are ranked first.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

from backend.app.knowledge import get_kb
from backend.app.nlp.skills import extract_skills
from backend.app.schemas import LearningResource, SearchOutcome, SkillResources, SourceItem
from backend.app.services.tavily_client import dedupe, tavily_search

MAX_PER_SKILL = 3
_YT_SUFFIX = re.compile(r"\s*[-|]\s*YouTube\s*$", re.IGNORECASE)
_CO_SUFFIX = re.compile(r"\s*[|-]\s*Coursera\s*$", re.IGNORECASE)
_TOKEN = r"[A-Z&][\w&'()-]*(?:\.[A-Za-z]+)*"  # allows "DeepLearning.AI", stops at sentence-ending "."
_OFFERED_BY = re.compile(rf"(?i:offered by|provided by|created by)\s+({_TOKEN}(?:\s+(?:of\s+)?{_TOKEN}){{0,6}})")
_FREE = re.compile(r"[^.]{0,60}\b(?:enroll for free|free(?![\s-]+trial)|audit (?:this|the) course)\b[^.]{0,60}", re.IGNORECASE)
COURSERA_PATHS = {"learn": "Course", "specializations": "Specialization", "professional-certificates": "Professional Certificate",
                  "projects": "Guided Project"}


def search_term(skill: str) -> str:
    """Unambiguous search phrase for a skill ("R" -> "R programming", "Go" -> "Golang")."""
    s = get_kb().skills.get(skill)
    if s is not None and s.ambiguous:
        longer = [a for a in s.aliases if len(a) > 3]
        if longer:
            return longer[0]
    return skill


def _mentions(skill: str, text: str) -> bool:
    return skill.lower() in text.lower() or skill in extract_skills(text, use_ner=False).skills


def mentions_skill(skill: str, item: SourceItem) -> bool:
    """True if the result's title/snippet mentions the skill (canonical name or any taxonomy alias)."""
    return _mentions(skill, f"{item.title}\n{item.snippet}")


def rank_by_relevance(skill: str, items: list[SourceItem]) -> list[SourceItem]:
    """Keep only results mentioning the skill; those naming it in the title come first (stable order)."""
    relevant = [r for r in items if mentions_skill(skill, r)]
    return sorted(relevant, key=lambda r: not _mentions(skill, r.title))


def _youtube_type(url: str) -> str | None:
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be" and p.path.strip("/"):
        return "Video"
    if host.endswith("youtube.com"):
        if p.path == "/watch" and "v=" in p.query:
            return "Video"
        if p.path == "/playlist" and "list=" in p.query:
            return "Playlist"
    return None


def _coursera_type(url: str) -> str | None:
    p = urlparse(url)
    if not p.netloc.lower().removeprefix("www.").endswith("coursera.org"):
        return None
    first = p.path.strip("/").split("/")[0] if p.path.strip("/") else ""
    return COURSERA_PATHS.get(first)


def _yt_resources(skill: str, outcome: SearchOutcome) -> list[LearningResource]:
    out: list[LearningResource] = []
    for r in rank_by_relevance(skill, dedupe(outcome.results)):
        kind = _youtube_type(r.url)
        if not kind:
            continue
        out.append(LearningResource(
            platform="YouTube", skill=skill, title=_YT_SUFFIX.sub("", r.title), url=r.url, snippet=r.snippet[:300],
            channel=None, resource_type=kind, retrieved_at=r.retrieved_at,
        ))
    return out[:MAX_PER_SKILL]


def _coursera_resources(skill: str, outcome: SearchOutcome) -> list[LearningResource]:
    out: list[LearningResource] = []
    for r in rank_by_relevance(skill, dedupe(outcome.results)):
        kind = _coursera_type(r.url)
        if not kind:
            continue
        text = f"{r.title}. {r.snippet}"
        provider = _OFFERED_BY.search(text)
        free = _FREE.search(text)
        out.append(LearningResource(
            platform="Coursera", skill=skill, title=_CO_SUFFIX.sub("", r.title), url=r.url, snippet=r.snippet[:300],
            provider=provider.group(1).strip(" .,") if provider else None, resource_type=kind,
            free_mentioned=bool(free), free_evidence=free.group(0).strip() if free else None, retrieved_at=r.retrieved_at,
        ))
    return out[:MAX_PER_SKILL]


async def find_youtube_resources(skill: str) -> tuple[list[LearningResource], SearchOutcome]:
    """Tool entrypoint: Tavily search restricted to YouTube for a skill tutorial."""
    outcome = await tavily_search(f"{search_term(skill)} tutorial for beginners", max_results=8,
                                  include_domains=["youtube.com"])
    return _yt_resources(skill, outcome), outcome


async def find_coursera_resources(skill: str) -> tuple[list[LearningResource], SearchOutcome]:
    """Tool entrypoint: Tavily search restricted to Coursera for a skill course."""
    outcome = await tavily_search(f"{search_term(skill)} course", max_results=8, include_domains=["coursera.org"])
    return _coursera_resources(skill, outcome), outcome


def _status(items: list[LearningResource], outcome: SearchOutcome) -> str:
    if outcome.status in {"not_configured", "error"}:
        return outcome.status
    return "ok" if items else "empty"


async def find_resources_for_skill(skill: str) -> SkillResources:
    (yt, yt_out), (co, co_out) = await asyncio.gather(find_youtube_resources(skill), find_coursera_resources(skill))
    msgs = [m for m in (yt_out.message, co_out.message) if m]
    if yt_out.status == "ok" and not yt:
        msgs.append("YouTube search returned pages, but none were relevant video/playlist URLs.")
    if co_out.status == "ok" and not co:
        msgs.append("Coursera search returned pages, but none were relevant course/specialization URLs.")
    return SkillResources(skill=skill, youtube=yt, coursera=co, youtube_status=_status(yt, yt_out),
                          coursera_status=_status(co, co_out), message=" ".join(dict.fromkeys(msgs)) or None)


async def find_resources(skills: list[str]) -> dict[str, SkillResources]:
    results = await asyncio.gather(*(find_resources_for_skill(s) for s in skills))
    return {r.skill: r for r in results}
