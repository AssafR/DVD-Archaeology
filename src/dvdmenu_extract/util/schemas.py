from __future__ import annotations

from pathlib import Path
from typing import Type

from pydantic import BaseModel

from dvdmenu_extract.util.assertx import assert_in_out_dir
from dvdmenu_extract.util.io import write_raw_json


def write_model_schema(out_dir: Path, name: str, model: Type[BaseModel]) -> Path:
    schema_path = out_dir / "schemas" / f"{name}.schema.json"
    assert_in_out_dir(schema_path, out_dir)
    schema = model.model_json_schema()
    write_raw_json(schema_path, schema)
    return schema_path
