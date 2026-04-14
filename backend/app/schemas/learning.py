from datetime import datetime
from typing import Any

from pydantic import BaseModel

from backend.app.models.entities import OutcomeResponseType
from backend.app.schemas.common import ORMModel


class ApplicationOutcomeCreate(BaseModel):
    application_plan_id: str
    application_run_id: str | None = None
    response_type: OutcomeResponseType
    interview: bool = False
    response_time_days: float | None = None
    outcome_source: str = "manual"
    notes: str | None = None
    metadata_json: dict[str, Any] | None = None
    outcome_at: datetime | None = None


class ApplicationOutcomeRead(ORMModel):
    id: str
    application_plan_id: str
    application_run_id: str | None
    generation_result_id: str | None
    prompt_version_id: str | None
    response_type: OutcomeResponseType
    interview: bool
    response_time_days: float | None
    outcome_source: str
    notes: str | None
    metadata_json: dict[str, Any] | None
    outcome_at: datetime | None


class PromptPerformanceRead(ORMModel):
    id: str
    prompt_version_id: str
    role_tag: str
    applications_count: int
    interviews_count: int
    success_rate: float
    avg_response_time_days: float | None
    last_outcome_at: datetime | None
    metadata_json: dict[str, Any] | None


class ResumeVariantScoreRead(ORMModel):
    id: str
    generation_result_id: str
    role_tag: str | None
    score: float
    keyword_coverage: float
    hallucination_risk: float
    interview_rate_proxy: float
    manual_edit_distance: float | None
    metadata_json: dict[str, Any] | None


class LearningSignalRead(BaseModel):
    source: str
    signal_type: str
    related_id: str | None = None
    status: str | None = None
    summary: str
    details_json: dict[str, Any] = {}
