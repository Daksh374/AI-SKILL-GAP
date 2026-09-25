"""Deterministic skill-gap engine. No LLM is involved: every value derives from data/ + code.

Priority score for a missing / partial skill (all factors in [0, 1]):
    0.35 * role_weight      role requirement weight / 3  (optional skills = 0.2)
  + 0.25 * jd_demand        share of the role's synthetic job descriptions listing the skill
  + 0.20 * importance       taxonomy importance / 3
  + 0.20 * foundation       0.5 * min(1, unblocks / 3) + 0.5 / (1 + prerequisite_depth)
                            unblocks = other gap skills that (transitively) require this one
Partial skills are discounted by (1 - 0.5 * credit).
High >= 0.60, Medium >= 0.40, else Low.
"""
from __future__ import annotations

from backend.app.knowledge import KnowledgeBase, get_kb
from backend.app.schemas import CandidateProfile, GapSkill, SkillGapResult
from backend.app.services.matching import skill_credit

W_ROLE, W_DEMAND, W_IMPORTANCE, W_FOUNDATION = 0.35, 0.25, 0.20, 0.20
HIGH, MEDIUM = 0.60, 0.40
METHOD = (
    "Deterministic: matched = exact skill; partial = credit via implied/related/sibling skills from "
    "skill_relationships.csv; priority = 0.35·role weight + 0.25·synthetic-JD demand + 0.20·taxonomy importance "
    "+ 0.20·foundation (prerequisite depth & how many other gaps it unblocks). High ≥ 0.60, Medium ≥ 0.40."
)


class UnknownRoleError(ValueError):
    pass


def _bucket(score: float) -> str:
    return "High" if score >= HIGH else "Medium" if score >= MEDIUM else "Low"


def calculate_skill_gap(profile: CandidateProfile, role_name: str, kb: KnowledgeBase | None = None) -> SkillGapResult:
    """Tool entrypoint."""
    kb = kb or get_kb()
    role = kb.roles.get(role_name)
    if role is None:
        raise UnknownRoleError(f"Unknown role '{role_name}'. Valid roles: {', '.join(kb.role_names)}")
    candidate = set(profile.all_skill_names)
    conf = {s.name: s.confidence for s in profile.technical_skills + profile.soft_skills}

    requirements: list[tuple[str, str, int]] = [(s, "required", w) for s, w in role.required.items()]
    requirements += [(s, "optional", 1) for s in role.optional if s not in role.required]

    items: list[GapSkill] = []
    for skill, req, weight in requirements:
        c = skill_credit(skill, candidate, kb)
        status = "matched" if c.credit == 1.0 else "partial" if c.credit > 0 else "missing"
        items.append(GapSkill(
            name=skill, category=kb.skills[skill].category, status=status, requirement=req, role_weight=weight,
            evidence=c.evidence if status == "partial" else [], credit=c.credit, candidate_confidence=conf.get(skill),
        ))

    gap_names = {i.name for i in items if i.status != "matched"}
    depth_memo: dict[str, int] = {}
    demand = kb.jd_demand.get(role_name, {})
    for item in items:
        if item.status == "matched":
            continue
        unblocks = sum(1 for other in gap_names if other != item.name and item.name in kb.all_prerequisites(other))
        depth = kb.prerequisite_depth(item.name, depth_memo)
        factors = {
            "role_weight": round(item.role_weight / 3 if item.requirement == "required" else 0.2, 3),
            "jd_demand": round(min(1.0, demand.get(item.name, 0.0)), 3),
            "importance": round(kb.skills[item.name].importance / 3, 3),
            "foundation": round(0.5 * min(1.0, unblocks / 3) + 0.5 / (1 + depth), 3),
        }
        score = (W_ROLE * factors["role_weight"] + W_DEMAND * factors["jd_demand"]
                 + W_IMPORTANCE * factors["importance"] + W_FOUNDATION * factors["foundation"])
        if item.status == "partial":
            score *= 1 - 0.5 * item.credit
            factors["partial_discount"] = round(1 - 0.5 * item.credit, 3)
        factors["unblocks"] = float(unblocks)
        factors["prerequisite_depth"] = float(depth)
        item.priority_score = round(score, 4)
        item.priority = _bucket(score)
        item.priority_factors = factors

    required = [i for i in items if i.requirement == "required"]
    total_w = sum(i.role_weight for i in required)
    readiness = sum(i.role_weight * i.credit for i in required) / total_w if total_w else 0.0

    def order(i: GapSkill) -> tuple:
        return (i.requirement != "required", -(i.priority_score or 0), -i.role_weight, i.name)

    matched = sorted((i for i in items if i.status == "matched"), key=lambda i: (i.requirement != "required", -i.role_weight, i.name))
    partial = sorted((i for i in items if i.status == "partial"), key=order)
    missing = sorted((i for i in items if i.status == "missing"), key=order)
    gaps = partial + missing
    summary = {
        "required_total": len(required),
        "required_matched": sum(1 for i in required if i.status == "matched"),
        "required_partial": sum(1 for i in required if i.status == "partial"),
        "required_missing": sum(1 for i in required if i.status == "missing"),
        "optional_total": len(items) - len(required),
        "optional_matched": sum(1 for i in items if i.requirement == "optional" and i.status == "matched"),
        "high_priority": sum(1 for i in gaps if i.priority == "High"),
        "medium_priority": sum(1 for i in gaps if i.priority == "Medium"),
        "low_priority": sum(1 for i in gaps if i.priority == "Low"),
    }
    return SkillGapResult(role=role_name, readiness_score=round(readiness, 4), matched=matched, partial=partial,
                          missing=missing, summary=summary, method=METHOD)
