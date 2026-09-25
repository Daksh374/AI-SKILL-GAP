"""Resume upload / analysis / career ranking / skill-gap endpoints."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db.database import ResumeRecord, RoadmapRecord, get_db
from backend.app.ml.predictor import ModelNotTrainedError, predict_career
from backend.app.nlp.parser import ResumeParseError, parse_resume
from backend.app.nlp.profile import build_profile
from backend.app.routers.deps import get_resume, profile_of, session_id
from backend.app.schemas import CareerPredictions, SkillGapResult
from backend.app.services.skill_gap import UnknownRoleError, calculate_skill_gap

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _summary(rec: ResumeRecord) -> dict:
    prof = rec.profile_json
    preds = rec.predictions_json.get("predictions", [])
    return {
        "id": rec.id, "filename": rec.filename, "file_type": rec.file_type, "created_at": rec.created_at,
        "name": prof.get("name"), "skill_count": len(prof.get("technical_skills", [])) + len(prof.get("soft_skills", [])),
        "top_role": preds[0]["role"] if preds else None,
    }


@router.post("", summary="Upload a PDF/DOCX resume, extract a profile and rank careers")
async def upload_resume(file: UploadFile = File(...), sid: str = Depends(session_id), db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB limit.")
    filename = file.filename or "resume"
    try:
        parsed = await asyncio.to_thread(parse_resume, filename, data)
    except ResumeParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    profile = await asyncio.to_thread(build_profile, parsed.text)
    try:
        predictions = await asyncio.to_thread(predict_career, profile)
    except ModelNotTrainedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    rec = ResumeRecord(session_id=sid, filename=filename[:255], file_type=parsed.file_type, raw_text=parsed.text,
                       profile_json=profile.model_dump(mode="json"), predictions_json=predictions.model_dump(mode="json"))
    db.add(rec)
    db.commit()
    db.refresh(rec)
    logger.info("Stored resume %d (%d skills) for session %s…", rec.id, len(profile.all_skill_names), sid[:8])
    return {"resume": _summary(rec), "profile": profile, "careers": predictions}


@router.get("", summary="List resumes uploaded in this session")
def list_resumes(sid: str = Depends(session_id), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(ResumeRecord).where(ResumeRecord.session_id == sid).order_by(ResumeRecord.created_at.desc()))
    return [_summary(r) for r in rows]


@router.get("/{resume_id}", summary="Get the extracted profile for a resume")
def get_resume_detail(rec: ResumeRecord = Depends(get_resume)) -> dict:
    return {"resume": _summary(rec), "profile": rec.profile_json, "careers": rec.predictions_json}


@router.delete("/{resume_id}", status_code=204, response_class=Response, summary="Delete a resume and its roadmaps")
def delete_resume(rec: ResumeRecord = Depends(get_resume), db: Session = Depends(get_db)) -> Response:
    db.delete(rec)
    db.commit()
    return Response(status_code=204)


@router.get("/{resume_id}/careers", response_model=CareerPredictions, summary="Ranked career roles")
def get_careers(rec: ResumeRecord = Depends(get_resume)) -> dict:
    return rec.predictions_json


@router.get("/{resume_id}/skill-gap", response_model=SkillGapResult, summary="Deterministic skill gap for a role")
def get_skill_gap(role: str | None = Query(None, description="Defaults to the top-ranked role"),
                  rec: ResumeRecord = Depends(get_resume)) -> SkillGapResult:
    role = role or rec.predictions_json["predictions"][0]["role"]
    try:
        return calculate_skill_gap(profile_of(rec), role)
    except UnknownRoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{resume_id}/dashboard", summary="Aggregated dashboard data")
def dashboard(role: str | None = Query(None), rec: ResumeRecord = Depends(get_resume), db: Session = Depends(get_db)) -> dict:
    profile = profile_of(rec)
    preds = rec.predictions_json["predictions"]
    role = role or preds[0]["role"]
    try:
        gap = calculate_skill_gap(profile, role)
    except UnknownRoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    roadmap = db.scalars(select(RoadmapRecord).where(RoadmapRecord.resume_id == rec.id, RoadmapRecord.role == role)
                         .order_by(RoadmapRecord.created_at.desc())).first()
    by_cat: dict[str, int] = {}
    for s in profile.technical_skills:
        by_cat[s.category] = by_cat.get(s.category, 0) + 1
    progress = None
    if roadmap:
        stages = roadmap.roadmap_json["stages"]
        done = set(roadmap.completed_stages or [])
        total_h = sum(s["estimated_hours"] for s in stages) or 1
        progress = {"roadmap_id": roadmap.id, "stages_total": len(stages), "stages_completed": len(done),
                    "hours_completed": sum(s["estimated_hours"] for s in stages if s["index"] in done),
                    "hours_total": total_h, "percent": round(100 * sum(s["estimated_hours"] for s in stages if s["index"] in done) / total_h, 1)}
    return {
        "resume": _summary(rec),
        "role": role,
        "readiness_score": gap.readiness_score,
        "match_score": next((p["match"]["score"] for p in preds if p["role"] == role), None),
        "skill_count": len(profile.all_skill_names),
        "technical_skill_count": len(profile.technical_skills),
        "soft_skill_count": len(profile.soft_skills),
        "skills_by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
        "experience_years": profile.total_experience_years,
        "education_level": profile.highest_education_level,
        "top_roles": [{"role": p["role"], "probability": p["probability"], "match_score": p["match"]["score"]} for p in preds[:5]],
        "gap_summary": gap.summary,
        "top_gaps": [{"name": g.name, "priority": g.priority, "status": g.status, "priority_score": g.priority_score}
                     for g in sorted(gap.missing + gap.partial, key=lambda g: -(g.priority_score or 0))
                     if g.requirement == "required"][:6],
        "progress": progress,
    }
