from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dvdmenu_extract.models.enums import DiscFormat


class VideoTsFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    size_bytes: int


class VideoTsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_count: int
    total_bytes: int
    vts_title_count: int
    ifo_total_bytes: int
    bup_total_bytes: int
    vob_total_bytes: int
    files: list[VideoTsFileEntry]


class DiscFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    size_bytes: int


class DiscReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disc_format: DiscFormat
    file_count: int
    total_bytes: int
    directories: list[str]
    files: list[DiscFileEntry]
    video_ts_report: VideoTsReport | None = None
    mpeg2_file_count: int | None = None
    mpeg2_total_bytes: int | None = None
    mpegav_file_count: int | None = None
    mpegav_total_bytes: int | None = None
    video_track_count: int
    video_track_files: list[str]


class IngestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_path: str
    video_ts_path: str
    disc_type_guess: DiscFormat
    has_video_ts: bool
    created_at: str = Field(..., description="UTC ISO timestamp")
    video_ts_report: VideoTsReport | None = None
    disc_report: DiscReport | None = None

    @model_validator(mode="after")
    def _validate(self) -> "IngestModel":
        if self.disc_type_guess not in DiscFormat:
            raise ValueError("disc_type_guess must be a valid DiscFormat")
        if self.has_video_ts and self.disc_type_guess != "DVD":
            raise ValueError("has_video_ts implies disc_type_guess=DVD")
        if self.has_video_ts and self.video_ts_report is None:
            raise ValueError("video_ts_report required when VIDEO_TS exists")
        if self.disc_report is None:
            raise ValueError("disc_report required")
        return self
