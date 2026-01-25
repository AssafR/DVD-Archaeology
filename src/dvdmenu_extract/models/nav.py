from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.menu import RectModel
from dvdmenu_extract.models.svcd_nav import SvcdNavModel
from dvdmenu_extract.models.vcd_nav import VcdNavModel


class DvdCellModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: int
    start_time: float
    end_time: float
    first_sector: int | None = None
    last_sector: int | None = None
    vob_id: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "DvdCellModel":
        if self.cell_id <= 0:
            raise ValueError("cell_id must be positive")
        if self.start_time < 0 or self.end_time < 0:
            raise ValueError("cell times must be non-negative")
        if self.end_time <= self.start_time:
            raise ValueError("cell end_time must be greater than start_time")
        if (self.first_sector is None) != (self.last_sector is None):
            raise ValueError("first_sector and last_sector must be provided together")
        if self.first_sector is not None:
            if self.first_sector < 0 or self.last_sector < 0:
                raise ValueError("sector values must be non-negative")
            if self.last_sector < self.first_sector:
                raise ValueError("last_sector must be >= first_sector")
        if self.vob_id is not None and self.vob_id <= 0:
            raise ValueError("vob_id must be positive when provided")
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


class DvdMenuButtonModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    button_id: str
    menu_id: str
    title_id: int
    pgc_id: int
    selection_rect: RectModel | None = None
    highlight_rect: RectModel | None = None

    @model_validator(mode="after")
    def _validate(self) -> "DvdMenuButtonModel":
        if not self.button_id:
            raise ValueError("button_id must be non-empty")
        if not self.menu_id:
            raise ValueError("menu_id must be non-empty")
        if self.title_id <= 0 or self.pgc_id <= 0:
            raise ValueError("title_id/pgc_id must be positive")
        return self


class DvdNavigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titles: list[DvdTitleModel]
    menu_domains: list[str] = Field(default_factory=list)
    menu_buttons: list[DvdMenuButtonModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "DvdNavigationModel":
        title_ids = [title.title_id for title in self.titles]
        if len(title_ids) != len(set(title_ids)):
            raise ValueError("title_id must be unique")
        button_ids = [button.button_id for button in self.menu_buttons]
        if len(button_ids) != len(set(button_ids)):
            raise ValueError("button_id must be unique")
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
