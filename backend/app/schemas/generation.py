from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.common import ORMModel


class GenerationRequestCreate(BaseModel):
    job_id: str
    template_variant_name: str = "default-resume"
    cover_template_variant_name: str = "default-cover-letter"
    force_regenerate: bool = False


class TemplateVariantCreate(BaseModel):
    name: str
    document_kind: str
    template_path: str
    metadata_json: dict[str, Any] | None = None


class TemplateVariantRead(ORMModel):
    id: str
    name: str
    document_kind: str
    template_path: str
    metadata_json: dict[str, Any] | None


class GeneratedDocument(BaseModel):
    identity: dict[str, str | None] = Field(default_factory=dict)
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    page_plan: dict[str, Any] = Field(default_factory=dict)


class GenerationResultRead(ORMModel):
    id: str
    request_id: str
    composition_plan_id: str | None
    resume_json: dict[str, Any] = Field(default_factory=dict)
    cover_letter_json: dict[str, Any] = Field(default_factory=dict)
    qa_scores_json: dict[str, Any] = Field(default_factory=dict)
    compile_status: str
    resume_tex_path: str | None
    resume_pdf_path: str | None
    cover_tex_path: str | None
    cover_pdf_path: str | None
    preview_html_path: str | None
    preview_pdf_path: str | None
    selected_section_ids_json: list[str] = Field(default_factory=list)
    excluded_section_ids_json: list[str] = Field(default_factory=list)
    fit_score: float = 0.0
    verifier_output_json: dict[str, Any] = Field(default_factory=dict)
    repair_attempts_json: list[dict[str, Any]] = Field(default_factory=list)
    stage_status_json: dict[str, Any] = Field(default_factory=dict)
    composition_plan_json: dict[str, Any] = Field(default_factory=dict)
    evidence_pack_json: list[dict[str, Any]] = Field(default_factory=list)
    layout_blueprint_json: dict[str, Any] = Field(default_factory=dict)
    rendered_metrics_json: dict[str, Any] = Field(default_factory=dict)
    verification_json: dict[str, Any] = Field(default_factory=dict)
    rewrite_provenance_json: dict[str, Any] = Field(default_factory=dict)
    grounding_notes: str | None


class GenerationWorkflowResponse(BaseModel):
    accepted: bool = True
    workflow_id: str
    workflow_status: str
    result: GenerationResultRead | None = None
    error: str | None = None
