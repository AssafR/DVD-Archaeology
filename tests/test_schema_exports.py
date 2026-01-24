from __future__ import annotations

import json
from pathlib import Path

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.util.schemas import write_model_schema


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_enum(schema: dict, prop: str) -> list[str]:
    prop_schema = schema["properties"][prop]
    if "enum" in prop_schema:
        return prop_schema["enum"]
    ref = prop_schema.get("$ref")
    if ref and ref.startswith("#/$defs/"):
        key = ref.split("/")[-1]
        return schema["$defs"][key]["enum"]
    raise KeyError(f"enum not found for property: {prop}")


def test_schema_export_includes_disc_format_enum(tmp_path: Path) -> None:
    ingest_schema = write_model_schema(tmp_path, "ingest", IngestModel)
    nav_schema = write_model_schema(tmp_path, "nav", NavigationModel)

    ingest = _load_json(ingest_schema)
    nav = _load_json(nav_schema)

    allowed = [value for value in DiscFormat]
    assert _resolve_enum(ingest, "disc_type_guess") == allowed
    assert _resolve_enum(nav, "disc_format") == allowed
