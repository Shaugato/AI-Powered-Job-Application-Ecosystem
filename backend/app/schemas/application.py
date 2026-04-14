from typing import Any

from pydantic import BaseModel, Field

from backend.app.models.entities import ApplicationMode, ApplicationStatus, RunStatus
from backend.app.schemas.common import ORMModel


class ApplicationPlanCreate(BaseModel):
    job_id: str
    generation_result_id: str


class ApplicationPlanRead(ORMModel):
    id: str
    job_id: str
    generation_result_id: str
    source_adapter: str
    mode: ApplicationMode
    field_map_json: dict[str, Any] = Field(default_factory=dict)
    risk_reasons_json: list[str] = Field(default_factory=list)
    fit_reasons_json: list[str] = Field(default_factory=list)
    approval_state: str
    notification_state: str
    preview_required: bool = True
    source_policy: str = "review_before_apply"
    fit_score: float = 0.0
    terminal_status: ApplicationStatus


class ApplicationRunRead(ORMModel):
    id: str
    plan_id: str
    status: RunStatus
    execution_log_json: list[dict[str, Any]] = Field(default_factory=list)
    uploaded_artifacts_json: list[str] = Field(default_factory=list)
    result_payload_json: dict[str, Any] | None


class ApplicationRunStartRequest(BaseModel):
    plan_id: str


class ApplicationPreviewRead(BaseModel):
    application_plan_id: str
    generation_result_id: str | None = None
    html_path: str | None = None
    pdf_path: str | None = None
    preview_required: bool = True
    selected_section_ids_json: list[str] = Field(default_factory=list)
    composition_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    verification_metadata_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
