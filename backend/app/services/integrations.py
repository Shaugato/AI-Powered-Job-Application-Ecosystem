from __future__ import annotations

import asyncio
import json
import uuid
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.entities import IntegrationConnection
from backend.app.schemas.integrations import (
    IntegrationBrowserCaptureRead,
    IntegrationConnectResponse,
    IntegrationConnectionCreate,
    IntegrationConnectionRead,
    IntegrationProviderFieldRead,
    IntegrationProviderRead,
)



DEFAULT_BACKEND_BASE_URL = get_settings().backend_base_url.rstrip("/")

@dataclass(frozen=True)
class ProviderDefinition:
    key: str
    name: str
    category: str
    auth_type: str
    description: str
    capabilities: list[str]
    fields: list[IntegrationProviderFieldRead]
    default_scopes: list[str]
    launch_url: str | None = None
    auth_url: str | None = None
    token_url: str | None = None


DISCOVERY_CONNECTION_PRIORITY: dict[str, list[str]] = {
    "seek": ["seek_account", "seek"],
    "linkedin": ["linkedin_account", "linkedin"],
    "indeed": ["indeed_account", "indeed"],
    "apsjobs": ["apsjobs"],
    "careers_vic": ["careers_vic"],
    "company_portal": ["company_portal"],
}

APPLICATION_CONNECTION_PRIORITY: dict[str, list[str]] = {
    "seek": ["seek_account"],
    "linkedin": ["linkedin_account"],
    "indeed": ["indeed_account"],
    "company_portal": ["company_portal"],
}


