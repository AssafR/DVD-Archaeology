from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.stages.extract import run as extract_run
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.stages.segments import run as segments_run
from dvdmenu_extract.stages.timing import run as timing_run
from dvdmenu_extract.stages.verify_extract import run as verify_run
from tests.helpers import fixtures_dir, load_expected_json


def test_stage_verify_extract_stub(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    ingest_run(input_path, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path, allow_dvd_ifo_fallback=True)
    menu_map_run(tmp_path / "nav.json", tmp_path)
    timing_run(
        tmp_path / "nav.json",
        tmp_path / "ingest.json",
        tmp_path / "menu_map.json",
        tmp_path,
        use_real_timing=False,
    )
    segments_run(tmp_path / "menu_map.json", tmp_path / "timing.json", tmp_path)
    extract_run(
        tmp_path / "segments.json",
        tmp_path / "ingest.json",
        tmp_path / "menu_map.json",
        tmp_path,
        use_real_ffmpeg=False,
        repair="off",
    )
    verify = verify_run(tmp_path / "segments.json", tmp_path / "extract.json", tmp_path)

    assert (tmp_path / "verify.json").is_file()
    assert verify.model_dump(mode="json") == load_expected_json("verify.json")
