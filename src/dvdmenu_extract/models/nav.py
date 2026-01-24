from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.svcd_nav import SvcdNavModel
from dvdmenu_extract.models.vcd_nav import VcdNavModel


class DvdCellModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: int
    start_time: float
    end_time: float

    @model_validator(mode="after")
    def _validate(self) -> "DvdCellModel":
        if self.cell_id <= 0:
            raise ValueError("cell_id must be positive")
        if self.start_time < 0 or self.end_time < 0:
            raise ValueError("cell times must be non-negative")
        if self.end_time <= self.start_time:
            raise ValueError("cell end_time must be greater than start_time")
        return self


class DvdPgcModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pgc_id: int
    cells: list[DvdCellModel]

    @model_validator(mode="after")
    def _validate(self) -> "DvdPgcModel":
        if self.pgc_id <= 0:
            raise ValueError("pgc_id must be positive")
        cell_ids = [cell.cell_id for cell in self.cells]
        if len(cell_ids) != len(set(cell_ids)):
            raise ValueError("cell_id must be unique within pgc")
        return self


class DvdTitleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_id: int
    pgcs: list[DvdPgcModel]

    @model_validator(mode="after")
    def _validate(self) -> "DvdTitleModel":
        if self.title_id <= 0:
            raise ValueError("title_id must be positive")
        pgc_ids = [pgc.pgc_id for pgc in self.pgcs]
        if len(pgc_ids) != len(set(pgc_ids)):
            raise ValueError("pgc_id must be unique within title")
        return self


class DvdNavigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titles: list[DvdTitleModel]
    menu_domains: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "DvdNavigationModel":
        title_ids = [title.title_id for title in self.titles]
        if len(title_ids) != len(set(title_ids)):
            raise ValueError("title_id must be unique")
        return self


class SvcdNavigationModel(SvcdNavModel):
    model_config = ConfigDict(extra="forbid")


class NavigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disc_format: DiscFormat
    dvd: DvdNavigationModel | None = None
    svcd: SvcdNavigationModel | None = None
    vcd: VcdNavModel | None = None

    @model_validator(mode="after")
    def _validate(self) -> "NavigationModel":
        if self.disc_format not in DiscFormat:
            raise ValueError("disc_format must be a valid DiscFormat")
        if self.disc_format == "DVD" and self.dvd is None:
            raise ValueError("dvd field required for disc_format=DVD")
        if self.disc_format != "DVD" and self.dvd is not None:
            raise ValueError("dvd field must be null when disc_format is not DVD")
        if self.disc_format == "SVCD" and self.svcd is None:
            raise ValueError("svcd field required for disc_format=SVCD")
        if self.disc_format != "SVCD" and self.svcd is not None:
            raise ValueError("svcd field must be null when disc_format is not SVCD")
        if self.disc_format == "VCD" and self.vcd is None:
            raise ValueError("vcd field required for disc_format=VCD")
        if self.disc_format != "VCD" and self.vcd is not None:
            raise ValueError("vcd field must be null when disc_format is not VCD")
        return self
