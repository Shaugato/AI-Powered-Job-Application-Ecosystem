from typing import Any

from pydantic import BaseModel

from backend.app.schemas.common import ORMModel


class BaseProfileBase(BaseModel):
    full_name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    website: str | None = None
    summary: str | None = None
    skills_json: list[str] | None = None
    certifications_json: list[str] | None = None
    experience_json: list[dict[str, Any]] | None = None
    projects_json: list[dict[str, Any]] | None = None
    education_json: list[dict[str, Any]] | None = None
    metadata_json: dict[str, Any] | None = None


class BaseProfileCreate(BaseProfileBase):
    pass


class BaseProfileUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    website: str | None = None
    summary: str | None = None
    skills_json: list[str] | None = None
    certifications_json: list[str] | None = None
    experience_json: list[dict[str, Any]] | None = None
    projects_json: list[dict[str, Any]] | None = None
    education_json: list[dict[str, Any]] | None = None
    metadata_json: dict[str, Any] | None = None


class BaseProfileRead(BaseProfileBase, ORMModel):
    id: str
