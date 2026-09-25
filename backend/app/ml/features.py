"""Feature engineering: CandidateProfile -> numeric vector.

Feature groups (all derived from the NLP output, so training and inference share one code path):
  skill::<name>        219  binary presence of each taxonomy skill
  cat::<category>       19  number of skills per category (scaled /10)
  jd_sim::<role>        22  cosine similarity between the candidate's skill vector and the role's
                            prototype built from job_descriptions.csv (required=1, preferred=0.5)
  exp_years              1  total experience (years, clipped to 30, scaled /10)
  edu_level              1  highest degree ordinal (0 unknown .. 4 PhD)
  field::<group>         8  field-of-study group one-hot
  cert::<group>          7  certification-keyword group flags
  n_certs, n_projects,
  n_tech_skills, n_soft_skills
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.app.config import DATA_DIR
from backend.app.knowledge import KnowledgeBase
from backend.app.schemas import CandidateProfile

EDU_LEVEL = {"Unknown": 0, "Associate": 1, "Bachelor": 2, "Master": 3, "PhD": 4}

FIELD_GROUPS: dict[str, list[str]] = {
    "computing": ["computer science", "software", "information technology", "computer engineering", "computing", "computer applications"],
    "data_ai": ["data science", "artificial intelligence", "machine learning", "computational linguistics", "analytics"],
    "math_stats": ["statistics", "mathematics", "math", "physics", "applied math"],
    "engineering": ["electrical", "electronics", "robotics", "mechanical", "engineering"],
    "business": ["business", "management", "economics", "finance", "commerce", "information systems", "mba"],
    "security": ["cybersecurity", "cyber security", "information security", "security"],
    "design": ["design", "hci", "human-computer", "fine arts"],
}
CERT_GROUPS: dict[str, str] = {
    "cloud": r"\b(aws|azure|google cloud|gcp|cloud)\b",
    "security": r"\b(security|comptia|cissp|ceh|oscp|ethical|cyber)",
    "data": r"\b(data|analytics|power bi|tableau|dbt|snowpro|databricks)\b",
    "ml_ai": r"\b(machine learning|tensorflow|ai|deep learning|nlp|natural language|generative|nvidia|llm)\b",
    "devops": r"\b(kubernetes|terraform|devops|sysops|cka|docker)\b",
    "business_pm": r"\b(scrum|business analysis|pmi|iiba|pmp|agile)\b",
    "software_dev": r"\b(developer|java|front-end|back-end|oracle)\b",
}


def field_group(field: str | None) -> str:
    if not field:
        return "other"
    f = field.lower()
    for group, keys in FIELD_GROUPS.items():
        if any(k in f for k in keys):
            return group
    return "other"


def build_role_prototypes(kb: KnowledgeBase, jd_path=DATA_DIR / "job_descriptions.csv") -> dict[str, np.ndarray]:
    """Mean skill vector per role over the synthetic job-description corpus."""
    skill_index = {s: i for i, s in enumerate(kb.skills)}
    jd = pd.read_csv(jd_path)
    protos: dict[str, np.ndarray] = {}
    for role, grp in jd.groupby("role_name"):
        acc = np.zeros(len(skill_index))
        for row in grp.itertuples(index=False):
            for col, w in (("required_skills", 1.0), ("preferred_skills", 0.5)):
                val = getattr(row, col)
                if isinstance(val, str):
                    for s in val.split(";"):
                        if s in skill_index:
                            acc[skill_index[s]] += w
        protos[str(role)] = acc / max(len(grp), 1)
    return protos


@dataclass
class FeatureBuilder:
    skill_names: list[str]
    categories: list[str]
    roles: list[str]
    prototypes: dict[str, np.ndarray]

    @classmethod
    def from_kb(cls, kb: KnowledgeBase) -> "FeatureBuilder":
        return cls(
            skill_names=list(kb.skills),
            categories=list(kb.categories),
            roles=list(kb.roles),
            prototypes=build_role_prototypes(kb),
        )

    @property
    def feature_names(self) -> list[str]:
        return (
            [f"skill::{s}" for s in self.skill_names]
            + [f"cat::{c}" for c in self.categories]
            + [f"jd_sim::{r}" for r in self.roles]
            + ["exp_years", "edu_level"]
            + [f"field::{g}" for g in [*FIELD_GROUPS, "other"]]
            + [f"cert::{g}" for g in CERT_GROUPS]
            + ["n_certs", "n_projects", "n_tech_skills", "n_soft_skills"]
        )

    def skill_vector(self, skills: set[str]) -> np.ndarray:
        return np.array([1.0 if s in skills else 0.0 for s in self.skill_names])

    def transform_one(self, profile: CandidateProfile, skills_override: set[str] | None = None) -> np.ndarray:
        skills = skills_override if skills_override is not None else set(profile.all_skill_names)
        sv = self.skill_vector(skills)

        cat_index = {c: i for i, c in enumerate(self.categories)}
        cats = np.zeros(len(self.categories))
        skill_cat = {s.name: s.category for s in profile.technical_skills + profile.soft_skills}
        for s in skills:
            if s in skill_cat:
                cats[cat_index[skill_cat[s]]] += 1
        cats /= 10.0

        sims = []
        norm_c = np.linalg.norm(sv)
        for r in self.roles:
            p = self.prototypes.get(r)
            if p is None or norm_c == 0:
                sims.append(0.0)
            else:
                sims.append(float(sv @ p / (norm_c * (np.linalg.norm(p) or 1.0))))

        exp = min(profile.total_experience_years, 30.0) / 10.0
        edu = EDU_LEVEL.get(profile.highest_education_level, 0)
        groups = [*FIELD_GROUPS, "other"]
        fvec = np.zeros(len(groups))
        highest = [e for e in profile.education if e.level == profile.highest_education_level] or profile.education
        if highest:
            fvec[groups.index(field_group(highest[0].field_of_study))] = 1.0
        cert_text = " ".join(profile.certifications).lower()
        cvec = [1.0 if re.search(p, cert_text) else 0.0 for p in CERT_GROUPS.values()]
        n_tech = sum(1 for s in skills if skill_cat.get(s) != "Soft Skills")
        n_soft = len(skills) - n_tech
        counts = [len(profile.certifications) / 3.0, len(profile.projects) / 3.0, n_tech / 20.0, n_soft / 5.0]
        return np.concatenate([sv, cats, np.array(sims), [exp, edu], fvec, cvec, counts]).astype(np.float32)

    def transform(self, profiles: list[CandidateProfile]) -> np.ndarray:
        return np.vstack([self.transform_one(p) for p in profiles])
