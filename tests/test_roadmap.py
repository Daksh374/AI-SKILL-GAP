from datetime import datetime, timezone

from backend.app.knowledge import get_kb
from backend.app.schemas import LearningResource, SkillResources
from backend.app.services.roadmap import build_learning_path, roadmap_resource_skills
from backend.app.services.skill_gap import calculate_skill_gap
from tests.test_skill_gap import profile_with


def _stage_of(roadmap):
    return {s.name: st.index for st in roadmap.stages for s in st.skills}


def test_prerequisites_come_in_earlier_stages():
    kb = get_kb()
    p = profile_with("Excel", "SQL")
    gap = calculate_skill_gap(p, "GenAI Engineer")
    rm = build_learning_path(p, gap, resume_id=1, hours_per_week=10)
    where = _stage_of(rm)
    for name, idx in where.items():
        for pre in kb.prerequisites.get(name, ()):
            if pre in where:
                assert where[pre] < idx, f"{pre} must precede {name}"


def test_roadmap_covers_required_gaps_and_skips_known_skills():
    p = profile_with("Python", "SQL", "Pandas")
    gap = calculate_skill_gap(p, "Data Scientist")
    rm = build_learning_path(p, gap, resume_id=1, hours_per_week=8)
    names = set(_stage_of(rm))
    required_gaps = {g.name for g in gap.missing + gap.partial if g.requirement == "required"}
    assert required_gaps <= names
    assert not names & {"Python", "SQL", "Pandas"}


def test_timeline_is_contiguous_and_hours_consistent():
    p = profile_with("HTML")
    gap = calculate_skill_gap(p, "Full Stack Developer")
    rm = build_learning_path(p, gap, resume_id=1, hours_per_week=12)
    week = 1
    for st in rm.stages:
        assert st.week_start == week and st.week_end >= st.week_start
        assert st.estimated_hours == sum(s.estimated_hours for s in st.skills)
        assert st.practice_project["title"] and st.objective
        week = st.week_end + 1
    assert rm.total_weeks == week - 1
    assert rm.total_hours == sum(st.estimated_hours for st in rm.stages)


def test_more_hours_per_week_means_fewer_weeks():
    p = profile_with("Excel")
    gap = calculate_skill_gap(p, "ML Engineer")
    slow = build_learning_path(p, gap, resume_id=1, hours_per_week=5)
    fast = build_learning_path(p, gap, resume_id=1, hours_per_week=25)
    assert fast.total_weeks < slow.total_weeks
    assert fast.total_hours == slow.total_hours


def test_resources_are_attached_per_stage_and_missing_ones_reported():
    p = profile_with("Excel")
    gap = calculate_skill_gap(p, "Data Analyst")
    skills = roadmap_resource_skills(gap, p, cap=3)
    now = datetime.now(timezone.utc)
    res = {s: SkillResources(skill=s, youtube_status="empty", coursera_status="empty", message="Tavily returned no results")
           for s in skills}
    res[skills[0]] = SkillResources(skill=skills[0], youtube_status="ok", coursera_status="empty", youtube=[
        LearningResource(platform="YouTube", skill=skills[0], title="T", url="https://www.youtube.com/watch?v=abc", retrieved_at=now)])
    rm = build_learning_path(p, gap, resume_id=1, resources=res)
    all_yt = [r for st in rm.stages for r in st.youtube]
    assert [r.url for r in all_yt] == ["https://www.youtube.com/watch?v=abc"]
    notes = " ".join(n for st in rm.stages for n in st.resource_notes)
    assert "no resources found" in notes
    assert rm.resources_status == "ok"
