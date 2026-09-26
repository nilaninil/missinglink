from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database.db import Base


def _now():
    return datetime.now()


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # police|hospital|shelter|ngo|investigator|public
    locality: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class MissingCase(Base):
    __tablename__ = "missing_cases"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_seen_locality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_seen_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    clothing_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    photo_quality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    photo_warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    occupation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reporting_org_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    sync_status: Mapped[str] = mapped_column(String, default="synced")


class FoundRecord(Base):
    __tablename__ = "found_records"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    record_type: Mapped[str] = mapped_column(String, default="found")
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    locality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    care_location_detail: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    found_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    clothing_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    photo_quality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    photo_warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    occupation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_org_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    sync_status: Mapped[str] = mapped_column(String, default="synced")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    evidence_type: Mapped[str] = mapped_column(String)
    source_org_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    observed_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    locality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    clothing_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    linked_record_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    needs_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    sync_status: Mapped[str] = mapped_column(String, default="synced")


class CCTVSighting(Base):
    __tablename__ = "cctv_sightings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    camera_name: Mapped[str] = mapped_column(String)
    locality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    frame_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    frame_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    crop_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    visual_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    matched_record_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    added_to_timeline: Mapped[bool] = mapped_column(Boolean, default=False)


class BodyScan(Base):
    __tablename__ = "body_scans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reference_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    scan_path: Mapped[str] = mapped_column(String)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    band: Mapped[str] = mapped_column(String, default="")
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attached_record_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class MatchResult(Base):
    __tablename__ = "match_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    record_id: Mapped[str] = mapped_column(String)
    run_id: Mapped[int] = mapped_column(Integer)
    rank: Mapped[int] = mapped_column(Integer)
    overall_score: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String)
    factor_json: Mapped[str] = mapped_column(Text)
    coverage: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    org_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ReviewFlag(Base):
    __tablename__ = "review_flags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String)
    record_id: Mapped[str] = mapped_column(String)
    flagged_by_role: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String, default="needs_review")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FaissMap(Base):
    __tablename__ = "faiss_map"
    embedding_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String)  # found_record | missing_case
    entity_id: Mapped[str] = mapped_column(String)
