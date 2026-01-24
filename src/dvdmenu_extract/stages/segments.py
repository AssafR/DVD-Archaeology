from __future__ import annotations

import json
from pathlib import Path

from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.nav import NavModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.fixtures import expected_dir
from dvdmenu_extract.util.io import read_json, write_json


def run(menu_map_path: Path, nav_path: Path, out_dir: Path) -> SegmentsModel:
    _menu_map = read_json(menu_map_path, MenuMapModel)
    read_json(nav_path, NavModel)
    fixture_path = expected_dir() / "segments.json"
    if not fixture_path.is_file():
        raise ValidationError(f"Missing segments fixture: {fixture_path}")
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    model = SegmentsModel.model_validate(payload)

    menu_button_ids = {
        button.button_id for menu in _menu_map.menus for button in menu.buttons
    }
    for entry in model.segments:
        if entry.button_id not in menu_button_ids:
            raise ValidationError("segments include unknown button_id")

    write_json(out_dir / "segments.json", model)
    return model
