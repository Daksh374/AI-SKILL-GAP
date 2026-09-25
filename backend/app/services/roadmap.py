"""Prerequisite-aware, personalized learning roadmap.

Algorithm (deterministic):
  1. Targets = the user's skill-gap result for the role: all required missing/partial skills plus
     optional ones with High/Medium priority.
  2. Expand with transitive prerequisites the candidate does not already hold (credit < 0.75).
  3. Layered topological sort of the prerequisite sub-graph: a stage may only contain skills whose
     prerequisites were covered in EARLIER stages. Among ready skills, the most urgent go first
     (a prerequisite inherits the urgency of the most urgent skill it unlocks), then the most
     foundational (lowest prerequisite depth).
  4. Estimated hours per skill from taxonomy difficulty (1→10h, 2→20h, 3→35h); partial skills
     need half. Each stage is filled up to ~2 weeks of the user's weekly hours; a single large
     skill may span more weeks.
  5. Each stage gets a templated objective and practice project (from the stage's dominant
     category) and, optionally, live YouTube/Coursera resources found through Tavily.
"""
from __future__ import annotations

import math

from backend.app.knowledge import KnowledgeBase, get_kb
from backend.app.schemas import CandidateProfile, Roadmap, RoadmapSkill, RoadmapStage, SkillGapResult, SkillResources
from backend.app.services.matching import skill_credit

HOURS_BY_DIFFICULTY = {1: 10.0, 2: 20.0, 3: 35.0}
PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2, None: 3}
STAGE_WEEKS = 2
METHOD = ("Prerequisite graph from skill_relationships.csv → topological order by gap priority → stages of ~2 weeks "
          "sized by your weekly hours. Study-hour estimates come from taxonomy difficulty (10/20/35 h), halved for partial skills.")

PROJECTS: dict[str, tuple[str, str, list[str]]] = {
    "Programming Languages": ("CLI utility", "Write a small command-line tool that solves a real annoyance (file renamer, log summarizer) using {skills}.",
                              ["Public Git repository with README", "Unit tests for core functions"]),
    "Mathematics & Statistics": ("Statistical investigation", "Pick a public dataset and answer one question rigorously with {skills}; state assumptions and uncertainty.",
                                 ["Notebook with derivations/plots", "One-page findings summary"]),
    "Data Analysis": ("Exploratory analysis report", "Clean and explore an open dataset (e.g. city open-data portal) using {skills}; document data-quality issues you fixed.",
                      ["Cleaned dataset + data dictionary", "Notebook with 5+ insights"]),
    "Data Visualization": ("Interactive dashboard", "Build a dashboard for a public dataset with {skills}, designed for a specific stakeholder question.",
                           ["Published dashboard or screenshots", "Short write-up of design choices"]),
    "Machine Learning": ("End-to-end prediction project", "Train, tune and evaluate models on a public tabular dataset using {skills}; compare at least two models with proper validation.",
                         ["Reproducible training script", "Evaluation report with metrics & error analysis"]),
    "Deep Learning": ("Neural network from dataset to demo", "Train a neural model on an open dataset with {skills}; track experiments and compare to a baseline.",
                      ["Training code + saved weights", "Learning curves and ablation notes"]),
    "NLP": ("Text understanding pipeline", "Build a text classification or extraction pipeline on public text data with {skills}.",
            ["Evaluation on a held-out set", "Small demo API or notebook"]),
    "Computer Vision": ("Vision model demo", "Train or fine-tune a vision model on an open image dataset with {skills}; include failure-case analysis.",
                        ["Inference script / demo", "Precision-recall or accuracy report"]),
    "Generative AI": ("LLM-powered assistant", "Build a small assistant over your own documents using {skills}; add an evaluation set to measure answer quality.",
                      ["Working demo", "Eval set with scores and known failure modes"]),
    "Data Engineering": ("Batch/stream data pipeline", "Ingest a public API or dataset into a warehouse-style store with {skills}, including scheduling and data-quality checks.",
                         ["Pipeline code + orchestration config", "Data-quality tests"]),
    "Databases": ("Database design exercise", "Design, populate and optimize a schema for a realistic app (e.g. library, clinic) using {skills}.",
                  ["ER diagram + DDL", "Query plan before/after an optimization"]),
    "Cloud": ("Cloud deployment", "Deploy a small web service to the cloud using {skills}, keeping it within free-tier limits and documenting costs.",
              ["Architecture diagram", "Teardown/cleanup instructions"]),
    "DevOps": ("CI/CD + container pipeline", "Containerize an app and automate test/build/deploy using {skills}.",
               ["Pipeline config in repo", "Rollback procedure in README"]),
    "MLOps": ("Model lifecycle pipeline", "Take a trained model to a monitored deployment with {skills}: versioning, serving and drift checks.",
              ["Serving endpoint", "Monitoring dashboard or report"]),
    "Backend Development": ("REST API service", "Build a documented REST API with auth, persistence and tests using {skills}.",
                            ["OpenAPI docs", "Test suite with >70% coverage"]),
    "Frontend Development": ("Responsive web app", "Build a responsive single-page app consuming a public API with {skills}.",
                             ["Deployed site or recording", "Accessibility checklist"]),
    "Cybersecurity": ("Home security lab", "Set up an isolated lab (VMs) and practice detection/response scenarios using {skills}.",
                      ["Lab setup notes", "Incident write-up with timeline"]),
    "Business & Product": ("Business case study", "Analyse a real process (e.g. a public case study) and produce requirements and recommendations using {skills}.",
                           ["Requirements document", "Stakeholder presentation deck"]),
    "Soft Skills": ("Communication practice", "Present one of your projects to peers or a meetup, applying {skills}; collect feedback.",
                    ["Slides or recording", "Feedback summary"]),
}


