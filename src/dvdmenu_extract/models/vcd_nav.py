from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from dvdmenu_extract.models.svcd_nav import SvcdEntryPoint, SvcdTrack


class VcdNavModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "v1"
    source: str = "directory"
    control_files: dict[str, bool] = Field(default_factory=dict)
    tracks: list[SvcdTrack]
    entry_points: list[SvcdEntryPoint] = Field(default_factory=list)
