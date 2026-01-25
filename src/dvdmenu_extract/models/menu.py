from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RectModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    w: int
    h: int

    @model_validator(mode="after")
    def _validate(self) -> "RectModel":
        if min(self.x, self.y, self.w, self.h) < 0:
            raise ValueError("rect values must be non-negative")
        if self.w == 0 or self.h == 0:
            raise ValueError("rect w/h must be non-zero")
        return self


class MenuTargetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    title_id: int | None = None
    pgc_id: int | None = None
    cell_id: int | None = None
    track_no: int | None = None
    item_no: int | None = None
    start_time: float | None = None
    end_time: float | None = None

    @model_validator(mode="after")
    def _validate(self) -> "MenuTargetModel":
        if self.kind not in {
            "dvd_cell",
            "dvd_pgc",
            "time_range",
            "track",
            "segment_item",
        }:
            raise ValueError(
                "target kind must be dvd_cell, dvd_pgc, time_range, track, or segment_item"
            )
        if self.kind == "dvd_cell":
            if self.title_id is None or self.pgc_id is None or self.cell_id is None:
                raise ValueError("dvd_cell requires title_id/pgc_id/cell_id")
            if min(self.title_id, self.pgc_id, self.cell_id) <= 0:
                raise ValueError("dvd_cell ids must be positive")
        if self.kind == "dvd_pgc":
            if self.title_id is None or self.pgc_id is None:
                raise ValueError("dvd_pgc requires title_id/pgc_id")
            if min(self.title_id, self.pgc_id) <= 0:
                raise ValueError("dvd_pgc ids must be positive")
        if self.kind == "time_range":
            if (
                self.track_no is None
                or self.start_time is None
                or self.end_time is None
            ):
                raise ValueError("time_range requires track_no/start_time/end_time")
            if self.track_no <= 0:
                raise ValueError("time_range track_no must be positive")
            if self.start_time < 0 or self.end_time <= self.start_time:
                raise ValueError("time_range times must be non-negative and increasing")
        if self.kind == "track":
            if self.track_no is None or self.track_no <= 0:
                raise ValueError("track requires positive track_no")
        if self.kind == "segment_item":
            if self.item_no is None or self.item_no <= 0:
                raise ValueError("segment_item requires positive item_no")
        return self


class VisualRegionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    source_path: str | None = None
    rect: RectModel | None = None


class MenuEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    rect: RectModel | None = None
    selection_rect: RectModel | None = None
    highlight_rect: RectModel | None = None
    target: MenuTargetModel
    menu_id: str | None = None
    visuals: list[VisualRegionModel] = Field(default_factory=list)


class MenuMapModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[MenuEntryModel]

    @model_validator(mode="after")
    def _validate(self) -> "MenuMapModel":
        entry_ids = [entry.entry_id for entry in self.entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("entry_id must be unique")
        return self


class MenuImageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    image_path: str
    menu_id: str | None = None
    selection_rect: RectModel | None = None
    highlight_rect: RectModel | None = None
    target: MenuTargetModel | None = None


class MenuImagesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    images: list[MenuImageEntry]

    @model_validator(mode="after")
    def _validate(self) -> "MenuImagesModel":
        entry_ids = [entry.entry_id for entry in self.images]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("entry_id must be unique in menu images")
        return self
