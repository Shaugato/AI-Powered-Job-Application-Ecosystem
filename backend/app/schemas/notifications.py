from typing import Any

from pydantic import BaseModel

from backend.app.schemas.common import ORMModel


class NotificationPreferenceCreate(BaseModel):
    channel: str
    enabled: bool = False
    target: str | None = None
    metadata_json: dict[str, Any] | None = None


class NotificationPreferenceRead(ORMModel):
    id: str
    channel: str
    enabled: bool
    target: str | None
    metadata_json: dict[str, Any] | None


class NotificationEventRead(ORMModel):
    id: str
    channel: str
    subject: str
    body: str
    delivery_status: str
    metadata_json: dict[str, Any] | None


class NotificationTestRequest(BaseModel):
    channel: str
    subject: str = "Test notification"
    body: str = "This is a dashboard-triggered test notification."
