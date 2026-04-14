from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.review_queue import ReviewQueueItemRead, ReviewQueueResolveRequest
from backend.app.services.review_queue import ReviewQueueService

router = APIRouter(prefix="/review-queue", tags=["review-queue"])


@router.get("", response_model=list[ReviewQueueItemRead])
def list_review_queue(db: Session = Depends(get_db)):
    return ReviewQueueService(db).open_items()


@router.post("/{item_id}/resolve", response_model=ReviewQueueItemRead)
def resolve_review_item(item_id: str, payload: ReviewQueueResolveRequest, db: Session = Depends(get_db)):
    item = ReviewQueueService(db).resolve(item_id, resolution_notes=payload.resolution_notes, dismissed=payload.dismissed)
    if item is None:
        raise HTTPException(status_code=404, detail="Review queue item not found")
    db.commit()
    db.refresh(item)
    return item
