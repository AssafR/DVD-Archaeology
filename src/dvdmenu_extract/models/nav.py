from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CellModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: int
    start_time: float
    end_time: float

    @model_validator(mode="after")
    def _validate(self) -> "CellModel":
        if self.cell_id <= 0:
            raise ValueError("cell_id must be positive")
        if self.start_time < 0 or self.end_time < 0:
            raise ValueError("cell times must be non-negative")
        if self.end_time <= self.start_time:
            raise ValueError("cell end_time must be greater than start_time")
        return self


class PgcModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pgc_id: int
    cells: list[CellModel]

    @model_validator(mode="after")
    def _validate(self) -> "PgcModel":
        if self.pgc_id <= 0:
            raise ValueError("pgc_id must be positive")
        cell_ids = [cell.cell_id for cell in self.cells]
        if len(cell_ids) != len(set(cell_ids)):
            raise ValueError("cell_id must be unique within pgc")
        return self


class TitleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_id: int
    pgcs: list[PgcModel]

    @model_validator(mode="after")
    def _validate(self) -> "TitleModel":
        if self.title_id <= 0:
            raise ValueError("title_id must be positive")
        pgc_ids = [pgc.pgc_id for pgc in self.pgcs]
        if len(pgc_ids) != len(set(pgc_ids)):
            raise ValueError("pgc_id must be unique within title")
        return self


class NavModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titles: list[TitleModel]
    menu_domains: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "NavModel":
        title_ids = [title.title_id for title in self.titles]
        if len(title_ids) != len(set(title_ids)):
            raise ValueError("title_id must be unique")
        return self
