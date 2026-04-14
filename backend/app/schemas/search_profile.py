from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.common import ORMModel


class SearchProfileBase(BaseModel):
    name: str
    roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_policy: str = "hybrid"
    salary_floor: int | None = None
    source_allowlist: list[str] = Field(default_factory=list)
    daily_cap: int = 15
    review_policy: str = "mixed"
    schedule_window: dict[str, Any] | None = None


class SearchProfileCreate(SearchProfileBase):
    pass


class SearchProfileRead(SearchProfileBase, ORMModel):
    id: str
