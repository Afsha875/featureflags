"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import FlagType, Reason


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    api_key: str


class FlagCreate(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    flag_type: FlagType
    enabled: bool = True
    percentage: int = Field(default=0, ge=0, le=100)
    allowlist: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> FlagCreate:
        if self.flag_type is FlagType.PERCENTAGE and not (0 <= self.percentage <= 100):
            raise ValueError("percentage must be between 0 and 100")
        return self


class FlagUpdate(BaseModel):
    """Partial update. Only provided fields are changed."""

    enabled: bool | None = None
    flag_type: FlagType | None = None
    percentage: int | None = Field(default=None, ge=0, le=100)
    allowlist: list[str] | None = None


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    flag_type: FlagType
    enabled: bool
    percentage: int
    allowlist: list[str]


class EvaluateRequest(BaseModel):
    flag_key: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    attributes: dict[str, str] | None = None


class EvaluateResponse(BaseModel):
    flag_key: str
    enabled: bool
    reason: Reason
    bucket: int | None = None


class BatchEvaluateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    attributes: dict[str, str] | None = None


class BatchEvaluateResponse(BaseModel):
    user_id: str
    flags: dict[str, EvaluateResponse]
