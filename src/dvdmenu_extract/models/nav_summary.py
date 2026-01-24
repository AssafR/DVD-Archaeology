from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dvdmenu_extract.models.enums import DiscFormat


class NavSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disc_format: DiscFormat
    tracks: int
    entry_points: int
    titles: int | None = None
    pgcs: int | None = None
    cells: int | None = None
    menu_domains: int | None = None
    control_files: dict[str, bool] | None = None
