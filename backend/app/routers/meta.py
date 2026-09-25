"""Health, roles, taxonomy and model-report endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.config import MODELS_DIR, get_settings
from backend.app.knowledge import get_kb
from backend.app.ml.predictor import load_evaluation_report
from backend.app.nlp.spacy_loader import get_nlp

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", summary="Service health and configuration status")
def health() -> dict:
    return {
        "status": "ok",
        "model_trained": (MODELS_DIR / "career_model.joblib").exists(),
        "spacy_model_loaded": get_nlp() is not None,
        "tavily_configured": get_settings().tavily_configured,
    }


@router.get("/roles", summary="All roles with requirement weights")
def roles() -> list[dict]:
    kb = get_kb()
    return [
        {"role_id": r.role_id, "role": r.name, "category": r.category, "description": r.description,
         "experience_level": r.experience_level, "required_skills": r.required, "optional_skills": r.optional,
         "education_requirements": r.education_requirements, "synthetic_jd_count": kb.jd_counts.get(r.name, 0)}
        for r in kb.roles.values()
    ]


@router.get("/skills", summary="Search the skills taxonomy")
def skills(q: str = Query("", max_length=60), limit: int = Query(20, le=100)) -> list[dict]:
    kb = get_kb()
    ql = q.lower().strip()
    out = []
    for s in kb.skills.values():
        if not ql or ql in s.name.lower() or any(ql in a.lower() for a in s.aliases):
            out.append({"name": s.name, "category": s.category, "aliases": list(s.aliases),
                        "prerequisites": sorted(kb.prerequisites.get(s.name, [])), "difficulty": s.difficulty,
                        "importance": s.importance})
        if len(out) >= limit:
            break
    return out


@router.get("/model/report", summary="Training/evaluation report of the career model")
def model_report() -> dict:
    report = load_evaluation_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No evaluation report. Run: python -m backend.app.ml.train")
    return report
