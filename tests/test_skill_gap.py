import pytest

from backend.app.knowledge import get_kb
from backend.app.nlp.profile import build_profile
from backend.app.schemas import CandidateProfile, ExtractedSkill
from backend.app.services.matching import role_match, skill_credit
from backend.app.services.skill_gap import UnknownRoleError, calculate_skill_gap


def profile_with(*skills: str) -> CandidateProfile:
    kb = get_kb()
    return CandidateProfile(technical_skills=[
        ExtractedSkill(name=s, category=kb.skills[s].category, confidence=0.9, mentions=1, sections=["skills"], matched_forms=[s])
        for s in skills
    ])


def test_credit_rules():
    kb = get_kb()
    assert skill_credit("Python", {"Python"}, kb).credit == 1.0
    implied = skill_credit("Deep Learning", {"PyTorch"}, kb)
    assert implied.credit == 0.75 and implied.kind == "implied" and implied.evidence == ["PyTorch"]
    assert skill_credit("Kubernetes", set(), kb).credit == 0.0
    related = skill_credit("Tableau", {"Power BI"}, kb)
    assert 0 < related.credit < 1


def test_gap_partitions_all_role_skills():
    kb = get_kb()
    role = kb.roles["Data Analyst"]
    gap = calculate_skill_gap(profile_with("SQL", "Excel", "Power BI", "Python"), "Data Analyst")
    names = [g.name for g in gap.matched + gap.partial + gap.missing]
    assert len(names) == len(set(names))
    assert set(names) == set(role.required) | set(role.optional)
    assert {"SQL", "Excel", "Power BI", "Python"} <= {g.name for g in gap.matched}
    assert "Tableau" in {g.name for g in gap.partial}  # related to Power BI
    assert all(g.priority is None for g in gap.matched)
    assert all(g.priority in {"High", "Medium", "Low"} for g in gap.partial + gap.missing)


def test_readiness_is_weighted_required_coverage():
    kb = get_kb()
    role = kb.roles["Data Engineer"]
    full = calculate_skill_gap(profile_with(*role.required), "Data Engineer")
    assert full.readiness_score == 1.0 and not [g for g in full.missing if g.requirement == "required"]
    empty = calculate_skill_gap(profile_with("Communication"), "Data Engineer")
    assert empty.readiness_score == 0.0


def test_priority_prefers_core_and_foundational_skills():
    gap = calculate_skill_gap(profile_with("Excel"), "Data Scientist")
    by_name = {g.name: g for g in gap.missing + gap.partial}
    # Python: weight 3, importance 3, many dependents -> must outrank an optional niche skill
    assert by_name["Python"].priority == "High"
    assert by_name["Python"].priority_score > by_name["Time Series Analysis"].priority_score
    assert by_name["Python"].priority_factors["unblocks"] >= 3


def test_gap_is_deterministic():
    p = profile_with("Python", "SQL", "Docker")
    a = calculate_skill_gap(p, "MLOps Engineer").model_dump()
    b = calculate_skill_gap(p, "MLOps Engineer").model_dump()
    assert a == b


def test_unknown_role():
    with pytest.raises(UnknownRoleError):
        calculate_skill_gap(profile_with("Python"), "Astronaut")


def test_role_match_score_bounds(resume_text):
    kb = get_kb()
    p = build_profile(resume_text, use_ner=False)
    for role in kb.roles.values():
        m = role_match(role, set(p.all_skill_names), kb)
        assert 0 <= m.score <= 1
    da = role_match(kb.roles["Data Analyst"], set(p.all_skill_names), kb)
    sec = role_match(kb.roles["Cybersecurity Analyst"], set(p.all_skill_names), kb)
    assert da.score > sec.score
