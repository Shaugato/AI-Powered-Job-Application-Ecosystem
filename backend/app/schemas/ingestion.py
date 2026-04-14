from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from backend.app.models.entities import IngestionRunStatus, SourceName
from backend.app.schemas.common import ORMModel


class IngestionSourceConfigCreate(BaseModel):
    name: str
    search_profile_id: str | None = None
    connection_id: str | None = None
    source: SourceName
    enabled: bool = True
    cadence_minutes: int = 60
    query_text: str | None = None
    location_override: str | None = None
    max_results: int = 20
    auto_start_pipeline: bool = True
    search_url: HttpUrl | None = None
    metadata_json: dict[str, Any] | None = None


class IngestionSourceConfigRead(ORMModel):
    id: str
    name: str
    search_profile_id: str | None
    connection_id: str | None
    source: SourceName
    enabled: bool
    cadence_minutes: int
    query_text: str | None
    location_override: str | None
    max_results: int
    auto_start_pipeline: bool
    search_url: str | None
    last_cursor: str | None
    last_run_at: datetime | None
    metadata_json: dict[str, Any] | None


class IngestionRunRead(ORMModel):
    id: str
    config_id: str
    workflow_id: str | None
    status: IngestionRunStatus
    discovered_count: int
    ingested_count: int
    duplicate_count: int
    pipeline_triggered_count: int
    error_message: str | None
    metadata_json: dict[str, Any] | None


class IngestionTriggerRequest(BaseModel):
    config_id: str
    iterations: int = Field(default=1, ge=1, le=100)
    continuous: bool = False
