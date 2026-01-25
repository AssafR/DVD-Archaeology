from __future__ import annotations

import json
from pathlib import Path

from dvdmenu_extract.pipeline import PipelineOptions, run_pipeline
from tests.helpers import fixtures_dir, load_expected_json


def test_pipeline_stub_e2e(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    options = PipelineOptions(
        ocr_lang="eng+heb",
        use_real_ocr=False,
        use_real_ffmpeg=False,
        repair="off",
        force=True,
        json_out_root=False,
        json_root_dir=False,
        use_real_timing=False,
        allow_dvd_ifo_fallback=True,
    )
    run_pipeline(input_path=input_path, out_dir=tmp_path, options=options)

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file()
    assert (tmp_path / "menu_images").is_dir()
    assert (tmp_path / "episodes").is_dir()

    expected_ocr = load_expected_json("ocr.json")
    for entry in expected_ocr["results"]:
        filename = f"{entry['cleaned_label']}.mkv"
        assert (tmp_path / "episodes" / filename).is_file()

    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert "ingest" in manifest
    assert "extract" in manifest
