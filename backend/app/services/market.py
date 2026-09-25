"""Live market intelligence for a target role, via Tavily only.

Output keeps two things strictly apart:
  * observed_sources / skill_mentions — what the retrieved pages say (title, URL, snippet,
    retrieval date) and a deterministic count of taxonomy skills mentioned across those snippets.
  * ai_interpretation — Tavily's LLM-generated answer text, labelled as AI interpretation.
Synthetic training data is never used here.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from backend.app.knowledge import get_kb
from backend.app.nlp.skills import extract_skills
from backend.app.schemas import MarketIntelligence, SearchOutcome, SkillMention
from backend.app.services.tavily_client import dedupe, tavily_search


def market_queries(role: str, year: int) -> list[dict]:
    return [
        {"query": f"most in-demand skills for {role} jobs in {year}", "topic": "general", "include_answer": True},
        {"query": f"{role} job market trends {year}", "topic": "news", "time_range": "year", "include_answer": True},
        {"query": f"emerging tools and technologies {role}s should learn in {year}", "topic": "general", "include_answer": True},
    ]


async def get_market_intelligence(role: str, candidate_skills: set[str] | None = None) -> MarketIntelligence:
    """Tool entrypoint."""
    kb = get_kb()
    candidate_skills = candidate_skills or set()
    specs = market_queries(role, datetime.now(timezone.utc).year)
    outcomes: list[SearchOutcome] = await asyncio.gather(*(
        tavily_search(s["query"], max_results=6, topic=s["topic"], include_answer=s["include_answer"],
                      time_range=s.get("time_range")) for s in specs
    ))

    if all(o.status == "not_configured" for o in outcomes):
        return MarketIntelligence(role=role, status="not_configured", message=outcomes[0].message, queries=outcomes)

    sources = dedupe([r for o in outcomes for r in o.results])
    mentions: dict[str, set[str]] = defaultdict(set)
    for src in sources:
        for skill in extract_skills(f"{src.title}\n{src.snippet}", use_ner=False).skills:
            if kb.skills[skill].category != "Soft Skills":
                mentions[skill].add(src.url)
    skill_mentions = sorted(
        (SkillMention(skill=s, category=kb.skills[s].category, source_count=len(urls), candidate_has=s in candidate_skills,
                      source_urls=sorted(urls)) for s, urls in mentions.items()),
        key=lambda m: (-m.source_count, m.skill),
    )[:30]

    interpretation = [
        {"query": o.query, "text": o.answer, "generated_by": "Tavily answer (LLM-generated summary of the retrieved pages)",
         "based_on_urls": [r.url for r in o.results], "retrieved_at": o.retrieved_at.isoformat() if o.retrieved_at else None}
        for o in outcomes if o.answer
    ]

    errors = [o for o in outcomes if o.status == "error"]
    if not sources:
        status = "error" if errors else "empty"
        message = ("All market searches failed: " + "; ".join(o.message or "" for o in errors)) if errors \
            else "Tavily returned no usable sources for this role. No market insights are shown rather than inventing any."
    else:
        status = "partial" if errors else "ok"
        message = ("Some searches failed: " + "; ".join(o.message or "" for o in errors)) if errors else None

    retrieved = [o.retrieved_at for o in outcomes if o.retrieved_at]
    return MarketIntelligence(
        role=role, status=status, message=message, retrieved_at=max(retrieved) if retrieved else None,
        observed_sources=sources, skill_mentions=skill_mentions, ai_interpretation=interpretation, queries=outcomes,
    )
