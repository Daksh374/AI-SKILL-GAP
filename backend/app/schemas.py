"""Pydantic models shared by services and API routes."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ============================================================== candidate profile (NLP)


class ExtractedSkill(BaseModel):
    name: str = Field(description="Canonical skill name from the taxonomy")
    category: str
    confidence: float = Field(ge=0, le=1, description="Heuristic extraction confidence (not a probability)")
    mentions: int
    sections: list[str]
    matched_forms: list[str] = Field(description="Surface forms found in the resume that normalized to this skill")
    ner_supported: bool = False


class EducationEntry(BaseModel):
    degree: str | None = None
    level: Literal["PhD", "Master", "Bachelor", "Associate", "Unknown"] = "Unknown"
    field_of_study: str | None = None
    institution: str | None = None
    year: int | None = None
    raw: str


class ExperienceEntry(BaseModel):
    title: str | None = None
    company: str | None = None
    start: str | None = Field(None, description="YYYY-MM")
    end: str | None = Field(None, description="YYYY-MM or 'Present'")
    duration_months: int = 0
    raw: str


class ProjectEntry(BaseModel):
    title: str
    description: str = ""
    skills: list[str] = []


class CandidateProfile(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    summary: str | None = None
    technical_skills: list[ExtractedSkill] = []
    soft_skills: list[ExtractedSkill] = []
    unrecognized_terms: list[str] = Field(default=[], description="Entities in the Skills section not found in the taxonomy")
    education: list[EducationEntry] = []
    highest_education_level: str = "Unknown"
    experience: list[ExperienceEntry] = []
    total_experience_years: float = 0.0
    experience_source: Literal["date_ranges", "stated_years", "none"] = "none"
    projects: list[ProjectEntry] = []
    certifications: list[str] = []
    sections_detected: list[str] = []
    word_count: int = 0
    warnings: list[str] = []

    @property
    def all_skill_names(self) -> list[str]:
        return [s.name for s in self.technical_skills + self.soft_skills]


# ============================================================== career ranking


class RoleMatchDetail(BaseModel):
    score: float = Field(ge=0, le=1, description="Deterministic weighted overlap between candidate and role skills")
    required_coverage: float
    optional_coverage: float
    matched_required: list[str]
    partial_required: list[str]
    missing_required: list[str]
    matched_optional: list[str]


class RolePrediction(BaseModel):
    rank: int
    role: str
    category: str
    probability: float = Field(description="Model-predicted probability (trained on synthetic data)")
    match: RoleMatchDetail
    explanation: list[str]
    top_features: list[dict] = Field(default=[], description="Model features that most supported this role")


class CareerPredictions(BaseModel):
    model_name: str
    model_trained_at: str | None
    model_test_macro_f1: float | None
    disclaimer: str
    predictions: list[RolePrediction]


# ============================================================== skill gap


class GapSkill(BaseModel):
    name: str
    category: str
    status: Literal["matched", "partial", "missing"]
    requirement: Literal["required", "optional"]
    role_weight: int = Field(description="Role requirement weight 1-3 from job_roles.csv (optional skills = 1)")
    priority: Literal["High", "Medium", "Low"] | None = None
    priority_score: float | None = None
    priority_factors: dict[str, float] = {}
    evidence: list[str] = Field(default=[], description="Candidate skills that give partial credit")
    credit: float = Field(ge=0, le=1)
    candidate_confidence: float | None = None


class SkillGapResult(BaseModel):
    role: str
    readiness_score: float = Field(ge=0, le=1, description="Weighted required-skill coverage (matched=1, partial=credit)")
    matched: list[GapSkill]
    partial: list[GapSkill]
    missing: list[GapSkill]
    summary: dict[str, int]
    method: str


# ============================================================== web / market


class SourceItem(BaseModel):
    title: str
    url: str
    snippet: str
    domain: str
    published_date: str | None = None
    retrieved_at: datetime
    score: float | None = None
    query: str


class SearchOutcome(BaseModel):
    query: str
    status: Literal["ok", "empty", "error", "not_configured"]
    message: str | None = None
    results: list[SourceItem] = []
    answer: str | None = None
    retrieved_at: datetime | None = None
    cached: bool = False


class SkillMention(BaseModel):
    skill: str
    category: str
    source_count: int
    candidate_has: bool
    source_urls: list[str]


class MarketIntelligence(BaseModel):
    role: str
    status: Literal["ok", "partial", "empty", "error", "not_configured"]
    message: str | None = None
    retrieved_at: datetime | None = None
    observed_sources: list[SourceItem] = []
    skill_mentions: list[SkillMention] = Field(default=[], description="Taxonomy skills mentioned in retrieved snippets")
    ai_interpretation: list[dict] = Field(default=[], description="Tavily's AI-generated answers (labelled as interpretation)")
    queries: list[SearchOutcome] = []


class LearningResource(BaseModel):
    platform: Literal["YouTube", "Coursera"]
    skill: str
    title: str
    url: str
    snippet: str = ""
    channel: str | None = None
    provider: str | None = None
    resource_type: str | None = None
    free_mentioned: bool = Field(False, description="True only if the retrieved snippet explicitly mentions free access")
    free_evidence: str | None = None
    retrieved_at: datetime


class SkillResources(BaseModel):
    skill: str
    youtube: list[LearningResource] = []
    coursera: list[LearningResource] = []
    youtube_status: str = "not_requested"
    coursera_status: str = "not_requested"
    message: str | None = None


# ============================================================== roadmap


class RoadmapSkill(BaseModel):
    name: str
    category: str
    reason: Literal["missing", "partial", "prerequisite"]
    priority: str | None = None
    estimated_hours: float
    prerequisites: list[str] = []


class RoadmapStage(BaseModel):
    index: int
    week_start: int
    week_end: int
    label: str
    objective: str
    skills: list[RoadmapSkill]
    prerequisites: list[str]
    estimated_hours: float
    practice_project: dict
    youtube: list[LearningResource] = []
    coursera: list[LearningResource] = []
    resource_notes: list[str] = []
    completed: bool = False


class Roadmap(BaseModel):
    id: int | None = None
    resume_id: int
    role: str
    hours_per_week: int
    total_weeks: int
    total_hours: float
    stages: list[RoadmapStage]
    method: str
    resources_status: str
    created_at: datetime | None = None


class RoadmapRequest(BaseModel):
    role: str | None = None
    hours_per_week: int = Field(10, ge=2, le=60)
    include_resources: bool = True


class ProgressUpdate(BaseModel):
    stage_index: int
    completed: bool


class MarketRequest(BaseModel):
    role: str
    resume_id: int | None = None
    refresh: bool = False
