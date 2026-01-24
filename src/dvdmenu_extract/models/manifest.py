from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.menu import MenuImagesModel, MenuMapModel
from dvdmenu_extract.models.nav import NavModel
from dvdmenu_extract.models.ocr import OcrModel
from dvdmenu_extract.models.segments import SegmentsModel


class ExtractEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    button_id: str
    output_path: str
    status: str


class ExtractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs: list[ExtractEntryModel]

    @model_validator(mode="after")
    def _validate(self) -> "ExtractModel":
        button_ids = [entry.button_id for entry in self.outputs]
        if len(button_ids) != len(set(button_ids)):
            raise ValueError("button_id must be unique in extract outputs")
        return self


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str]
    ingest: IngestModel
    nav: NavModel
    menu_map: MenuMapModel
    menu_images: MenuImagesModel
    ocr: OcrModel
    segments: SegmentsModel
    extract: ExtractModel
    stage_status: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> "ManifestModel":
        button_ids = {entry.button_id for entry in self.ocr.results}
        for entry in self.segments.segments:
            if entry.button_id not in button_ids:
                raise ValueError("segments reference missing OCR button_id")
        for entry in self.extract.outputs:
            if entry.button_id not in button_ids:
                raise ValueError("extract reference missing OCR button_id")
        return self
