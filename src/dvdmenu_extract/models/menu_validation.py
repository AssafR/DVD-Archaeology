from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MenuValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class MenuValidationMenuCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    menu_id: str
    menu_entry_count: int
    nav_button_count: int


class MenuValidationTargetKindCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    count: int


class MenuValidationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    disc_format: str
    menu_entry_count: int
    nav_button_count: int
    menu_counts: list[MenuValidationMenuCount] = Field(default_factory=list)
    target_kind_counts: list[MenuValidationTargetKindCount] = Field(default_factory=list)
    missing_in_menu_map: list[str] = Field(default_factory=list)
    missing_in_nav_buttons: list[str] = Field(default_factory=list)
    issues: list[MenuValidationIssue] = Field(default_factory=list)
