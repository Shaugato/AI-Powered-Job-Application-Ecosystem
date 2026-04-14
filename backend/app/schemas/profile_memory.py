from pydantic import BaseModel, Field
from typing import Any


class CandidateMemoryEntry(BaseModel):
    title: str
    subtitle: str | None = None
    bullets: list[str] = Field(default_factory=list)
    source_document: str | None = None
    confidence: float = 0.0


class CandidateMemoryRead(BaseModel):
    source_profile_id: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    experience: list[CandidateMemoryEntry] = Field(default_factory=list)
    projects: list[CandidateMemoryEntry] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    approved_documents: int = 0
    pending_documents: int = 0
    source_documents: list[str] = Field(default_factory=list)


class MemoryProfileRead(BaseModel):
    profile_id: str | None = None
    identity: dict[str, str | None] = Field(default_factory=dict)
    summary: str | None = None
    role_signals: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    asset_count: int = 0
    section_counts: dict[str, int] = Field(default_factory=dict)
    readiness: dict[str, bool] = Field(default_factory=dict)
    review_queue_open: int = 0
    needs_review_assets: int = 0
    average_parsing_confidence: float = 0.0
    provenance_summary: dict[str, Any] = Field(default_factory=dict)


class CandidateMemorySyncRequest(BaseModel):
    profile_id: str | None = None
    overwrite_summary: bool = False
