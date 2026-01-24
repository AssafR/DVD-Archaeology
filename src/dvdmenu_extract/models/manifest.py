from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.menu import MenuImagesModel, MenuMapModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.models.ocr import OcrModel
from dvdmenu_extract.models.segments import SegmentsModel


class ExtractEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    output_path: str
    status: str


class ExtractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs: list[ExtractEntryModel]

    @model_validator(mode="after")
    def _validate(self) -> "ExtractModel":
        entry_ids = [entry.entry_id for entry in self.outputs]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("entry_id must be unique in extract outputs")
        return self


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str]
    ingest: IngestModel
    nav: NavigationModel
    menu_map: MenuMapModel
    menu_images: MenuImagesModel
    ocr: OcrModel
    segments: SegmentsModel
    extract: ExtractModel
    stage_status: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> "ManifestModel":
        entry_ids = {entry.entry_id for entry in self.ocr.results}
        for entry in self.segments.segments:
            if entry.entry_id not in entry_ids:
                raise ValueError("segments reference missing OCR entry_id")
        for entry in self.extract.outputs:
            if entry.entry_id not in entry_ids:
                raise ValueError("extract reference missing OCR entry_id")
        return self
