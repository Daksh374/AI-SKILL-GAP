"""Learning-roadmap endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.database import ResumeRecord, RoadmapRecord, get_db
from backend.app.routers.deps import get_resume, profile_of, session_id
from backend.app.schemas import ProgressUpdate, Roadmap, RoadmapRequest
from backend.app.services.resources import find_resources
from backend.app.services.roadmap import build_learning_path, roadmap_resource_skills
from backend.app.services.skill_gap import UnknownRoleError, calculate_skill_gap

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["roadmap"])


def _to_model(rec: RoadmapRecord) -> Roadmap:
    rm = Roadmap.model_validate(rec.roadmap_json)
    rm.id = rec.id
    rm.created_at = rec.created_at
    done = set(rec.completed_stages or [])
    for s in rm.stages:
        s.completed = s.index in done
    return rm


@router.post("/resumes/{resume_id}/roadmap", response_model=Roadmap, summary="Generate a personalized roadmap")
async def create_roadmap(req: RoadmapRequest, rec: ResumeRecord = Depends(get_resume), db: Session = Depends(get_db)) -> Roadmap:
    profile = profile_of(rec)
    role = req.role or rec.predictions_json["predictions"][0]["role"]
    try:
        gap = calculate_skill_gap(profile, role)
    except UnknownRoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resources = None
    if req.include_resources:
        skills = roadmap_resource_skills(gap, profile)
        resources = await find_resources(skills)
        logger.info("Fetched resources for %d skills (role=%s)", len(skills), role)

    roadmap = build_learning_path(profile, gap, resume_id=rec.id, hours_per_week=req.hours_per_week, resources=resources)
    row = RoadmapRecord(resume_id=rec.id, role=role, hours_per_week=req.hours_per_week,
                        roadmap_json=roadmap.model_dump(mode="json"), completed_stages=[])
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_model(row)


@router.get("/resumes/{resume_id}/roadmap", response_model=Roadmap | None, summary="Latest roadmap for a role")
def latest_roadmap(role: str | None = Query(None), rec: ResumeRecord = Depends(get_resume), db: Session = Depends(get_db)) -> Roadmap | None:
    q = select(RoadmapRecord).where(RoadmapRecord.resume_id == rec.id)
    if role:
        q = q.where(RoadmapRecord.role == role)
    row = db.scalars(q.order_by(RoadmapRecord.created_at.desc())).first()
    return _to_model(row) if row else None


@router.patch("/roadmaps/{roadmap_id}/progress", response_model=Roadmap, summary="Mark a stage complete/incomplete")
def update_progress(roadmap_id: int, upd: ProgressUpdate, sid: str = Depends(session_id), db: Session = Depends(get_db)) -> Roadmap:
    row = db.get(RoadmapRecord, roadmap_id)
    if row is None or row.resume.session_id != sid:
        raise HTTPException(status_code=404, detail="Roadmap not found for this session.")
    n_stages = len(row.roadmap_json["stages"])
    if not 0 <= upd.stage_index < n_stages:
        raise HTTPException(status_code=400, detail=f"stage_index must be in [0, {n_stages - 1}]")
    done = set(row.completed_stages or [])
    (done.add if upd.completed else done.discard)(upd.stage_index)
    row.completed_stages = sorted(done)
    db.commit()
    db.refresh(row)
    return _to_model(row)
