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


class ButtonTargetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_id: int
    pgc_id: int
    cell_id: int

    @model_validator(mode="after")
    def _validate(self) -> "ButtonTargetModel":
        if min(self.title_id, self.pgc_id, self.cell_id) <= 0:
            raise ValueError("target ids must be positive")
        return self


class ButtonModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    button_id: str
    rect: RectModel
    target: ButtonTargetModel


class MenuModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    menu_id: str
    buttons: list[ButtonModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "MenuModel":
        button_ids = [button.button_id for button in self.buttons]
        if len(button_ids) != len(set(button_ids)):
            raise ValueError("button_id must be unique within menu")
        return self


class MenuMapModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    menus: list[MenuModel]

    @model_validator(mode="after")
    def _validate(self) -> "MenuMapModel":
        menu_ids = [menu.menu_id for menu in self.menus]
        if len(menu_ids) != len(set(menu_ids)):
            raise ValueError("menu_id must be unique")
        return self


class MenuImageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    button_id: str
    image_path: str
    menu_id: str


class MenuImagesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    images: list[MenuImageEntry]

    @model_validator(mode="after")
    def _validate(self) -> "MenuImagesModel":
        button_ids = [entry.button_id for entry in self.images]
        if len(button_ids) != len(set(button_ids)):
            raise ValueError("button_id must be unique in menu images")
        return self
