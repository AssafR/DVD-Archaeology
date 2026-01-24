from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OcrEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    raw_text: str
    cleaned_label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: str
    background_attempted: bool
    spu_text_nonempty: bool

    @model_validator(mode="after")
    def _validate(self) -> "OcrEntryModel":
        if self.source not in {"spu", "background"}:
            raise ValueError("source must be 'spu' or 'background'")
        valid_combo = (self.spu_text_nonempty and not self.background_attempted) or (
            (not self.spu_text_nonempty) and self.background_attempted
        )
        if not valid_combo:
            raise ValueError(
                "Exactly one of: spu_text_nonempty or background_attempted must be true"
            )
        if self.source == "spu" and not self.spu_text_nonempty:
            raise ValueError("source=spu requires spu_text_nonempty")
        if self.source == "background" and not self.background_attempted:
            raise ValueError("source=background requires background_attempted")
        return self


class OcrModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[OcrEntryModel]

    @model_validator(mode="after")
    def _validate(self) -> "OcrModel":
        entry_ids = [entry.entry_id for entry in self.results]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("entry_id must be unique in ocr results")
        return self
