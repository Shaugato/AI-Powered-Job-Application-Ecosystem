from datetime import datetime

from pydantic import BaseModel

from backend.app.schemas.common import ORMModel


class AuthUserRead(ORMModel):
    id: str
    email: str
    full_name: str | None
    avatar_url: str | None
    last_login_at: datetime | None


class AuthStatusRead(BaseModel):
    authenticated: bool
    google_ready: bool
    auth_mode: str
    session_expires_at: datetime | None = None
    user: AuthUserRead | None = None
