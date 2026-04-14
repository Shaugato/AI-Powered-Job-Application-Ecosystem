from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None


def vector_column(dimensions: int) -> Mapped[list[float] | None]:
    if Vector is not None:
        return mapped_column(Vector(dimensions), nullable=True)
    return mapped_column(JSON, nullable=True)


class SourceName(str, enum.Enum):
    SEEK = "seek"
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    APSJOBS = "apsjobs"
    CAREERS_VIC = "careers_vic"
    COMPANY_PORTAL = "company_portal"


class TruthStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FragmentType(str, enum.Enum):
    BULLET = "bullet"
    SUMMARY = "summary"
    PROJECT = "project"
    COVER_PARAGRAPH = "cover_paragraph"
    PROMPT = "prompt"
    SKILL = "skill"


class SourceAssetKind(str, enum.Enum):
    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    PROMPT = "prompt"
    DOCUMENT = "document"


class StructuredSectionType(str, enum.Enum):
    IDENTITY = "identity"
    SUMMARY = "summary"
    TECHNICAL_SKILL = "technical_skill"
    EXPERIENCE = "experience"
    PROJECT = "project"
    CERTIFICATION = "certification"
    EDUCATION = "education"
    COVER_LETTER_BODY = "cover_letter_body"
    PROMPT_LOGIC = "prompt_logic"


class ApplicationMode(str, enum.Enum):
    AUTO_SUBMIT = "AUTO_SUBMIT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class ApplicationStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    GENERATED = "generated"
    PLANNED = "planned"
    REVIEW_REQUIRED = "review_required"
    SUBMITTED = "submitted"
    FAILED = "failed"
    BLOCKED = "blocked"


