from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.stages.segments import run as segments_run
from tests.helpers import fixtures_dir, load_expected_json


def test_stage_segments_stub(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    ingest_run(input_path, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path)
    menu_map_run(tmp_path / "nav.json", tmp_path)

    segments = segments_run(tmp_path / "menu_map.json", tmp_path / "nav.json", tmp_path)
    assert (tmp_path / "segments.json").is_file()
    assert segments.model_dump(mode="json") == load_expected_json("segments.json")
