from datetime import datetime
from typing import Any

from pydantic import BaseModel

from backend.app.schemas.common import ORMModel


class IntegrationProviderFieldRead(BaseModel):
    key: str
    label: str
    input_type: str
    required: bool = False
    secret: bool = False
    placeholder: str | None = None
    help_text: str | None = None


class IntegrationProviderRead(BaseModel):
    key: str
    name: str
    category: str
    auth_type: str
    description: str
    capabilities: list[str]
    fields: list[IntegrationProviderFieldRead]
    default_scopes: list[str] = []
    launch_url: str | None = None


class IntegrationConnectionCreate(BaseModel):
    name: str
    provider_key: str
    login_hint: str | None = None
    settings_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class IntegrationConnectionRead(ORMModel):
    id: str
    name: str
    provider_key: str
    category: str
    auth_type: str
    status: str
    login_hint: str | None
    settings_json: dict[str, Any] | None
    scopes_json: list[str]
    secret_fields_present: list[str]
    last_connected_at: datetime | None
    last_tested_at: datetime | None
    error_message: str | None
    metadata_json: dict[str, Any] | None
    has_session_state: bool = False
    session_state_filename: str | None = None


class IntegrationConnectResponse(BaseModel):
    status: str
    connection_id: str
    auth_url: str | None = None
    redirect_uri: str | None = None
    launch_url: str | None = None
    instructions: list[str] = []
    details: dict[str, Any] | None = None

class IntegrationBrowserCaptureRead(BaseModel):
    connection_id: str
    provider_key: str
    provider_name: str
    status: str
    login_url: str | None = None
    helper_script_path: str | None = None
    helper_command: str | None = None
    debug_port: int | None = None
    browser_reachable: bool = False
    has_session_state: bool = False
    session_state_filename: str | None = None
    started_at: datetime | None = None
    last_checked_at: datetime | None = None
    instructions: list[str] = []
    details: dict[str, Any] | None = None