class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_REVIEW = "waiting_for_review"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionRunStatus(str, enum.Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class OutcomeResponseType(str, enum.Enum):
    REJECT = "reject"
    INTERVIEW = "interview"
    NO_RESPONSE = "no_response"
    WITHDRAWN = "withdrawn"
    OTHER = "other"


class PipelineEntityType(str, enum.Enum):
    ASSET = "asset"
    PROFILE = "profile"
    JOB = "job"
    FIT = "fit"
    GENERATION = "generation"
    APPLICATION = "application"


class PipelineStageName(str, enum.Enum):
    FILE_INTAKE = "file_intake"
    DOCLING_CONVERSION = "docling_conversion"
    PAGE_RENDERING = "page_rendering"
    LAYOUT_ZONING = "layout_zoning"
    STRUCTURED_EXTRACTION = "structured_extraction"
    PROFILE_FUSION = "profile_fusion"
    JOB_UNDERSTANDING = "job_understanding"
    EVIDENCE_PACK = "evidence_pack"
    TAILORING = "tailoring"
    LAYOUT_PLANNING = "layout_planning"
    VERIFICATION = "verification"
    RENDER = "render"
    REPAIR = "repair"


class ReviewQueueStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReviewQueueReason(str, enum.Enum):
    LOW_CONFIDENCE_EXTRACTION = "low_confidence_extraction"
    LAYOUT_AMBIGUITY = "layout_ambiguity"
    VERIFIER_FAILURE = "verifier_failure"
    REPAIR_EXHAUSTED = "repair_exhausted"
    MERGE_CONFLICT = "merge_conflict"


class BaseRecord(Base):
    __abstract__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BaseProfile(BaseRecord):
    __tablename__ = "base_profiles"

    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    certifications_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    experience_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    projects_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    education_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CandidateMemoryProfile(BaseRecord):
    __tablename__ = "candidate_memory_profiles"

    base_profile_id: Mapped[str | None] = mapped_column(ForeignKey("base_profiles.id"), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_signals_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_locations_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    certifications_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class SourceAsset(BaseRecord):
    __tablename__ = "source_assets"

    source_document: Mapped[str] = mapped_column(String(500), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    asset_kind: Mapped[SourceAssetKind] = mapped_column(Enum(SourceAssetKind), default=SourceAssetKind.DOCUMENT)
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    parse_status: Mapped[str] = mapped_column(String(50), default="parsed")
    parser_version: Mapped[str] = mapped_column(String(50), default="v1")
    library_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    library_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class StructuredSection(BaseRecord):
    __tablename__ = "structured_sections"

    asset_id: Mapped[str] = mapped_column(ForeignKey("source_assets.id"), index=True)
    section_type: Mapped[StructuredSectionType] = mapped_column(Enum(StructuredSectionType), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_text: Mapped[str] = mapped_column(Text)
    body_lines_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    role_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_spans_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    canonical_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provenance_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence_lineage_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class MemoryEmbedding(BaseRecord):
    __tablename__ = "memory_embeddings"

    structured_section_id: Mapped[str] = mapped_column(ForeignKey("structured_sections.id"), unique=True, index=True)
    embedding: Mapped[list[float] | None] = vector_column(3072)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PipelineStageRecord(BaseRecord):
    __tablename__ = "pipeline_stage_records"

    entity_type: Mapped[PipelineEntityType] = mapped_column(Enum(PipelineEntityType), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    stage_name: Mapped[PipelineStageName] = mapped_column(Enum(PipelineStageName), index=True)
    stage_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    provenance_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    validation_result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    repair_hints_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ambiguity_flags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PlatformUser(BaseRecord):
    __tablename__ = "platform_users"

    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PlatformSession(BaseRecord):
    __tablename__ = "platform_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("platform_users.id"))
    session_token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class RoleTaxonomy(BaseRecord):
    __tablename__ = "role_taxonomy"

    domain_name: Mapped[str] = mapped_column(String(120), unique=True)
    priority_weight: Mapped[float] = mapped_column(Float, default=1.0)
    aliases_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    parent_role_id: Mapped[str | None] = mapped_column(ForeignKey("role_taxonomy.id"), nullable=True)


class PromptVersion(BaseRecord):
    __tablename__ = "prompt_versions"

    name: Mapped[str] = mapped_column(String(255))
    role_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    prompt_text: Mapped[str] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    success_rate_metric: Mapped[float] = mapped_column(Float, default=0.0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TemplateVariant(BaseRecord):
    __tablename__ = "template_variants"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    document_kind: Mapped[str] = mapped_column(String(50))
    template_path: Mapped[str] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class SearchProfile(BaseRecord):
    __tablename__ = "search_profiles"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    roles_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_terms_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    locations_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    remote_policy: Mapped[str] = mapped_column(String(50), default="hybrid")
    salary_floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_allowlist_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    daily_cap: Mapped[int] = mapped_column(Integer, default=15)
    review_policy: Mapped[str] = mapped_column(String(50), default="mixed")
    schedule_window_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    @property
    def roles(self) -> list[str]:
        return self.roles_json

    @property
    def keywords(self) -> list[str]:
        return self.keywords_json

    @property
    def excluded_terms(self) -> list[str]:
        return self.excluded_terms_json

    @property
    def locations(self) -> list[str]:
        return self.locations_json

    @property
    def source_allowlist(self) -> list[str]:
        return self.source_allowlist_json

    @property
    def schedule_window(self) -> dict[str, Any] | None:
        return self.schedule_window_json


class EvidenceFragment(BaseRecord):
    __tablename__ = "evidence_fragments"

    source_document: Mapped[str] = mapped_column(String(500))
    fragment_type: Mapped[FragmentType] = mapped_column(Enum(FragmentType))
    role_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    seniority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    certifications_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    truth_status: Mapped[TruthStatus] = mapped_column(Enum(TruthStatus), default=TruthStatus.PENDING)
    success_weight: Mapped[float] = mapped_column(Float, default=1.0)
    payload_text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float] | None] = vector_column(3072)


class NormalizedJobPosting(BaseRecord):
    __tablename__ = "job_postings"

    source: Mapped[SourceName] = mapped_column(Enum(SourceName))
    external_id: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(String(1000))
    company: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description_text: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    classification_labels_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    eligibility_flags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_flags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    dedupe_fingerprint: Mapped[str] = mapped_column(String(255), index=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float] | None] = vector_column(3072)


class OpportunityFit(BaseRecord):
    __tablename__ = "opportunity_fits"

    job_id: Mapped[str] = mapped_column(ForeignKey("job_postings.id"), index=True)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_memory_profiles.id"), nullable=True)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    component_scores_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    matched_section_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_signals_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    explanation_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    requirement_profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rerank_scores_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class GenerationRequest(BaseRecord):
    __tablename__ = "generation_requests"

    job_id: Mapped[str] = mapped_column(ForeignKey("job_postings.id"))
    prompt_version_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    template_variant_id: Mapped[str | None] = mapped_column(ForeignKey("template_variants.id"), nullable=True)
    selected_evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    request_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), default="queued")

    job: Mapped[NormalizedJobPosting] = relationship()


class ResumeCompositionPlan(BaseRecord):
    __tablename__ = "resume_composition_plans"

    job_id: Mapped[str] = mapped_column(ForeignKey("job_postings.id"), index=True)
    generation_request_id: Mapped[str | None] = mapped_column(ForeignKey("generation_requests.id"), nullable=True, unique=True)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_memory_profiles.id"), nullable=True)
    fit_id: Mapped[str | None] = mapped_column(ForeignKey("opportunity_fits.id"), nullable=True)
    selected_section_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_section_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    section_order_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    section_budget_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_lines: Mapped[int] = mapped_column(Integer, default=0)
    line_budget: Mapped[int] = mapped_column(Integer, default=52)
    trim_decisions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_pack_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    layout_blueprint_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rendered_metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verification_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    repair_loop_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    composition_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class GenerationResult(BaseRecord):
    __tablename__ = "generation_results"

    request_id: Mapped[str] = mapped_column(ForeignKey("generation_requests.id"), unique=True)
    composition_plan_id: Mapped[str | None] = mapped_column(ForeignKey("resume_composition_plans.id"), nullable=True)
    resume_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    cover_letter_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    qa_scores_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    compile_status: Mapped[str] = mapped_column(String(50), default="pending")
    resume_tex_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resume_pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_tex_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_html_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    selected_section_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_section_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    verifier_output_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    repair_attempts_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    stage_status_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    grounding_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SubmissionPreview(BaseRecord):
    __tablename__ = "submission_previews"

    generation_result_id: Mapped[str] = mapped_column(ForeignKey("generation_results.id"), unique=True)
    application_plan_id: Mapped[str | None] = mapped_column(ForeignKey("application_plans.id"), nullable=True)
    html_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_required: Mapped[bool] = mapped_column(Boolean, default=True)
    selected_section_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    composition_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verification_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ReviewQueueItem(BaseRecord):
    __tablename__ = "review_queue_items"

    reason: Mapped[ReviewQueueReason] = mapped_column(Enum(ReviewQueueReason), index=True)
    status: Mapped[ReviewQueueStatus] = mapped_column(Enum(ReviewQueueStatus), default=ReviewQueueStatus.OPEN, index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("source_assets.id"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("job_postings.id"), nullable=True)
    generation_result_id: Mapped[str | None] = mapped_column(ForeignKey("generation_results.id"), nullable=True)
    stage_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApplicationPlan(BaseRecord):
    __tablename__ = "application_plans"

    job_id: Mapped[str] = mapped_column(ForeignKey("job_postings.id"))
    generation_result_id: Mapped[str] = mapped_column(ForeignKey("generation_results.id"))
    source_adapter: Mapped[str] = mapped_column(String(120))
    mode: Mapped[ApplicationMode] = mapped_column(Enum(ApplicationMode))
    field_map_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    fit_reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    approval_state: Mapped[str] = mapped_column(String(50), default="pending")
    notification_state: Mapped[str] = mapped_column(String(50), default="queued")
    preview_required: Mapped[bool] = mapped_column(Boolean, default=True)
    source_policy: Mapped[str] = mapped_column(String(80), default="review_before_apply")
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    terminal_status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus), default=ApplicationStatus.PLANNED)


