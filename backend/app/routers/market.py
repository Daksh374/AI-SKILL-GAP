"""Market-intelligence and learning-resource endpoints (Tavily proxied server-side)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.database import MarketReportRecord, ResumeRecord, get_db
from backend.app.knowledge import get_kb
from backend.app.routers.deps import profile_of, session_id
from backend.app.schemas import MarketIntelligence, MarketRequest, SkillResources
from backend.app.services.market import get_market_intelligence
from backend.app.services.resources import find_resources_for_skill

router = APIRouter(prefix="/api", tags=["market"])
REPORT_REUSE_HOURS = 12


@router.post("/market", response_model=MarketIntelligence, summary="Live market intelligence for a role (Tavily)")
async def market(req: MarketRequest, sid: str = Depends(session_id), db: Session = Depends(get_db)) -> MarketIntelligence:
    if req.role not in get_kb().roles:
        raise HTTPException(status_code=400, detail=f"Unknown role '{req.role}'.")
    candidate: set[str] = set()
    if req.resume_id is not None:
        rec = db.get(ResumeRecord, req.resume_id)
        if rec is None or rec.session_id != sid:
            raise HTTPException(status_code=404, detail="Resume not found for this session.")
        candidate = set(profile_of(rec).all_skill_names)

    if not req.refresh:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=REPORT_REUSE_HOURS)
        prev = db.scalars(select(MarketReportRecord).where(MarketReportRecord.session_id == sid, MarketReportRecord.role == req.role)
                          .order_by(MarketReportRecord.created_at.desc())).first()
        if prev and (prev.created_at if prev.created_at.tzinfo else prev.created_at.replace(tzinfo=timezone.utc)) > cutoff \
                and prev.report_json.get("status") in {"ok", "partial"}:
            report = MarketIntelligence.model_validate(prev.report_json)
            for m in report.skill_mentions:
                m.candidate_has = m.skill in candidate
            return report

    report = await get_market_intelligence(req.role, candidate)
    if report.status in {"ok", "partial"}:
        db.add(MarketReportRecord(session_id=sid, resume_id=req.resume_id, role=req.role, report_json=report.model_dump(mode="json")))
        db.commit()
    return report


@router.get("/resources", response_model=SkillResources, summary="YouTube + Coursera resources for one skill (Tavily)")
async def resources(skill: str = Query(..., min_length=1, max_length=80)) -> SkillResources:
    kb = get_kb()
    canonical = next((s for s in kb.skills if s.lower() == skill.strip().lower()), None)
    if canonical is None:
        raise HTTPException(status_code=400, detail=f"'{skill}' is not a skill in the taxonomy.")
    return await find_resources_for_skill(canonical)
