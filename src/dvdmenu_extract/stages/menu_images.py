from __future__ import annotations

"""Stage D: menu_images.

Produces per-entry image crops used for OCR. For non-DVD formats, this stage
generates placeholders when no fixture images are available.
"""

import shutil
from pathlib import Path

from dvdmenu_extract.models.menu import MenuImagesModel, MenuImageEntry, MenuMapModel
from dvdmenu_extract.util.assertx import ValidationError, assert_in_out_dir
from dvdmenu_extract.util.fixtures import menu_buttons_dir
from dvdmenu_extract.util.io import read_json, write_json
import base64


def run(menu_map_path: Path, out_dir: Path) -> MenuImagesModel:
    menu_map = read_json(menu_map_path, MenuMapModel)
    output_dir = out_dir / "menu_images"
    output_dir.mkdir(parents=True, exist_ok=True)

    entries: list[MenuImageEntry] = []
    placeholder_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+7VZkAAAAASUVORK5CYII="
    )
    for entry in menu_map.entries:
        src = menu_buttons_dir() / f"{entry.entry_id}.png"
        dst = output_dir / f"{entry.entry_id}.png"
        assert_in_out_dir(dst, out_dir)
        if src.is_file():
            shutil.copyfile(src, dst)
        else:
            if entry.target.kind == "dvd_cell":
                raise ValidationError(f"Missing menu image fixture: {src}")
            dst.write_bytes(placeholder_png)
        entries.append(
            MenuImageEntry(
                entry_id=entry.entry_id,
                image_path=str(dst),
                menu_id=entry.menu_id,
                selection_rect=entry.selection_rect,
                highlight_rect=entry.highlight_rect,
                target=entry.target,
            )
        )

    model = MenuImagesModel(images=entries)
    write_json(out_dir / "menu_images.json", model)
    return model