class ApplicationRun(BaseRecord):
    __tablename__ = "application_runs"

    plan_id: Mapped[str] = mapped_column(ForeignKey("application_plans.id"))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.QUEUED)
    execution_log_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    uploaded_artifacts_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    result_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class NotificationEvent(BaseRecord):
    __tablename__ = "notification_events"

    channel: Mapped[str] = mapped_column(String(50))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(50), default="queued")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class NotificationPreference(BaseRecord):
    __tablename__ = "notification_preferences"

    channel: Mapped[str] = mapped_column(String(50), unique=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class IngestionSourceConfig(BaseRecord):
    __tablename__ = "ingestion_source_configs"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    search_profile_id: Mapped[str | None] = mapped_column(ForeignKey("search_profiles.id"), nullable=True)
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("integration_connections.id"), nullable=True)
    source: Mapped[SourceName] = mapped_column(Enum(SourceName))
    enabled: Mapped[bool] = mapped_column(default=True)
    cadence_minutes: Mapped[int] = mapped_column(Integer, default=60)
    query_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location_override: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_results: Mapped[int] = mapped_column(Integer, default=20)
    auto_start_pipeline: Mapped[bool] = mapped_column(default=True)
    search_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class IngestionRun(BaseRecord):
    __tablename__ = "ingestion_runs"

    config_id: Mapped[str] = mapped_column(ForeignKey("ingestion_source_configs.id"))
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[IngestionRunStatus] = mapped_column(Enum(IngestionRunStatus), default=IngestionRunStatus.QUEUED)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    pipeline_triggered_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ApplicationOutcome(BaseRecord):
    __tablename__ = "application_outcomes"

    application_plan_id: Mapped[str] = mapped_column(ForeignKey("application_plans.id"))
    application_run_id: Mapped[str | None] = mapped_column(ForeignKey("application_runs.id"), nullable=True)
    generation_result_id: Mapped[str | None] = mapped_column(ForeignKey("generation_results.id"), nullable=True)
    prompt_version_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    response_type: Mapped[OutcomeResponseType] = mapped_column(Enum(OutcomeResponseType))
    interview: Mapped[bool] = mapped_column(default=False)
    response_time_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome_source: Mapped[str] = mapped_column(String(50), default="manual")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PromptPerformance(BaseRecord):
    __tablename__ = "prompt_performance"

    prompt_version_id: Mapped[str] = mapped_column(ForeignKey("prompt_versions.id"))
    role_tag: Mapped[str] = mapped_column(String(120), default="all")
    applications_count: Mapped[int] = mapped_column(Integer, default=0)
    interviews_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_response_time_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ResumeVariantScore(BaseRecord):
    __tablename__ = "resume_variant_scores"

    generation_result_id: Mapped[str] = mapped_column(ForeignKey("generation_results.id"), unique=True)
    role_tag: Mapped[str | None] = mapped_column(String(120), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    keyword_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    hallucination_risk: Mapped[float] = mapped_column(Float, default=0.0)
    interview_rate_proxy: Mapped[float] = mapped_column(Float, default=0.0)
    manual_edit_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class IntegrationConnection(BaseRecord):
    __tablename__ = "integration_connections"

    name: Mapped[str] = mapped_column(String(255))
    provider_key: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(50))
    auth_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="disconnected")
    login_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    settings_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    secrets_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    scopes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
