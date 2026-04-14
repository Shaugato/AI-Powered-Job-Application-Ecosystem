from typing import Any

from pydantic import BaseModel, Field

from backend.app.models.entities import FragmentType, TruthStatus
from backend.app.schemas.common import ORMModel


class CorpusIngestRequest(BaseModel):
    path: str
    role_hint: list[str] = Field(default_factory=list)
    source_document_glob: str = "**/*"
    document_kind_override: str | None = None


class CorpusIngestResponse(BaseModel):
    ingested_documents: int
    created_fragments: int
    created_prompts: int
    warnings: list[str] = Field(default_factory=list)
    source_documents: list[str] = Field(default_factory=list)
    auto_approved_documents: int = 0
    profile_id: str | None = None
    profile_updated: bool = False
    created_asset_ids: list[str] = Field(default_factory=list)
    created_section_count: int = 0
    library_keys: list[str] = Field(default_factory=list)
    stage_statuses: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parsing_confidence: float = 0.0
    ambiguity_flags: list[str] = Field(default_factory=list)
    review_queue_item_ids: list[str] = Field(default_factory=list)
    created_library_manifest: dict[str, Any] = Field(default_factory=dict)


class CorpusIngestWorkflowResponse(BaseModel):
    accepted: bool = True
    workflow_id: str
    workflow_status: str
    result: CorpusIngestResponse | None = None
    error: str | None = None


class CorpusLegacyCleanupResponse(BaseModel):
    removed_asset_ids: list[str] = Field(default_factory=list)
    removed_library_keys: list[str] = Field(default_factory=list)
    removed_source_documents: list[str] = Field(default_factory=list)
    removed_generation_result_ids: list[str] = Field(default_factory=list)
    removed_application_plan_ids: list[str] = Field(default_factory=list)
    removed_application_run_ids: list[str] = Field(default_factory=list)
    removed_section_ids: list[str] = Field(default_factory=list)
    removed_request_ids: list[str] = Field(default_factory=list)
    removed_fit_ids: list[str] = Field(default_factory=list)
    reasons_by_asset: dict[str, list[str]] = Field(default_factory=dict)


class EvidenceFragmentRead(ORMModel):
    id: str
    source_document: str
    fragment_type: FragmentType
    role_tags_json: list[str] = Field(default_factory=list)
    seniority: str | None
    skills_json: list[str] = Field(default_factory=list)
    certifications_json: list[str] = Field(default_factory=list)
    truth_status: TruthStatus
    success_weight: float
    payload_text: str
    metadata_json: dict[str, Any] | None


class TruthApprovalRequest(BaseModel):
    approved: bool
    reviewer_notes: str | None = None


class SourceDocumentApprovalRequest(BaseModel):
    source_document: str
    approved: bool = True
    reviewer_notes: str | None = None


class SourceDocumentApprovalResponse(BaseModel):
    source_document: str
    updated_fragments: int
    truth_status: TruthStatus


class LibraryFileRead(BaseModel):
    name: str
    path: str | None = None
    title: str | None = None
    subtitle: str | None = None
    lines: list[str] = Field(default_factory=list)
    preview_excerpt: str | None = None


class LibrarySectionRead(BaseModel):
    key: str
    title: str
    file_count: int
    files: list[LibraryFileRead] = Field(default_factory=list)


class CorpusDocumentSummaryRead(BaseModel):
    source_document: str
    display_name: str
    document_kind: str
    fragment_count: int
    pending_count: int
    approved_count: int
    rejected_count: int
    fragment_types: list[str] = Field(default_factory=list)
    role_tags: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    preview_excerpt: str | None = None
    library_key: str | None = None
    folder_name: str | None = None
    library_path: str | None = None
    status: str = "learned"
    parsing_confidence: float = 0.0
    ambiguity_flags: list[str] = Field(default_factory=list)
    review_required: bool = False
    provenance_summary: dict[str, Any] = Field(default_factory=dict)
    stage_statuses: dict[str, Any] = Field(default_factory=dict)
    section_counts: dict[str, int] = Field(default_factory=dict)
    sections: list[LibrarySectionRead] = Field(default_factory=list)
    asset_id: str | None = None
