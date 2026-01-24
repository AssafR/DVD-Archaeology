from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IngestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_path: str
    video_ts_path: str
    disc_type_guess: str
    has_video_ts: bool
    created_at: str = Field(..., description="UTC ISO timestamp")

    @model_validator(mode="after")
    def _validate(self) -> "IngestModel":
        if self.disc_type_guess not in {"DVD", "UNKNOWN"}:
            raise ValueError("disc_type_guess must be DVD or UNKNOWN")
        if self.has_video_ts and self.disc_type_guess != "DVD":
            raise ValueError("has_video_ts implies disc_type_guess=DVD")
        return self
