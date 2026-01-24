from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from tests.helpers import fixtures_dir, load_expected_json


def test_stage_nav_parse(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    ingest_run(input_path, tmp_path)
    nav = nav_parse_run(tmp_path / "ingest.json", tmp_path)

    assert (tmp_path / "nav.json").is_file()
    assert nav.model_dump(mode="json") == load_expected_json("nav.json")
