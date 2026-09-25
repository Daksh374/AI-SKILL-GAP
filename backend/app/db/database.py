"""SQLAlchemy engine/session setup and ORM models (SQLite by default)."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from backend.app.config import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ResumeRecord(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    raw_text: Mapped[str] = mapped_column(Text)
    profile_json: Mapped[dict] = mapped_column(JSON)
    predictions_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    roadmaps: Mapped[list["RoadmapRecord"]] = relationship(back_populates="resume", cascade="all, delete-orphan")


class RoadmapRecord(Base):
    __tablename__ = "roadmaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(100))
    hours_per_week: Mapped[int] = mapped_column(Integer)
    roadmap_json: Mapped[dict] = mapped_column(JSON)
    completed_stages: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    resume: Mapped[ResumeRecord] = relationship(back_populates="roadmaps")


class MarketReportRecord(Base):
    __tablename__ = "market_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    role: Mapped[str] = mapped_column(String(100), index=True)
    report_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SearchCacheRecord(Base):
    """Caches raw Tavily responses to respect rate limits. Only successful, real responses are stored."""

    __tablename__ = "search_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    query: Mapped[str] = mapped_column(Text)
    params_json: Mapped[dict] = mapped_column(JSON)
    response_json: Mapped[dict] = mapped_column(JSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


_settings = get_settings()
engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
