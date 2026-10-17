"""Validated request schemas and typed response models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ConstructionType = Literal["residential_building", "commercial_building", "bridge", "road", "rail", "other"]
EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Strict):
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=200)


class RegisterIn(Strict):
    email: str = Field(pattern=EMAIL_PATTERN)
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: Literal["admin", "member"]
    created_at: datetime


class AuthOut(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"


class ProjectCreate(Strict):
    name: str = Field(min_length=3, max_length=120)
    construction_type: ConstructionType
    location: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)
    planned_start_date: date
    target_completion_date: date

    @model_validator(mode="after")
    def _dates(self) -> "ProjectCreate":
        if self.target_completion_date <= self.planned_start_date:
            raise ValueError("target_completion_date must be after planned_start_date")
        return self


class ReviewIn(Strict):
    stage_key: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    stage_progress: float | None = Field(None, ge=0, le=100, description="percent complete within the stage")


class ForecastPreviewIn(Strict):
    observation_id: str = Field(max_length=40)
    stage_key: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    stage_progress: float | None = Field(None, ge=0, le=100, description="None = unknown → returns a start/end range")
