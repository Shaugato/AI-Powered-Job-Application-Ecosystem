from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import NotificationEvent, NotificationPreference
from backend.app.schemas.notifications import (
    NotificationEventRead,
    NotificationPreferenceCreate,
    NotificationPreferenceRead,
    NotificationTestRequest,
)
from backend.app.services.notifications import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/events", response_model=list[NotificationEventRead])
def list_notification_events(db: Session = Depends(get_db)) -> list[NotificationEvent]:
    return db.query(NotificationEvent).order_by(NotificationEvent.created_at.desc()).limit(50).all()


@router.get("/preferences", response_model=list[NotificationPreferenceRead])
def list_notification_preferences(db: Session = Depends(get_db)) -> list[NotificationPreference]:
    return db.query(NotificationPreference).order_by(NotificationPreference.channel.asc()).all()


@router.post("/preferences", response_model=NotificationPreferenceRead)
def create_or_update_notification_preference(
    payload: NotificationPreferenceCreate,
    db: Session = Depends(get_db),
) -> NotificationPreference:
    record = db.query(NotificationPreference).filter(NotificationPreference.channel == payload.channel).first()
    if record is None:
        record = NotificationPreference(channel=payload.channel)
    record.enabled = payload.enabled
    record.target = payload.target
    record.metadata_json = payload.metadata_json
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/test", response_model=NotificationEventRead)
def send_test_notification(payload: NotificationTestRequest, db: Session = Depends(get_db)) -> NotificationEvent:
    service = NotificationService(db)
    return service.enqueue(channel=payload.channel, subject=payload.subject, body=payload.body)
