from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from backend.app.models.entities import SourceName
from backend.app.schemas.common import ORMModel


class NormalizedJobPostingBase(BaseModel):
    source: SourceName
    external_id: str
    source_url: HttpUrl
    company: str
    title: str
    location: str | None = None
    work_mode: str | None = None
    description_text: str
    posted_at: datetime | None = None
    classification_labels: list[str] = Field(default_factory=list)
    eligibility_flags: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] | None = None


class NormalizedJobPostingCreate(NormalizedJobPostingBase):
    pass


class NormalizedJobPostingRead(ORMModel):
    id: str
    source: SourceName
    external_id: str
    source_url: str
    company: str
    title: str
    location: str | None
    work_mode: str | None
    description_text: str
    posted_at: datetime | None
    classification_labels_json: list[str]
    eligibility_flags_json: list[str]
    risk_flags_json: list[str]
    dedupe_fingerprint: str
    metadata_json: dict[str, Any] | None


class SourceHealth(BaseModel):
    source: str
    auto_submit_certified: bool
    monitoring_enabled: bool
    status: str
    notes: list[str]


class OpportunityFitRead(BaseModel):
    job_id: str
    fit_score: float
    component_scores: dict[str, Any] = Field(default_factory=dict)
    matched_section_ids: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    requirement_profile: dict[str, Any] = Field(default_factory=dict)
    rerank_scores: list[dict[str, Any]] = Field(default_factory=list)
    evidence_pack: list[dict[str, Any]] = Field(default_factory=list)
