from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.stages.extract import run as extract_run
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.stages.segments import run as segments_run
from tests.helpers import fixtures_dir


def test_stage_extract_stub(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    ingest_run(input_path, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path)
    menu_map_run(tmp_path / "nav.json", tmp_path)
    segments_run(tmp_path / "menu_map.json", tmp_path / "nav.json", tmp_path)

    extract = extract_run(
        tmp_path / "segments.json",
        tmp_path,
        use_real_ffmpeg=False,
        repair="off",
    )

    assert (tmp_path / "extract.json").is_file()
    assert (tmp_path / "episodes").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert len(extract.outputs) == 3
    for entry in extract.outputs:
        assert Path(entry.output_path).is_file()
