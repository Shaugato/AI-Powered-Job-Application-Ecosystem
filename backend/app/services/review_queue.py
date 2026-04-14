from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.entities import ReviewQueueItem, ReviewQueueReason, ReviewQueueStatus


class ReviewQueueService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(
        self,
        *,
        reason: ReviewQueueReason,
        summary: str,
        confidence: float,
        details: dict[str, Any] | None = None,
        asset_id: str | None = None,
        job_id: str | None = None,
        generation_result_id: str | None = None,
        stage_name: str | None = None,
    ) -> ReviewQueueItem:
        item = ReviewQueueItem(
            reason=reason,
            status=ReviewQueueStatus.OPEN,
            asset_id=asset_id,
            job_id=job_id,
            generation_result_id=generation_result_id,
            stage_name=stage_name,
            confidence=float(confidence or 0.0),
            summary=summary,
            details_json=details or {},
        )
        self.db.add(item)
        self.db.flush()
        return item

    def open_items(self) -> list[ReviewQueueItem]:
        return (
            self.db.query(ReviewQueueItem)
            .filter(ReviewQueueItem.status == ReviewQueueStatus.OPEN)
            .order_by(ReviewQueueItem.created_at.desc())
            .all()
        )

    def resolve(self, item_id: str, *, resolution_notes: str | None = None, dismissed: bool = False) -> ReviewQueueItem | None:
        item = self.db.query(ReviewQueueItem).filter(ReviewQueueItem.id == item_id).first()
        if item is None:
            return None
        item.status = ReviewQueueStatus.DISMISSED if dismissed else ReviewQueueStatus.RESOLVED
        item.resolution_notes = resolution_notes
        item.resolved_at = datetime.now(timezone.utc)
        self.db.add(item)
        self.db.flush()
        return item
