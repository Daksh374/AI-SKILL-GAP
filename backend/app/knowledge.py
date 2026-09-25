"""Loads the curated/synthetic knowledge files from data/ into typed, queryable structures.

This is the single place the backend reads data/*.csv|json. Everything downstream (NLP,
feature engineering, skill gap, roadmap) consumes the `KnowledgeBase`.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.app.config import DATA_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Skill:
    skill_id: str
    name: str
    category: str
    aliases: tuple[str, ...]
    case_sensitive_aliases: tuple[str, ...]
    importance: int
    difficulty: int
    ambiguous: bool


@dataclass
class Role:
    role_id: str
    name: str
    category: str
    description: str
    experience_level: str
    required: dict[str, int]  # skill -> weight (1..3)
    optional: list[str]
    education_requirements: str


@dataclass
class KnowledgeBase:
    skills: dict[str, Skill]
    categories: list[str]
    roles: dict[str, Role]
    prerequisites: dict[str, set[str]] = field(default_factory=dict)  # skill -> direct prerequisites
    dependents: dict[str, set[str]] = field(default_factory=dict)  # skill -> skills that need it
    related: dict[str, dict[str, float]] = field(default_factory=dict)  # skill -> {related: strength}
    specializations: dict[str, set[str]] = field(default_factory=dict)  # general -> {specific tools}
    generalizations: dict[str, set[str]] = field(default_factory=dict)  # specific -> {general concepts}
    # role -> skill -> share of synthetic JDs for that role listing the skill (required=1, preferred=0.5)
    jd_demand: dict[str, dict[str, float]] = field(default_factory=dict)
    jd_counts: dict[str, int] = field(default_factory=dict)

    # ---------------------------------------------------------------- queries
    def skill(self, name: str) -> Skill | None:
        return self.skills.get(name)

    def all_prerequisites(self, name: str) -> set[str]:
        """Transitive closure of prerequisites for a skill."""
        out: set[str] = set()
        stack = list(self.prerequisites.get(name, ()))
        while stack:
            p = stack.pop()
            if p not in out:
                out.add(p)
                stack.extend(self.prerequisites.get(p, ()))
        return out

    def prerequisite_depth(self, name: str, _memo: dict[str, int] | None = None) -> int:
        """Length of the longest prerequisite chain below a skill (0 = foundational)."""
        memo = _memo if _memo is not None else {}
        if name in memo:
            return memo[name]
        prereqs = self.prerequisites.get(name, set())
        depth = 0 if not prereqs else 1 + max(self.prerequisite_depth(p, memo) for p in prereqs)
        memo[name] = depth
        return depth

    @property
    def role_names(self) -> list[str]:
        return list(self.roles)


def _split(value: object) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return []
    return [v.strip() for v in value.split(";") if v.strip()]


def load_knowledge_base(data_dir: Path = DATA_DIR) -> KnowledgeBase:
    tax = json.loads((data_dir / "skills_taxonomy.json").read_text())
    skills = {
        s["name"]: Skill(
            skill_id=s["skill_id"],
            name=s["name"],
            category=s["category"],
            aliases=tuple(s.get("aliases", [])),
            case_sensitive_aliases=tuple(s.get("case_sensitive_aliases", [])),
            importance=int(s["importance"]),
            difficulty=int(s["difficulty"]),
            ambiguous=bool(s.get("ambiguous", False)),
        )
        for s in tax["skills"]
    }

    roles_df = pd.read_csv(data_dir / "job_roles.csv")
    roles: dict[str, Role] = {}
    for row in roles_df.itertuples(index=False):
        weights = {k: int(v) for k, v in json.loads(row.skill_weights).items()}
        roles[row.role_name] = Role(
            role_id=row.role_id,
            name=row.role_name,
            category=row.category,
            description=row.description,
            experience_level=row.experience_level,
            required=weights,
            optional=_split(row.optional_skills),
            education_requirements=row.education_requirements,
        )

    kb = KnowledgeBase(skills=skills, categories=list(tax["categories"]), roles=roles)
    prereq: dict[str, set[str]] = defaultdict(set)
    dependents: dict[str, set[str]] = defaultdict(set)
    related: dict[str, dict[str, float]] = defaultdict(dict)
    spec: dict[str, set[str]] = defaultdict(set)
    gen: dict[str, set[str]] = defaultdict(set)
    rel_df = pd.read_csv(data_dir / "skill_relationships.csv")
    for r in rel_df.itertuples(index=False):
        src, dst = r.source_skill, r.target_skill
        if src not in skills or dst not in skills:
            logger.warning("Skipping relationship %s with unknown skill(s)", r.relationship_id)
            continue
        if r.relationship_type == "prerequisite":
            prereq[dst].add(src)
            dependents[src].add(dst)
        elif r.relationship_type == "related":
            related[src][dst] = float(r.strength)
            related[dst][src] = float(r.strength)
        elif r.relationship_type == "specialization":
            spec[dst].add(src)
            gen[src].add(dst)
    kb.prerequisites, kb.dependents, kb.related = dict(prereq), dict(dependents), dict(related)
    kb.specializations, kb.generalizations = dict(spec), dict(gen)

    jd_path = data_dir / "job_descriptions.csv"
    if jd_path.exists():
        jd = pd.read_csv(jd_path)
        demand: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        counts = jd["role_name"].value_counts().to_dict()
        for row in jd.itertuples(index=False):
            for s in _split(row.required_skills):
                demand[row.role_name][s] += 1.0
            for s in _split(row.preferred_skills):
                demand[row.role_name][s] += 0.5
        kb.jd_demand = {
            role: {s: round(v / counts[role], 4) for s, v in sk.items()} for role, sk in demand.items()
        }
        kb.jd_counts = {k: int(v) for k, v in counts.items()}

    logger.info(
        "Knowledge base loaded: %d skills, %d roles, %d relationships, %d synthetic JDs",
        len(skills), len(roles), len(rel_df), sum(kb.jd_counts.values()),
    )
    return kb


@lru_cache
def get_kb() -> KnowledgeBase:
    return load_knowledge_base()
