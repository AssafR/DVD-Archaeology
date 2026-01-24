from __future__ import annotations

import json
from pathlib import Path

from dvdmenu_extract.pipeline import PipelineOptions, run_pipeline
from tests.helpers import fixtures_dir, load_expected_json


def _schema_view(value):
    if isinstance(value, dict):
        return {key: _schema_view(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        if not value:
            return {"__list__": "empty"}
        return {"__list__": _schema_view(value[0])}
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def test_manifest_schema_snapshot(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    options = PipelineOptions(
        ocr_lang="eng+heb",
        use_real_ocr=False,
        use_real_ffmpeg=False,
        repair="off",
        force=True,
    )
    run_pipeline(input_path=input_path, out_dir=tmp_path, options=options)

    manifest_path = tmp_path / "manifest.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    schema = _schema_view(manifest)
    assert schema == load_expected_json("manifest_schema.json")
