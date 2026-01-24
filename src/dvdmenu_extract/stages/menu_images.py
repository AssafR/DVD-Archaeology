from __future__ import annotations

import shutil
from pathlib import Path

from dvdmenu_extract.models.menu import MenuImagesModel, MenuImageEntry, MenuMapModel
from dvdmenu_extract.util.assertx import ValidationError, assert_in_out_dir
from dvdmenu_extract.util.fixtures import menu_buttons_dir
from dvdmenu_extract.util.io import read_json, write_json


def run(menu_map_path: Path, out_dir: Path) -> MenuImagesModel:
    menu_map = read_json(menu_map_path, MenuMapModel)
    output_dir = out_dir / "menu_images"
    output_dir.mkdir(parents=True, exist_ok=True)

    entries: list[MenuImageEntry] = []
    for menu in menu_map.menus:
        for button in menu.buttons:
            src = menu_buttons_dir() / f"{button.button_id}.png"
            if not src.is_file():
                raise ValidationError(f"Missing menu image fixture: {src}")
            dst = output_dir / f"{button.button_id}.png"
            assert_in_out_dir(dst, out_dir)
            shutil.copyfile(src, dst)
            entries.append(
                MenuImageEntry(
                    button_id=button.button_id,
                    image_path=str(dst),
                    menu_id=menu.menu_id,
                )
            )

    model = MenuImagesModel(images=entries)
    write_json(out_dir / "menu_images.json", model)
    return model
