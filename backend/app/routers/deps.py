"""Shared FastAPI dependencies."""
from __future__ import annotations

import hashlib
import hmac
import re

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db.database import ResumeRecord, get_db
from backend.app.schemas import CandidateProfile

_SESSION_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def session_id(x_session_id: str = Header(..., description="Client-generated anonymous session id (UUID)")) -> str:
    """Validate the client session id and return its keyed hash (raw ids are never stored)."""
    if not _SESSION_RE.match(x_session_id):
        raise HTTPException(status_code=400, detail="Invalid X-Session-ID header.")
    key = get_settings().secret_key.encode()
    if key:
        return hmac.new(key, x_session_id.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(x_session_id.encode()).hexdigest()


def get_resume(resume_id: int, sid: str = Depends(session_id), db: Session = Depends(get_db)) -> ResumeRecord:
    rec = db.get(ResumeRecord, resume_id)
    if rec is None or rec.session_id != sid:
        raise HTTPException(status_code=404, detail="Resume not found for this session.")
    return rec


def profile_of(rec: ResumeRecord) -> CandidateProfile:
    return CandidateProfile.model_validate(rec.profile_json)
