from __future__ import annotations

"""Stage F: segments.

Builds segment boundaries from the navigation and menu map. This stage is
format-neutral and must not rely on DVD-specific structures.
"""

from pathlib import Path

from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.io import read_json, write_json


def run(menu_map_path: Path, timing_path: Path, out_dir: Path) -> SegmentsModel:
    menu_map = read_json(menu_map_path, MenuMapModel)
    timing = read_json(timing_path, SegmentsModel)

    menu_entry_ids = {entry.entry_id for entry in menu_map.entries}
    for entry in timing.segments:
        if entry.entry_id not in menu_entry_ids:
            raise ValidationError("segments include unknown entry_id")

    model = SegmentsModel.model_validate(
        {"segments": [segment.model_dump(mode="json") for segment in timing.segments]}
    )
    write_json(out_dir / "segments.json", model)
    return model
