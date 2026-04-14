from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.schemas.common import ORMModel


class PromptVersionCreate(BaseModel):
    name: str
    role_tags: list[str] = Field(default_factory=list)
    prompt_text: str
    temperature: float = 0.2
    success_rate_metric: float = 0.0
    last_used_at: datetime | None = None


class PromptVersionRead(ORMModel):
    id: str
    name: str
    role_tags_json: list[str]
    prompt_text: str
    temperature: float
    success_rate_metric: float
    last_used_at: datetime | None
