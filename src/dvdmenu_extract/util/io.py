from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from dvdmenu_extract.util.assertx import assert_file_exists, assert_in_out_dir

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class StageMeta:
    stage: str
    started_at: str
    finished_at: str
    duration_ms: int
    inputs: list[str]
    outputs: list[str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, model_type: type[T]) -> T:
    assert_file_exists(path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return model_type.model_validate(payload)


def write_json(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(model.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)


def write_raw_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def write_stage_meta(out_dir: Path, meta: StageMeta) -> None:
    meta_path = out_dir / "stage_meta" / f"{meta.stage}.json"
    assert_in_out_dir(meta_path, out_dir)
    write_raw_json(meta_path, meta.__dict__)
