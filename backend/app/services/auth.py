from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.entities import PlatformSession, PlatformUser
from backend.app.schemas.auth import AuthStatusRead, AuthUserRead
from backend.app.services.integrations import IntegrationService

GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass
class GoogleAuthResult:
    redirect_url: str
    session_token: str
    session_expires_at: datetime
    user: PlatformUser


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.integrations = IntegrationService(db)

    def google_ready(self) -> bool:
        connection = self.integrations.config_for_provider("google_oauth")
        if connection is None:
            return False
        settings_json = connection.settings_json or {}
        secrets_json = connection.secrets_json or {}
        return bool(settings_json.get("client_id") and secrets_json.get("client_secret"))

    def google_start_url(self, next_url: str | None = None) -> str:
        connection = self.integrations.config_for_provider("google_oauth")
        if connection is None:
            raise ValueError("Google OAuth is not configured in Integrations")
        settings_json = connection.settings_json or {}
        secrets_json = connection.secrets_json or {}
        client_id = settings_json.get("client_id")
        client_secret = secrets_json.get("client_secret")
        if not client_id or not client_secret:
            raise ValueError("Google OAuth client ID and client secret must be configured first")
        redirect_uri = self._google_redirect_uri()
        provider = self.integrations.get_provider("google_oauth")
        scopes = connection.scopes_json or provider.default_scopes or ["openid", "email", "profile"]
        query = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": self._encode_state({"next": self._sanitize_next_url(next_url), "exp": int(time.time()) + 600, "nonce": secrets.token_urlsafe(12)}),
            "include_granted_scopes": "true",
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{provider.auth_url}?{urllib.parse.urlencode(query)}"

    def complete_google_login(self, code: str, state: str | None) -> GoogleAuthResult:
        state_payload = self._decode_state(state or "")
        if state_payload is None:
            raise ValueError("OAuth state is missing or invalid")
        connection = self.integrations.config_for_provider("google_oauth")
        if connection is None:
            raise ValueError("Google OAuth is not configured in Integrations")
        settings_json = connection.settings_json or {}
        secrets_json = connection.secrets_json or {}
        redirect_uri = self._google_redirect_uri()
        token_payload = self._exchange_code(
            code=code,
            client_id=str(settings_json.get("client_id") or ""),
            client_secret=str(secrets_json.get("client_secret") or ""),
            redirect_uri=redirect_uri,
        )
        access_token = str(token_payload.get("access_token") or "")
        if not access_token:
            raise ValueError("Google token exchange did not return an access token")
        profile = self._fetch_google_profile(access_token)
        user = self._upsert_user(profile)
        session = self._create_session(user)
        next_url = str(state_payload.get("next") or self.settings.frontend_base_url)
        separator = "&" if "?" in next_url else "?"
        redirect_url = f"{next_url}{separator}auth_token={urllib.parse.quote(session.session_token)}"
        return GoogleAuthResult(
            redirect_url=redirect_url,
            session_token=session.session_token,
            session_expires_at=session.expires_at,
            user=user,
        )

    def auth_status(self, session_token: str | None = None) -> AuthStatusRead:
        session = self.get_session(session_token)
        if session is None:
            return AuthStatusRead(authenticated=False, google_ready=self.google_ready(), auth_mode="google")
        user = self.db.query(PlatformUser).filter(PlatformUser.id == session.user_id).first()
        if user is None:
            return AuthStatusRead(authenticated=False, google_ready=self.google_ready(), auth_mode="google")
        session.last_seen_at = datetime.now(timezone.utc)
        self.db.add(session)
        self.db.commit()
        return AuthStatusRead(
            authenticated=True,
            google_ready=self.google_ready(),
            auth_mode="google",
            session_expires_at=session.expires_at,
            user=AuthUserRead.model_validate(user),
        )

    def logout(self, session_token: str | None) -> bool:
        session = self.get_session(session_token)
        if session is None:
            return False
        session.revoked_at = datetime.now(timezone.utc)
        self.db.add(session)
        self.db.commit()
        return True

    def get_session(self, session_token: str | None) -> PlatformSession | None:
        if not session_token:
            return None
        session = (
            self.db.query(PlatformSession)
            .filter(PlatformSession.session_token == session_token, PlatformSession.revoked_at.is_(None))
            .first()
        )
        if session is None:
            return None
        expires_at = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return None
        return session

    def _google_redirect_uri(self) -> str:
        return f"{self.settings.backend_base_url.rstrip('/')}{self.settings.api_v1_prefix}/auth/google/callback"

    def _exchange_code(self, *, code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict[str, Any]:
        if not client_id or not client_secret:
            raise ValueError("Google OAuth credentials are incomplete")
        payload = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post("https://oauth2.googleapis.com/token", data=payload)
            response.raise_for_status()
            return response.json()

    def _fetch_google_profile(self, access_token: str) -> dict[str, Any]:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
            response.raise_for_status()
            data = response.json()
        if not data.get("sub") or not data.get("email"):
            raise ValueError("Google user profile is missing required identity fields")
        return data

    def _upsert_user(self, profile: dict[str, Any]) -> PlatformUser:
        google_sub = str(profile["sub"])
        email = str(profile["email"])
        user = self.db.query(PlatformUser).filter(PlatformUser.google_sub == google_sub).first()
        if user is None:
            user = PlatformUser(
                google_sub=google_sub,
                email=email,
                full_name=profile.get("name"),
                avatar_url=profile.get("picture"),
                last_login_at=datetime.now(timezone.utc),
                metadata_json={"email_verified": profile.get("email_verified")},
            )
        else:
            user.email = email
            user.full_name = profile.get("name")
            user.avatar_url = profile.get("picture")
            user.last_login_at = datetime.now(timezone.utc)
            metadata = user.metadata_json or {}
            metadata["email_verified"] = profile.get("email_verified")
            user.metadata_json = metadata
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _create_session(self, user: PlatformUser) -> PlatformSession:
        session = PlatformSession(
            user_id=user.id,
            session_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(days=self.settings.auth_session_days),
            last_seen_at=datetime.now(timezone.utc),
            metadata_json={"provider": "google"},
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def _sanitize_next_url(self, next_url: str | None) -> str:
        candidate = str(next_url or self.settings.frontend_base_url).strip()
        allowed_prefixes = {self.settings.frontend_base_url.rstrip("/")}
        if any(candidate.startswith(prefix) for prefix in allowed_prefixes):
            return candidate
        return self.settings.frontend_base_url

    def _encode_state(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        sig = hmac.new(self.settings.auth_secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def _decode_state(self, token: str) -> dict[str, Any] | None:
        if "." not in token:
            return None
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(self.settings.auth_secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        padding = "=" * (-len(body) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(body + padding).decode("utf-8"))
        except Exception:
            return None
        if int(payload.get("exp") or 0) < int(time.time()):
            return None
        return payload



