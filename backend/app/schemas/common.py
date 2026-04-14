from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator
from pydantic_core import PydanticUndefined


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def coerce_null_to_declared_default(cls, value: Any, info: ValidationInfo) -> Any:
        if value is not None:
            return value
        field = cls.model_fields.get(info.field_name)
        if field is None:
            return value
        if field.default_factory is not None:
            return field.default_factory()
        if field.default is not PydanticUndefined:
            return field.default
        return value


class HealthResponse(BaseModel):
    status: str
    environment: str
    timestamp: datetime
