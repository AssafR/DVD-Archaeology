from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VerifyEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    expected_duration: float
    actual_duration: float | None = None
    delta: float | None = None
    within_tolerance: bool | None = None
    status: str


class VerifyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    skipped: bool
    tolerance_sec: float
    results: list[VerifyEntryModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "VerifyModel":
        if self.tolerance_sec < 0:
            raise ValueError("tolerance_sec must be non-negative")
        return self
