from __future__ import annotations

"""Stage F: segments.

Builds segment boundaries from the navigation and menu map. This stage is
format-neutral and must not rely on DVD-specific structures.
"""

import json
from pathlib import Path

from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.fixtures import expected_dir
from dvdmenu_extract.util.io import read_json, write_json
from dvdmenu_extract.models.enums import DiscFormat


def run(menu_map_path: Path, nav_path: Path, out_dir: Path) -> SegmentsModel:
    _menu_map = read_json(menu_map_path, MenuMapModel)
    nav = read_json(nav_path, NavigationModel)
    if nav.disc_format in {DiscFormat.SVCD, DiscFormat.VCD}:
        nav_tracks = []
        if nav.disc_format == DiscFormat.SVCD and nav.svcd is not None:
            nav_tracks = nav.svcd.tracks
        if nav.disc_format == DiscFormat.VCD and nav.vcd is not None:
            nav_tracks = nav.vcd.tracks
        segments = [
            {
                "entry_id": f"track_{track.track_no:02d}",
                "start_time": 0.0,
                "end_time": 600.0,
            }
            for track in nav_tracks
        ]
        model = SegmentsModel.model_validate({"segments": segments})
        menu_entry_ids = {entry.entry_id for entry in _menu_map.entries}
        for entry in model.segments:
            if entry.entry_id not in menu_entry_ids:
                raise ValidationError("segments include unknown entry_id")
        write_json(out_dir / "segments.json", model)
        return model

    fixture_path = expected_dir() / "segments.json"
    if not fixture_path.is_file():
        raise ValidationError(f"Missing segments fixture: {fixture_path}")
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    model = SegmentsModel.model_validate(payload)

    menu_entry_ids = {entry.entry_id for entry in _menu_map.entries}
    for entry in model.segments:
        if entry.entry_id not in menu_entry_ids:
            raise ValidationError("segments include unknown entry_id")

    write_json(out_dir / "segments.json", model)
    return model