PROVIDERS: dict[str, ProviderDefinition] = {
    "seek": ProviderDefinition(
        key="seek",
        name="Seek",
        category="source",
        auth_type="public_search",
        description="Monitor SEEK job search results without requiring a hardcoded search URL.",
        capabilities=["search monitoring", "job ingestion"],
        fields=[],
        default_scopes=[],
        launch_url="https://www.seek.com.au/jobs",
    ),
    "linkedin": ProviderDefinition(
        key="linkedin",
        name="LinkedIn Jobs",
        category="source",
        auth_type="public_search",
        description="Monitor LinkedIn Jobs search pages with optional connected account support.",
        capabilities=["search monitoring", "job ingestion", "easy apply planning"],
        fields=[],
        default_scopes=[],
        launch_url="https://www.linkedin.com/jobs/search/",
    ),
    "indeed": ProviderDefinition(
        key="indeed",
        name="Indeed",
        category="source",
        auth_type="public_search",
        description="Monitor Indeed search results without hardcoding URLs, with optional account-backed apply support.",
        capabilities=["search monitoring", "job ingestion"],
        fields=[],
        default_scopes=[],
        launch_url="https://au.indeed.com/jobs",
    ),
    "apsjobs": ProviderDefinition(
        key="apsjobs",
        name="APSJobs",
        category="source",
        auth_type="search_url_optional",
        description="Monitor Australian Public Service jobs with review-gated application handling.",
        capabilities=["government monitoring", "review-required applications"],
        fields=[IntegrationProviderFieldRead(key="search_url", label="Search URL", input_type="url", required=False, placeholder="https://www.apsjobs.gov.au/...", help_text="Optional override for a specific APS search result page.")],
        default_scopes=[],
        launch_url="https://www.apsjobs.gov.au/",
    ),
    "careers_vic": ProviderDefinition(
        key="careers_vic",
        name="Careers.Vic",
        category="source",
        auth_type="search_url_optional",
        description="Monitor Victorian government roles with manual review preserved for complex flows.",
        capabilities=["government monitoring", "review-required applications"],
        fields=[IntegrationProviderFieldRead(key="search_url", label="Search URL", input_type="url", required=False, placeholder="https://careers.vic.gov.au/...", help_text="Optional override for a specific Careers.Vic search result page.")],
        default_scopes=[],
        launch_url="https://www.careers.vic.gov.au/",
    ),
    "company_portal": ProviderDefinition(
        key="company_portal",
        name="Company Portal",
        category="source",
        auth_type="browser_session",
        description="Connect a company career site or applicant portal with browser-assisted login and monitoring.",
        capabilities=["career site monitoring", "deterministic apply flow", "browser session reuse"],
        fields=[
            IntegrationProviderFieldRead(key="base_url", label="Base URL", input_type="url", required=True, placeholder="https://company.example/careers", help_text="Career page or ATS base URL."),
            IntegrationProviderFieldRead(key="login_url", label="Login URL", input_type="url", required=False, placeholder="https://company.example/login", help_text="Optional login page for browser-assisted session capture."),
        ],
        default_scopes=[],
        launch_url="https://example.com/careers",
    ),
    "google_oauth": ProviderDefinition(
        key="google_oauth",
        name="Google",
        category="account",
        auth_type="oauth2",
        description="Connect Google identity for platform sign-in and future account-backed integrations.",
        capabilities=["oauth sign-in", "connected identity"],
        fields=[
            IntegrationProviderFieldRead(key="client_id", label="Client ID", input_type="text", required=True, placeholder="Google OAuth client ID", help_text="Create a Web application client in Google Cloud."),
            IntegrationProviderFieldRead(key="client_secret", label="Client Secret", input_type="password", required=True, secret=True, placeholder="Google OAuth client secret"),
            IntegrationProviderFieldRead(key="redirect_uri", label="Redirect URI", input_type="url", required=False, placeholder=f"{DEFAULT_BACKEND_BASE_URL}/api/v1/auth/google/callback", help_text="Use the exact platform callback URL for Sign in with Google."),
        ],
        default_scopes=["openid", "email", "profile"],
        launch_url="https://accounts.google.com/",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
    ),
    "microsoft_oauth": ProviderDefinition(
        key="microsoft_oauth",
        name="Microsoft",
        category="account",
        auth_type="oauth2",
        description="Connect Microsoft identity for enterprise account flows.",
        capabilities=["oauth sign-in", "connected identity"],
        fields=[
            IntegrationProviderFieldRead(key="tenant_id", label="Tenant ID", input_type="text", required=False, placeholder="common"),
            IntegrationProviderFieldRead(key="client_id", label="Client ID", input_type="text", required=True, placeholder="Azure app client ID"),
            IntegrationProviderFieldRead(key="client_secret", label="Client Secret", input_type="password", required=True, secret=True, placeholder="Azure app client secret"),
            IntegrationProviderFieldRead(key="redirect_uri", label="Redirect URI", input_type="url", required=False, placeholder=f"{DEFAULT_BACKEND_BASE_URL}/api/v1/integrations/oauth/callback/microsoft_oauth"),
        ],
        default_scopes=["openid", "email", "profile", "offline_access"],
        launch_url="https://login.microsoftonline.com/",
        auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    ),
    "linkedin_account": ProviderDefinition(
        key="linkedin_account",
        name="LinkedIn Account",
        category="account",
        auth_type="browser_session",
        description="Store a LinkedIn browser-backed account connection for careful operator-reviewed flows.",
        capabilities=["browser session", "operator-reviewed account connection"],
        fields=[IntegrationProviderFieldRead(key="login_url", label="Login URL", input_type="url", required=False, placeholder="https://www.linkedin.com/login")],
        default_scopes=[],
        launch_url="https://www.linkedin.com/login",
    ),
    "seek_account": ProviderDefinition(
        key="seek_account",
        name="Seek Account",
        category="account",
        auth_type="browser_session",
        description="Store a SEEK browser-backed account connection for monitored sessions and staged applications.",
        capabilities=["browser session", "operator-reviewed account connection"],
        fields=[IntegrationProviderFieldRead(key="login_url", label="Login URL", input_type="url", required=False, placeholder="https://www.seek.com.au/profile/login")],
        default_scopes=[],
        launch_url="https://www.seek.com.au/profile/login",
    ),
    "indeed_account": ProviderDefinition(
        key="indeed_account",
        name="Indeed Account",
        category="account",
        auth_type="browser_session",
        description="Store an Indeed browser-backed account connection for monitored sessions and staged applications.",
        capabilities=["browser session", "operator-reviewed account connection"],
        fields=[IntegrationProviderFieldRead(key="login_url", label="Login URL", input_type="url", required=False, placeholder="https://secure.indeed.com/account/login")],
        default_scopes=[],
        launch_url="https://secure.indeed.com/account/login",
    ),
    "openai_ai": ProviderDefinition(
        key="openai_ai",
        name="OpenAI Parser",
        category="ai",
        auth_type="api_key",
        description="Use OpenAI to clean uploaded resumes and extract structured candidate profile signals.",
        capabilities=["document cleanup", "profile extraction", "schema-locked parsing"],
        fields=[
            IntegrationProviderFieldRead(key="api_key", label="API Key", input_type="password", required=True, secret=True, placeholder="sk-..."),
            IntegrationProviderFieldRead(key="base_url", label="Base URL", input_type="url", required=False, placeholder="https://api.openai.com/v1"),
            IntegrationProviderFieldRead(key="parser_model", label="Parser model", input_type="text", required=False, placeholder="gpt-5-nano", help_text="Used only for document cleanup and profile extraction."),
        ],
        default_scopes=[],
        launch_url="https://platform.openai.com/",
    ),
    "gemini_ai": ProviderDefinition(
        key="gemini_ai",
        name="Gemini Parser",
        category="ai",
        auth_type="api_key",
        description="Use Google Gemini to parse resumes, PDFs, and cover letters into structured profile memory.",
        capabilities=["document understanding", "pdf parsing", "structured extraction"],
        fields=[
            IntegrationProviderFieldRead(key="api_key", label="API Key", input_type="password", required=True, secret=True, placeholder="AIza..."),
            IntegrationProviderFieldRead(key="base_url", label="Base URL", input_type="url", required=False, placeholder="https://generativelanguage.googleapis.com/v1beta"),
            IntegrationProviderFieldRead(key="parser_model", label="Parser model", input_type="text", required=False, placeholder="gemini-2.5-flash", help_text="Used only for document cleanup and profile extraction."),
        ],
        default_scopes=[],
        launch_url="https://ai.google.dev/",
    ),
    "smtp": ProviderDefinition(
        key="smtp",
        name="SMTP Email",
        category="notification",
        auth_type="smtp",
        description="Configure outbound email delivery directly from the dashboard.",
        capabilities=["email notifications"],
        fields=[
            IntegrationProviderFieldRead(key="host", label="SMTP Host", input_type="text", required=True, placeholder="smtp.example.com"),
            IntegrationProviderFieldRead(key="port", label="Port", input_type="number", required=True, placeholder="587"),
            IntegrationProviderFieldRead(key="username", label="Username", input_type="text", required=True, placeholder="name@example.com"),
            IntegrationProviderFieldRead(key="password", label="Password", input_type="password", required=True, secret=True, placeholder="SMTP password"),
            IntegrationProviderFieldRead(key="from_email", label="From Address", input_type="email", required=False, placeholder="jobs@example.com"),
        ],
        default_scopes=[],
    ),
    "slack_webhook": ProviderDefinition(
        key="slack_webhook",
        name="Slack Webhook",
        category="notification",
        auth_type="webhook",
        description="Configure Slack delivery through an incoming webhook from inside the platform.",
        capabilities=["slack notifications"],
        fields=[IntegrationProviderFieldRead(key="webhook_url", label="Webhook URL", input_type="password", required=True, secret=True, placeholder="https://hooks.slack.com/services/...")],
        default_scopes=[],
        launch_url="https://api.slack.com/apps",
    ),
}


class IntegrationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def list_providers(self, category: str | None = None) -> list[IntegrationProviderRead]:
        providers = [provider for provider in PROVIDERS.values() if provider.category != "ai"]
        if category:
            providers = [provider for provider in providers if provider.category == category]
        return [IntegrationProviderRead.model_validate(provider.__dict__) for provider in providers]

    def get_provider(self, provider_key: str) -> ProviderDefinition:
        provider = PROVIDERS.get(provider_key)
        if provider is None:
            raise KeyError(provider_key)
        return provider

    def list_connections(self) -> list[IntegrationConnectionRead]:
        connections = (
            self.db.query(IntegrationConnection)
            .filter(IntegrationConnection.category != "ai")
            .order_by(IntegrationConnection.created_at.desc())
            .all()
        )
        return [self._to_read_model(connection) for connection in connections]

    def get_connection(self, connection_id: str) -> IntegrationConnection | None:
        return self.db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()

    def create_connection(self, payload: IntegrationConnectionCreate) -> IntegrationConnectionRead:
        provider = self.get_provider(payload.provider_key)
        settings_json, secrets_json = self._split_settings(provider, payload.settings_json or {})
        record = IntegrationConnection(
            name=payload.name,
            provider_key=provider.key,
            category=provider.category,
            auth_type=provider.auth_type,
            status=("connected" if provider.auth_type == "api_key" else "configured") if self._has_required_fields(provider, settings_json, secrets_json) and provider.auth_type in {"oauth2", "smtp", "webhook", "public_search", "search_url_optional", "api_key"} else "disconnected",
            login_hint=payload.login_hint,
            settings_json=settings_json,
            secrets_json=secrets_json,
            scopes_json=provider.default_scopes,
            metadata_json=payload.metadata_json,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_read_model(record)

    def update_connection(self, connection_id: str, payload: IntegrationConnectionCreate) -> IntegrationConnectionRead | None:
        record = self.get_connection(connection_id)
        if record is None:
            return None
        provider = self.get_provider(payload.provider_key)
        settings_json, secrets_json = self._split_settings(provider, payload.settings_json or {}, existing_secrets=record.secrets_json or {})
        record.name = payload.name
        record.provider_key = provider.key
        record.category = provider.category
        record.auth_type = provider.auth_type
        record.login_hint = payload.login_hint
        record.settings_json = settings_json
        record.secrets_json = secrets_json
        record.scopes_json = provider.default_scopes
        record.metadata_json = payload.metadata_json
        if provider.auth_type in {"oauth2", "smtp", "webhook", "public_search", "search_url_optional", "api_key"} and self._has_required_fields(provider, settings_json, secrets_json):
            record.status = "connected" if provider.auth_type == "api_key" else "configured"
        elif provider.auth_type == "browser_session" and self.resolved_session_path(record):
            record.status = "connected"
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_read_model(record)

    def delete_connection(self, connection_id: str) -> bool:
        record = self.get_connection(connection_id)
        if record is None:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def connect(self, connection_id: str) -> IntegrationConnectResponse | None:
        record = self.get_connection(connection_id)
        if record is None:
            return None
        provider = self.get_provider(record.provider_key)
        if provider.auth_type == "oauth2":
            return self._oauth_connect(record, provider)
        if provider.auth_type == "browser_session":
            session_path = self.resolved_session_path(record)
            if session_path is not None:
                record.status = "connected"
                record.last_connected_at = datetime.now(timezone.utc)
                self.db.add(record)
                self.db.commit()
                return IntegrationConnectResponse(
                    status=record.status,
                    connection_id=record.id,
                    launch_url=self._browser_login_url(record, provider),
                    instructions=[
                        "A browser session is already stored for this connection.",
                        "You can reuse this account in monitoring and application runs.",
                    ],
                    details={"provider": provider.name, "storage_state_path": str(session_path)},
                )
            capture = self.start_browser_capture(connection_id)
            if capture is None:
                return None
            return IntegrationConnectResponse(
                status=capture.status,
                connection_id=record.id,
                launch_url=capture.login_url,
                instructions=capture.instructions,
                details={
                    "provider": provider.name,
                    "helper_command": capture.helper_command,
                    "helper_script_path": capture.helper_script_path,
                    "debug_port": capture.debug_port,
                    "browser_reachable": capture.browser_reachable,
                    "launch_mode": (capture.details or {}).get("launch_mode"),
                    "manual_action_required": (capture.details or {}).get("manual_action_required", False),
                },
            )
        if self._has_required_fields(provider, record.settings_json or {}, record.secrets_json or {}):
            record.status = "connected" if provider.auth_type == "api_key" else "connected"
            record.last_connected_at = datetime.now(timezone.utc)
            self.db.add(record)
            self.db.commit()
            return IntegrationConnectResponse(status=record.status, connection_id=record.id, instructions=[f"{provider.name} configuration is stored and ready."])
        record.status = "pending_config"
        self.db.add(record)
        self.db.commit()
        return IntegrationConnectResponse(status=record.status, connection_id=record.id, instructions=["Required settings are missing for this provider."])

    def handle_oauth_callback(self, provider_key: str, code: str, state: str | None) -> IntegrationConnectionRead | None:
        provider = self.get_provider(provider_key)
        if provider.auth_type != "oauth2":
            return None
        connection_id, state_token = self._parse_state(state or "")
        if not connection_id or not state_token:
            return None
        record = self.db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id, IntegrationConnection.provider_key == provider_key).first()
        if record is None:
            return None
        metadata = record.metadata_json or {}
        if metadata.get("oauth_state") != state_token:
            record.status = "oauth_state_mismatch"
            self.db.add(record)
            self.db.commit()
            return self._to_read_model(record)
        token_payload = self._exchange_code(provider, record, code)
        if token_payload is None:
            record.status = "oauth_exchange_failed"
            self.db.add(record)
            self.db.commit()
            return self._to_read_model(record)
        secrets_json = record.secrets_json or {}
        secrets_json.update(token_payload)
        record.secrets_json = secrets_json
        record.status = "connected"
        record.last_connected_at = datetime.now(timezone.utc)
        metadata.pop("oauth_state", None)
        record.metadata_json = metadata
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_read_model(record)

    def save_browser_session_state(self, connection_id: str, *, filename: str, payload: bytes) -> IntegrationConnectionRead | None:
        record = self.get_connection(connection_id)
        if record is None:
            return None
        provider = self.get_provider(record.provider_key)
        if provider.auth_type != "browser_session":
            raise ValueError("Browser session uploads are only supported for browser_session providers")

        try:
            decoded = payload.decode("utf-8")
            parsed = json.loads(decoded)
        except Exception as exc:
            raise ValueError(f"Invalid JSON session state: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("Session state payload must be a JSON object")

        connection_dir = self.settings.integration_data_dir / record.id
        connection_dir.mkdir(parents=True, exist_ok=True)
        destination = connection_dir / "storage_state.json"
        destination.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

        metadata = record.metadata_json or {}
        metadata["session_state_path"] = str(destination)
        metadata["session_state_filename"] = Path(filename).name or "storage_state.json"
        metadata["session_uploaded_at"] = datetime.now(timezone.utc).isoformat()
        record.metadata_json = metadata
        record.status = "connected"
        record.last_connected_at = datetime.now(timezone.utc)
        record.error_message = None
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_read_model(record)

    def resolved_session_path(self, record: IntegrationConnection | None) -> Path | None:
        if record is None:
            return None
        metadata = record.metadata_json or {}
        raw_path = metadata.get("session_state_path")
        if not raw_path:
            return None
        path = Path(str(raw_path))
        return path if path.exists() else None

    def connection_for_source(self, source_name: str, *, preferred_connection_id: str | None = None, purpose: str = "application") -> IntegrationConnection | None:
        provider_keys = self.provider_keys_for_source(source_name, purpose=purpose)
        if preferred_connection_id:
            preferred = self.get_connection(preferred_connection_id)
            if preferred is not None and preferred.provider_key in provider_keys:
                return preferred
        if not provider_keys:
            return None
        return (
            self.db.query(IntegrationConnection)
            .filter(
                IntegrationConnection.provider_key.in_(provider_keys),
                IntegrationConnection.status.in_(["connected", "configured", "action_required", "awaiting_browser", "browser_ready"]),
            )
            .order_by(IntegrationConnection.updated_at.desc())
            .first()
        )

    def provider_keys_for_source(self, source_name: str, *, purpose: str = "application") -> list[str]:
        if purpose == "monitoring":
            return DISCOVERY_CONNECTION_PRIORITY.get(source_name, [])
        return APPLICATION_CONNECTION_PRIORITY.get(source_name, [])

    def connection_runtime_payload(self, record: IntegrationConnection | None) -> dict[str, Any]:
        if record is None:
            return {}
        session_path = self.resolved_session_path(record)
        settings_json = record.settings_json or {}
        metadata = record.metadata_json or {}
        return {
            "connection_id": record.id,
            "connection_provider_key": record.provider_key,
            "connection_status": record.status,
            "login_hint": record.login_hint,
            "login_url": settings_json.get("login_url"),
            "base_url": settings_json.get("base_url"),
            "search_url": settings_json.get("search_url") or settings_json.get("base_url"),
            "storage_state_path": str(session_path) if session_path else None,
            "has_session_state": bool(session_path),
            "capture_status": metadata.get("capture_status"),
            "capture_debug_port": metadata.get("capture_debug_port"),
        }

    def _oauth_connect(self, record: IntegrationConnection, provider: ProviderDefinition) -> IntegrationConnectResponse:
        settings_json = record.settings_json or {}
        secrets_json = record.secrets_json or {}
        if not self._has_required_fields(provider, settings_json, secrets_json):
            record.status = "pending_config"
            self.db.add(record)
            self.db.commit()
            return IntegrationConnectResponse(status=record.status, connection_id=record.id, instructions=["Client ID and client secret are required before starting OAuth."])
        redirect_uri = settings_json.get("redirect_uri") or f"{self.settings.backend_base_url.rstrip('/' )}{self.settings.api_v1_prefix}/integrations/oauth/callback/{provider.key}"
        oauth_state = uuid.uuid4().hex
        metadata = record.metadata_json or {}
        metadata["oauth_state"] = oauth_state
        record.metadata_json = metadata
        record.status = "pending_authorization"
        self.db.add(record)
        self.db.commit()
        query = {
            "client_id": settings_json.get("client_id"),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(record.scopes_json or provider.default_scopes),
            "state": f"{record.id}:{oauth_state}",
        }
        if provider.key == "microsoft_oauth":
            query["response_mode"] = "query"
        auth_url = f"{provider.auth_url}?{urllib.parse.urlencode(query)}"
        return IntegrationConnectResponse(
            status=record.status,
            connection_id=record.id,
            auth_url=auth_url,
            redirect_uri=redirect_uri,
            launch_url=provider.launch_url,
            instructions=[
                "Open the authorization URL in a browser.",
                "Complete consent and sign-in with your own account.",
                "The local callback endpoint will store the returned token response for this connection.",
            ],
        )

    def _exchange_code(self, provider: ProviderDefinition, record: IntegrationConnection, code: str) -> dict[str, Any] | None:
        settings_json = record.settings_json or {}
        secrets_json = record.secrets_json or {}
        redirect_uri = settings_json.get("redirect_uri") or f"{self.settings.backend_base_url.rstrip('/' )}{self.settings.api_v1_prefix}/integrations/oauth/callback/{provider.key}"
        token_url = provider.token_url
        if not token_url:
            return None
        tenant_id = settings_json.get("tenant_id")
        if provider.key == "microsoft_oauth" and tenant_id:
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        payload = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings_json.get("client_id"),
            "client_secret": secrets_json.get("client_secret"),
            "redirect_uri": redirect_uri,
        }).encode("utf-8")
        request = urllib.request.Request(token_url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # pragma: no cover
                data = json.loads(response.read().decode("utf-8"))
                return data
        except Exception:
            return None

    def _parse_state(self, raw_state: str) -> tuple[str | None, str | None]:
        if ":" not in raw_state:
            return None, None
        connection_id, state_token = raw_state.split(":", 1)
        return connection_id, state_token

    def _has_required_fields(self, provider: ProviderDefinition, settings_json: dict[str, Any], secrets_json: dict[str, Any]) -> bool:
        for field in provider.fields:
            if not field.required:
                continue
            source = secrets_json if field.secret else settings_json
            if not source.get(field.key):
                return False
        return True

    def _split_settings(self, provider: ProviderDefinition, payload: dict[str, Any], existing_secrets: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        existing_secrets = existing_secrets or {}
        settings_json: dict[str, Any] = {}
        secrets_json = dict(existing_secrets)
        secret_keys = {field.key for field in provider.fields if field.secret}
        for key, value in payload.items():
            if value in {None, ""}:
                continue
            if key in secret_keys:
                secrets_json[key] = value
            else:
                settings_json[key] = value
        return settings_json, secrets_json

    def _to_read_model(self, record: IntegrationConnection) -> IntegrationConnectionRead:
        provider = self.get_provider(record.provider_key)
        secret_fields_present = sorted([key for key, value in (record.secrets_json or {}).items() if value])
        session_path = self.resolved_session_path(record)
        metadata = record.metadata_json or {}
        return IntegrationConnectionRead(
            id=record.id,
            name=record.name,
            provider_key=record.provider_key,
            category=record.category,
            auth_type=record.auth_type,
            status=record.status,
            login_hint=record.login_hint,
            settings_json=record.settings_json,
            scopes_json=record.scopes_json or provider.default_scopes,
            secret_fields_present=secret_fields_present,
            last_connected_at=record.last_connected_at,
            last_tested_at=record.last_tested_at,
            error_message=record.error_message,
            metadata_json=record.metadata_json,
            has_session_state=bool(session_path),
            session_state_filename=str(metadata.get("session_state_filename") or (session_path.name if session_path else "")) or None,
        )

    def config_for_provider(self, provider_key: str) -> IntegrationConnection | None:
        return (
            self.db.query(IntegrationConnection)
            .filter(IntegrationConnection.provider_key == provider_key)
            .order_by(IntegrationConnection.updated_at.desc())
            .first()
        )



    def start_browser_capture(self, connection_id: str) -> IntegrationBrowserCaptureRead | None:
        record = self.get_connection(connection_id)
        if record is None:
            return None
        provider = self.get_provider(record.provider_key)
        if provider.auth_type != "browser_session":
            raise ValueError("Browser capture is only supported for browser_session providers")

        if self.resolved_session_path(record) is not None:
            record.status = "connected"
            record.last_connected_at = datetime.now(timezone.utc)
            self.db.add(record)
            self.db.commit()
            return self.browser_capture_status(connection_id)

        metadata = dict(record.metadata_json or {})
        login_url = self._browser_login_url(record, provider)
        port = metadata.get("capture_debug_port")
        if not isinstance(port, int):
            port = self._allocate_capture_port(exclude_connection_id=record.id)

        bridge_result = self._launch_browser_via_bridge(
            connection_id=record.id,
            login_url=login_url,
            port=port,
            profile_relative_path=self._capture_profile_relative_path(record),
        )
        launched = bool(bridge_result and bridge_result.get("status") == "launched")
        launch_mode = "bridge" if launched else "manual"
        launch_message = str((bridge_result or {}).get("detail") or (bridge_result or {}).get("status") or "")
        if launched:
            launch_message = "The platform asked your computer to open a secure sign-in browser window."
        elif not launch_message:
            launch_message = "Automatic browser launch was unavailable, so the manual helper is ready as a fallback."

        metadata.update(
            {
                "capture_status": "launching_browser" if launched else "awaiting_browser",
                "capture_started_at": datetime.now(timezone.utc).isoformat(),
                "capture_debug_port": port,
                "capture_login_url": login_url,
                "capture_profile_dir": self._capture_profile_relative_path(record),
                "capture_helper_script_path": ".\\launch-browser-session.ps1",
                "capture_helper_command": self._browser_helper_command(record.id, login_url, port),
                "capture_last_checked_at": None,
                "capture_launch_mode": launch_mode,
                "capture_manual_fallback": not launched,
                "capture_launch_message": launch_message,
                "capture_bridge_response": bridge_result,
            }
        )
        record.metadata_json = metadata
        record.status = "launching_browser" if launched else "awaiting_browser"
        record.error_message = None
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self.browser_capture_status(connection_id)

    def browser_capture_status(self, connection_id: str) -> IntegrationBrowserCaptureRead | None:
        record = self.get_connection(connection_id)
        if record is None:
            return None
        provider = self.get_provider(record.provider_key)
        if provider.auth_type != "browser_session":
            raise ValueError("Browser capture is only supported for browser_session providers")

        metadata = dict(record.metadata_json or {})
        port = metadata.get("capture_debug_port")
        browser_info = self._probe_browser_capture(port) if isinstance(port, int) else None
        browser_reachable = browser_info is not None
        if browser_reachable and record.status in {"launching_browser", "awaiting_browser", "action_required", "configured", "disconnected"}:
            record.status = "browser_ready"
        metadata["capture_last_checked_at"] = datetime.now(timezone.utc).isoformat()
        record.metadata_json = metadata
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        details = {
            "browser_info": browser_info,
            "launch_mode": metadata.get("capture_launch_mode"),
            "manual_action_required": bool(metadata.get("capture_manual_fallback")),
            "launch_message": metadata.get("capture_launch_message"),
        }
        return self._to_browser_capture_model(record, provider, browser_reachable=browser_reachable, details=details)

    def finalize_browser_capture(self, connection_id: str) -> IntegrationBrowserCaptureRead | None:
        record = self.get_connection(connection_id)
        if record is None:
            return None
        provider = self.get_provider(record.provider_key)
        if provider.auth_type != "browser_session":
            raise ValueError("Browser capture is only supported for browser_session providers")

        metadata = dict(record.metadata_json or {})
        port = metadata.get("capture_debug_port")
        if not isinstance(port, int):
            record.status = "awaiting_browser"
            record.error_message = "Start the sign-in flow before finishing the connection."
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return self._to_browser_capture_model(record, provider, browser_reachable=False)

        browser_info = self._probe_browser_capture(port)
        if browser_info is None:
            record.status = "awaiting_browser"
            record.error_message = "The sign-in browser is not reachable yet. Complete sign-in in the launched browser window, or use the fallback helper if it did not open."
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return self._to_browser_capture_model(record, provider, browser_reachable=False)

        destination = self._session_directory(record) / "storage_state.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            page_urls = asyncio.run(self._capture_storage_state_from_cdp(port, destination))
        except Exception as exc:
            record.status = "capture_failed"
            record.error_message = str(exc)
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return self._to_browser_capture_model(record, provider, browser_reachable=True, details={"error": str(exc)})

        metadata.update(
            {
                "session_state_path": str(destination),
                "session_state_filename": destination.name,
                "session_uploaded_at": datetime.now(timezone.utc).isoformat(),
                "capture_status": "connected",
                "capture_completed_at": datetime.now(timezone.utc).isoformat(),
                "captured_page_urls": page_urls,
            }
        )
        record.metadata_json = metadata
        record.status = "connected"
        record.last_connected_at = datetime.now(timezone.utc)
        record.error_message = None
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_browser_capture_model(record, provider, browser_reachable=True, details={"captured_page_urls": page_urls})

    def cancel_browser_capture(self, connection_id: str) -> IntegrationBrowserCaptureRead | None:
        record = self.get_connection(connection_id)
        if record is None:
            return None
        provider = self.get_provider(record.provider_key)
        if provider.auth_type != "browser_session":
            raise ValueError("Browser capture is only supported for browser_session providers")

        metadata = dict(record.metadata_json or {})
        metadata["capture_status"] = "cancelled"
        metadata["capture_cancelled_at"] = datetime.now(timezone.utc).isoformat()
        record.metadata_json = metadata
        record.status = "connected" if self.resolved_session_path(record) else "configured" if self._has_required_fields(provider, record.settings_json or {}, record.secrets_json or {}) else "disconnected"
        record.error_message = None
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_browser_capture_model(record, provider, browser_reachable=False)
    def _session_directory(self, record: IntegrationConnection) -> Path:
        return self.settings.integration_data_dir / record.id

    def _capture_profile_relative_path(self, record: IntegrationConnection) -> str:
        return str(Path("private-data") / "integrations" / record.id / "browser-profile")

    def _browser_login_url(self, record: IntegrationConnection, provider: ProviderDefinition) -> str | None:
        settings_json = record.settings_json or {}
        login_url = settings_json.get("login_url") or settings_json.get("base_url") or provider.launch_url
        return str(login_url) if login_url else None

    def _allocate_capture_port(self, *, exclude_connection_id: str | None = None) -> int:
        taken: set[int] = set()
        for connection in self.db.query(IntegrationConnection).all():
            if exclude_connection_id and connection.id == exclude_connection_id:
                continue
            metadata = connection.metadata_json or {}
            port = metadata.get("capture_debug_port")
            if isinstance(port, int):
                taken.add(port)
        base = self.settings.browser_capture_base_port
        for port in range(base, base + 200):
            if port not in taken:
                return port
        return base + 500

    def _browser_helper_command(self, connection_id: str, login_url: str | None, port: int) -> str:
        escaped_url = (login_url or "").replace('"', '`"')
        return f'.\\launch-browser-session.ps1 -ConnectionId "{connection_id}" -LoginUrl "{escaped_url}" -Port {port}'

    def _launch_browser_via_bridge(
        self,
        *,
        connection_id: str,
        login_url: str | None,
        port: int,
        profile_relative_path: str,
    ) -> dict[str, Any]:
        if not login_url:
            return {"status": "error", "detail": "No login URL is available for this provider."}
        bridge_base = str(self.settings.browser_bridge_url or "").strip().rstrip("/")
        if not bridge_base:
            return {"status": "unavailable", "detail": "Browser bridge URL is not configured."}
        payload = json.dumps(
            {
                "connection_id": connection_id,
                "login_url": login_url,
                "port": port,
                "profile_relative_path": profile_relative_path,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{bridge_base}/launch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.browser_bridge_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {"status": "unavailable", "detail": str(exc)}

    def _probe_browser_capture(self, port: int | None) -> dict[str, Any] | None:
        if port is None:
            return None
        url = f"http://{self.settings.browser_capture_host}:{port}/json/version"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

    async def _capture_storage_state_from_cdp(self, port: int, destination: Path) -> list[str]:
        from playwright.async_api import async_playwright

        debug_url = f"http://{self.settings.browser_capture_host}:{port}"
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(debug_url)
            contexts = browser.contexts
            if not contexts:
                raise RuntimeError("The guided sign-in browser is open, but no browser context is available yet.")
            context = contexts[0]
            await context.storage_state(path=str(destination))
            return [page.url for page in context.pages if page.url][:5]

    def _parse_timestamp(self, raw_value: Any) -> datetime | None:
        if not raw_value or not isinstance(raw_value, str):
            return None
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _to_browser_capture_model(
        self,
        record: IntegrationConnection,
        provider: ProviderDefinition,
        *,
        browser_reachable: bool,
        details: dict[str, Any] | None = None,
    ) -> IntegrationBrowserCaptureRead:
        metadata = record.metadata_json or {}
        session_path = self.resolved_session_path(record)
        login_url = metadata.get("capture_login_url") or self._browser_login_url(record, provider)
        port = metadata.get("capture_debug_port")
        status = "connected" if session_path else str(metadata.get("capture_status") or record.status)
        launch_mode = str(metadata.get("capture_launch_mode") or "manual")
        manual_action_required = bool(metadata.get("capture_manual_fallback"))
        instructions = [
            "Save the connection details first.",
            "Run the guided sign-in helper from the repo root to open an isolated browser window.",
            "Log into the provider in that browser window, then return here and finish the connection.",
        ]
        if launch_mode == "bridge" and not manual_action_required:
            instructions = [
                "The platform asked your computer to open a secure sign-in browser window.",
                "Finish signing in there, then return here and click Finish connection.",
                "If no browser appeared, use the fallback helper and try again.",
            ]
        if browser_reachable and launch_mode == "bridge":
            instructions = [
                "The sign-in browser is open and detectable from the platform.",
                "Complete sign-in in that browser window, then finish the connection here.",
            ]
        if session_path:
            instructions = [
                "A browser session is already stored for this connection.",
                "You can reuse it for monitoring and application runs.",
            ]
        helper_command = metadata.get("capture_helper_command") if manual_action_required else None
        if not helper_command and manual_action_required and isinstance(port, int):
            helper_command = self._browser_helper_command(record.id, str(login_url) if login_url else None, port)
        merged_details = dict(details or {})
        merged_details.setdefault("launch_mode", launch_mode)
        merged_details.setdefault("manual_action_required", manual_action_required)
        merged_details.setdefault("launch_message", metadata.get("capture_launch_message"))
        return IntegrationBrowserCaptureRead(
            connection_id=record.id,
            provider_key=record.provider_key,
            provider_name=provider.name,
            status=status,
            login_url=str(login_url) if login_url else None,
            helper_script_path=str(metadata.get("capture_helper_script_path") or ".\\launch-browser-session.ps1"),
            helper_command=str(helper_command) if helper_command else None,
            debug_port=int(port) if isinstance(port, int) else None,
            browser_reachable=browser_reachable,
            has_session_state=bool(session_path),
            session_state_filename=str(metadata.get("session_state_filename") or (session_path.name if session_path else "")) or None,
            started_at=self._parse_timestamp(metadata.get("capture_started_at")),
            last_checked_at=self._parse_timestamp(metadata.get("capture_last_checked_at")),
            instructions=instructions,
            details=merged_details,
        )





