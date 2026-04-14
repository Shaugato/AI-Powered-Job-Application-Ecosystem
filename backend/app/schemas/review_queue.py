from typing import Any

from pydantic import BaseModel, Field

from backend.app.models.entities import ReviewQueueReason, ReviewQueueStatus
from backend.app.schemas.common import ORMModel


class ReviewQueueItemRead(ORMModel):
    id: str
    reason: ReviewQueueReason
    status: ReviewQueueStatus
    asset_id: str | None
    job_id: str | None
    generation_result_id: str | None
    stage_name: str | None
    confidence: float = 0.0
    summary: str
    details_json: dict[str, Any] = Field(default_factory=dict)
    resolution_notes: str | None = None


class ReviewQueueResolveRequest(BaseModel):
    resolution_notes: str | None = None
    dismissed: bool = False
