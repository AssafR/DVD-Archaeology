from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OcrEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    button_id: str
    raw_text: str
    cleaned_label: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class OcrModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[OcrEntryModel]

    @model_validator(mode="after")
    def _validate(self) -> "OcrModel":
        button_ids = [entry.button_id for entry in self.results]
        if len(button_ids) != len(set(button_ids)):
            raise ValueError("button_id must be unique in ocr results")
        return self
