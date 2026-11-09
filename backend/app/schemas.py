from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Talk(BaseModel):
    talk_id: str = Field(default_factory=lambda: str(uuid4()))
    title: NonEmpty
    abstract: str = Field(default="", max_length=10_000)
    tags: list[NonEmpty] = Field(default_factory=list, max_length=30)
    speaker_names: list[NonEmpty] = Field(default_factory=list, max_length=20)
    start_time: datetime
    end_time: datetime
    room: str | None = Field(default=None, max_length=300)

    @field_validator("start_time", "end_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("talk times must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def end_after_start(self) -> "Talk":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class Schedule(BaseModel):
    title: NonEmpty = "Conference Schedule"
    timezone: str = "UTC"
    warnings: list[str] = Field(default_factory=list, max_length=100)
    talks: list[Talk] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_talk_ids(self) -> "Schedule":
        ids = [talk.talk_id for talk in self.talks]
        if len(ids) != len(set(ids)):
            raise ValueError("talk_id values must be unique")
        return self


class ConfirmScheduleRequest(BaseModel):
    conference_id: NonEmpty
    draft_id: NonEmpty
    schedule: Schedule | None = None