def skill_hours(kb: KnowledgeBase, skill: str, partial: bool) -> float:
    h = HOURS_BY_DIFFICULTY.get(kb.skills[skill].difficulty, 20.0)
    return h * 0.5 if partial else h


def _objective(role: str, skills: list[RoadmapSkill]) -> str:
    names = [s.name for s in skills]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
    if all(s.reason == "prerequisite" for s in skills):
        return f"Build the foundations ({joined}) that later {role} skills depend on."
    if all(s.reason == "partial" for s in skills):
        return f"Deepen skills you partially have ({joined}) to the level expected of a {role}."
    return f"Gain working proficiency in {joined} for the {role} role."


def _project(role: str, skills: list[RoadmapSkill]) -> dict:
    weight: dict[str, float] = {}
    for s in skills:
        weight[s.category] = weight.get(s.category, 0) + s.estimated_hours
    category = max(weight, key=lambda c: (weight[c], c))
    title, desc, deliverables = PROJECTS.get(category, PROJECTS["Programming Languages"])
    names = ", ".join(s.name for s in skills)
    return {"title": f"{title} ({role} track)", "description": desc.format(skills=names), "deliverables": deliverables,
            "category": category, "source": "template (deterministic, based on the stage's dominant skill category)"}


def build_learning_path(profile: CandidateProfile, gap: SkillGapResult, resume_id: int, hours_per_week: int = 10,
                        resources: dict[str, SkillResources] | None = None, kb: KnowledgeBase | None = None) -> Roadmap:
    """Tool entrypoint."""
    kb = kb or get_kb()
    candidate = set(profile.all_skill_names)

    targets: dict[str, RoadmapSkill] = {}
    prio_score: dict[str, float] = {}
    for item in gap.partial + gap.missing:
        if item.requirement == "optional" and item.priority not in {"High", "Medium"}:
            continue
        partial = item.status == "partial"
        targets[item.name] = RoadmapSkill(name=item.name, category=item.category, reason="partial" if partial else "missing",
                                          priority=item.priority, estimated_hours=skill_hours(kb, item.name, partial))
        prio_score[item.name] = item.priority_score or 0.0

    # add missing prerequisites (transitively)
    frontier = list(targets)
    while frontier:
        s = frontier.pop()
        for p in kb.prerequisites.get(s, ()):
            if p in targets or skill_credit(p, candidate, kb).credit >= 0.75:
                continue
            targets[p] = RoadmapSkill(name=p, category=kb.skills[p].category, reason="prerequisite", priority=None,
                                      estimated_hours=skill_hours(kb, p, False))
            prio_score[p] = max(prio_score.get(p, 0.0), prio_score.get(s, 0.0))  # inherits urgency of what it unlocks
            frontier.append(p)

    for name, rs in targets.items():
        rs.prerequisites = sorted(p for p in kb.prerequisites.get(name, ()) if p in targets)

    # Effective urgency: a prerequisite is as urgent as the most urgent skill it (transitively) unlocks.
    eff_rank = {n: PRIORITY_RANK[targets[n].priority] for n in targets}
    eff_score = dict(prio_score)
    for n in targets:
        for p in kb.all_prerequisites(n):
            if p in targets:
                eff_rank[p] = min(eff_rank[p], eff_rank[n])
                eff_score[p] = max(eff_score.get(p, 0.0), prio_score.get(n, 0.0))
    depth_memo: dict[str, int] = {}

    def key(n: str) -> tuple:
        return (eff_rank[n], -eff_score.get(n, 0.0), kb.prerequisite_depth(n, depth_memo), n)

    # Stage packing = layered topological sort: each stage takes the most urgent skills whose
    # prerequisites were all covered in EARLIER stages, until the ~2-week hour budget is used.
    capacity = hours_per_week * STAGE_WEEKS
    remaining, done = set(targets), set()
    stages_skills: list[list[RoadmapSkill]] = []
    while remaining:
        ready = sorted((n for n in remaining if all(p in done for p in targets[n].prerequisites)), key=key)
        if not ready:  # cannot happen with a DAG; guard against malformed data
            ready = sorted(remaining, key=key)
        stage: list[RoadmapSkill] = []
        hours = 0.0
        for n in ready:
            h = targets[n].estimated_hours
            if stage and hours + h > capacity * 1.25:
                break
            stage.append(targets[n])
            hours += h
            if hours >= capacity:
                break
        stages_skills.append(stage)
        names = {s.name for s in stage}
        done |= names
        remaining -= names

    stages: list[RoadmapStage] = []
    week = 1
    stage_prereq_done: set[str] = set(candidate)
    for i, sk in enumerate(stages_skills):
        hours = sum(s.estimated_hours for s in sk)
        weeks = max(1, math.ceil(hours / hours_per_week))
        prereqs = sorted({p for s in sk for p in kb.prerequisites.get(s.name, ())})
        yt, co, notes = [], [], []
        if resources is not None:
            for s in sk:
                r = resources.get(s.name)
                if r is None:
                    notes.append(f"{s.name}: resources not searched (per-roadmap search cap reached).")
                    continue
                yt.extend(r.youtube)
                co.extend(r.coursera)
                if not r.youtube and not r.coursera:
                    notes.append(f"{s.name}: no resources found ({r.message or r.youtube_status}).")
        stages.append(RoadmapStage(
            index=i, week_start=week, week_end=week + weeks - 1,
            label=f"Week {week}" if weeks == 1 else f"Week {week}–{week + weeks - 1}",
            objective=_objective(gap.role, sk), skills=sk,
            prerequisites=[p for p in prereqs if p in stage_prereq_done or p in {x.name for st in stages for x in st.skills}],
            estimated_hours=hours, practice_project=_project(gap.role, sk), youtube=yt, coursera=co, resource_notes=notes,
        ))
        stage_prereq_done.update(s.name for s in sk)
        week += weeks

    if resources is None:
        res_status = "not_requested"
    else:
        statuses = {s for r in resources.values() for s in (r.youtube_status, r.coursera_status)}
        res_status = "not_configured" if statuses == {"not_configured"} else "ok" if "ok" in statuses else \
            "error" if statuses <= {"error", "not_configured"} else "empty"

    return Roadmap(resume_id=resume_id, role=gap.role, hours_per_week=hours_per_week, total_weeks=week - 1,
                   total_hours=sum(s.estimated_hours for s in stages), stages=stages, method=METHOD, resources_status=res_status)


def roadmap_resource_skills(gap: SkillGapResult, profile: CandidateProfile, cap: int = 12) -> list[str]:
    """Skills to fetch live resources for (bounded to control Tavily usage): gap skills by priority, then prerequisites."""
    kb = get_kb()
    ordered = [i.name for i in sorted(gap.partial + gap.missing, key=lambda i: (PRIORITY_RANK[i.priority], -(i.priority_score or 0)))
               if not (i.requirement == "optional" and i.priority not in {"High", "Medium"})]
    candidate = set(profile.all_skill_names)
    extra = [p for s in ordered for p in kb.all_prerequisites(s) if skill_credit(p, candidate, kb).credit < 0.75]
    return list(dict.fromkeys(ordered + extra))[:cap]
