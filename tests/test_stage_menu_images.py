from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_images import run as menu_images_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from tests.helpers import fixtures_dir


def test_stage_menu_images(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    ingest_run(input_path, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path, allow_dvd_ifo_fallback=True)
    menu_map_run(tmp_path / "nav.json", tmp_path)

    menu_images = menu_images_run(tmp_path / "menu_map.json", tmp_path)
    assert (tmp_path / "menu_images.json").is_file()
    assert (tmp_path / "menu_images").is_dir()
    assert len(menu_images.images) == 3
    for entry in menu_images.images:
        assert Path(entry.image_path).is_file()
