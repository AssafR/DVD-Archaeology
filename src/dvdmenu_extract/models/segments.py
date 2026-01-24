from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SegmentEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)

    @model_validator(mode="after")
    def _validate(self) -> "SegmentEntryModel":
        if self.end_time <= self.start_time:
            raise ValueError("segment end_time must be greater than start_time")
        return self


class SegmentsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[SegmentEntryModel]

    @model_validator(mode="after")
    def _validate(self) -> "SegmentsModel":
        entry_ids = [entry.entry_id for entry in self.segments]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("entry_id must be unique in segments")
        return self
