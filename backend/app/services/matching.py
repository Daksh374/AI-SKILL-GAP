"""Deterministic role-skill matching (no ML). Shared by career ranking and the skill-gap engine.

Credit a candidate earns for one role skill:
  1.00  exact  — candidate has the skill
  0.75  implied — candidate has a specialization of it (has PyTorch -> "Deep Learning")
  0.50  related — candidate has a strongly related skill (relationship strength >= 0.7)
  0.40  sibling — candidate has another specialization of the same broader concept (Power BI vs Tableau)
  0.35  related — candidate has a weakly related skill (strength < 0.7)
  0.00  missing
Role match score = 0.8 * weighted required coverage + 0.2 * optional coverage.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.knowledge import KnowledgeBase, Role
from backend.app.schemas import RoleMatchDetail

REQUIRED_SHARE = 0.8
OPTIONAL_SHARE = 0.2


@dataclass
class Credit:
    credit: float
    kind: str  # exact | implied | related | sibling | missing
    evidence: list[str]


def skill_credit(skill: str, candidate: set[str], kb: KnowledgeBase) -> Credit:
    if skill in candidate:
        return Credit(1.0, "exact", [skill])
    implied = sorted(kb.specializations.get(skill, set()) & candidate)
    if implied:
        return Credit(0.75, "implied", implied)
    related = {s: w for s, w in kb.related.get(skill, {}).items() if s in candidate}
    strong = sorted(s for s, w in related.items() if w >= 0.7)
    if strong:
        return Credit(0.5, "related", strong)
    siblings = sorted({sib for g in kb.generalizations.get(skill, set()) for sib in kb.specializations.get(g, set())} & candidate)
    if siblings:
        return Credit(0.4, "sibling", siblings)
    if related:
        return Credit(0.35, "related", sorted(related))
    return Credit(0.0, "missing", [])


def role_match(role: Role, candidate: set[str], kb: KnowledgeBase) -> RoleMatchDetail:
    total_w = sum(role.required.values())
    earned = 0.0
    matched, partial, missing = [], [], []
    for skill, w in sorted(role.required.items(), key=lambda kv: (-kv[1], kv[0])):
        c = skill_credit(skill, candidate, kb)
        earned += w * c.credit
        (matched if c.credit == 1.0 else partial if c.credit > 0 else missing).append(skill)
    req_cov = earned / total_w if total_w else 0.0
    opt_hits = [s for s in role.optional if s in candidate]
    opt_cov = sum(skill_credit(s, candidate, kb).credit for s in role.optional) / len(role.optional) if role.optional else 0.0
    return RoleMatchDetail(
        score=round(REQUIRED_SHARE * req_cov + OPTIONAL_SHARE * opt_cov, 4),
        required_coverage=round(req_cov, 4),
        optional_coverage=round(opt_cov, 4),
        matched_required=matched,
        partial_required=partial,
        missing_required=missing,
        matched_optional=opt_hits,
    )
