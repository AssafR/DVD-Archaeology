from __future__ import annotations

import json
from pathlib import Path

from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.nav import NavModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.fixtures import expected_dir
from dvdmenu_extract.util.io import read_json, write_json


def run(nav_path: Path, out_dir: Path) -> MenuMapModel:
    read_json(nav_path, NavModel)
    fixture_path = expected_dir() / "menu_map.json"
    if not fixture_path.is_file():
        raise ValidationError(f"Missing menu_map fixture: {fixture_path}")
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    model = MenuMapModel.model_validate(payload)
    write_json(out_dir / "menu_map.json", model)
    return model
