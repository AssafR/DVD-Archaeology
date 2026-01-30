from __future__ import annotations

from pathlib import Path

import pytest

from dvdmenu_extract.models.menu import MenuEntryModel, MenuMapModel, MenuTargetModel, RectModel
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_images import run as menu_images_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.io import write_json
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


def test_menu_images_rejects_overlapping_rects(tmp_path: Path) -> None:
    menu_map = MenuMapModel(
        entries=[
            MenuEntryModel(
                entry_id="btn1",
                menu_id="VTSM_01_pgc01",
                selection_rect=RectModel(x=10, y=10, w=120, h=50),
                target=MenuTargetModel(kind="dvd_pgc", title_id=1, pgc_id=1),
            ),
            MenuEntryModel(
                entry_id="btn2",
                menu_id="VTSM_01_pgc01",
                selection_rect=RectModel(x=30, y=20, w=120, h=50),
                target=MenuTargetModel(kind="dvd_pgc", title_id=1, pgc_id=2),
            ),
        ]
    )
    write_json(tmp_path / "menu_map.json", menu_map)

    with pytest.raises(ValidationError, match="overlapping button rects"):
        menu_images_run(tmp_path / "menu_map.json", tmp_path)
