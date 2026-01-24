from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SvcdTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track_no: int
    file_name: str
    size_bytes: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "SvcdTrack":
        if self.track_no <= 0:
            raise ValueError("track_no must be positive")
        return self


class SvcdEntryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track_no: int
    timecode: str


class SvcdNavModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "v1"
    source: str = "directory"
    control_files: dict[str, bool] = Field(default_factory=dict)
    tracks: list[SvcdTrack]
    entry_points: list[SvcdEntryPoint] = Field(default_factory=list)
