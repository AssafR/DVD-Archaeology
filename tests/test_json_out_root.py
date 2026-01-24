from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.pipeline import PipelineOptions, run_pipeline
from tests.helpers import fixtures_dir


def test_json_out_root_exports(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    options = PipelineOptions(
        ocr_lang="eng+heb",
        use_real_ocr=False,
        use_real_ffmpeg=False,
        repair="off",
        force=True,
        json_out_root=True,
        json_root_dir=False,
    )
    run_pipeline(input_path=input_path, out_dir=tmp_path, options=options, stage="ingest")

    export_root = input_path / "dvdmenu_extract_json"
    assert (export_root / "ingest.json").is_file()


def test_json_root_dir_reads_from_disc_root(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    options = PipelineOptions(
        ocr_lang="eng+heb",
        use_real_ocr=False,
        use_real_ffmpeg=False,
        repair="off",
        force=True,
        json_out_root=False,
        json_root_dir=True,
    )
    run_pipeline(input_path=input_path, out_dir=tmp_path, options=options, stage="ingest")
    run_pipeline(input_path=input_path, out_dir=tmp_path, options=options, stage="nav_parse")

    export_root = input_path / "dvdmenu_extract_json"
    assert (export_root / "ingest.json").is_file()
    assert (export_root / "nav.json").is_file()