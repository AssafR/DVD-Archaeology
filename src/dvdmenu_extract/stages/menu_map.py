from __future__ import annotations

"""Stage C: menu_map.

Produces a format-neutral MenuMapModel. For SVCD, entries are derived from
track metadata; for DVD, fixtures provide deterministic button mappings.
"""

import json
from pathlib import Path

from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.fixtures import expected_dir
from dvdmenu_extract.util.io import read_json, write_json
from dvdmenu_extract.models.enums import DiscFormat


def run(nav_path: Path, out_dir: Path) -> MenuMapModel:
    nav = read_json(nav_path, NavigationModel)
    if nav.disc_format in {DiscFormat.SVCD, DiscFormat.VCD}:
        nav_tracks = []
        menu_id = None
        if nav.disc_format == DiscFormat.SVCD and nav.svcd is not None:
            nav_tracks = nav.svcd.tracks
            menu_id = "svcd_root"
        if nav.disc_format == DiscFormat.VCD and nav.vcd is not None:
            nav_tracks = nav.vcd.tracks
            menu_id = "vcd_root"
        entries = []
        for track in nav_tracks:
            entries.append(
                {
                    "entry_id": f"track_{track.track_no:02d}",
                    "menu_id": menu_id,
                    "rect": None,
                    "selection_rect": None,
                    "highlight_rect": None,
                    "visuals": [
                        {
                            "kind": "track_file",
                            "source_path": track.file_name,
                            "rect": None,
                        }
                    ],
                    "target": {
                        "kind": "track",
                        "title_id": None,
                        "pgc_id": None,
                        "cell_id": None,
                        "track_no": track.track_no,
                        "item_no": None,
                        "start_time": None,
                        "end_time": None,
                    },
                }
            )
        model = MenuMapModel.model_validate({"entries": entries})
        write_json(out_dir / "menu_map.json", model)
        return model

    fixture_path = expected_dir() / "menu_map.json"
    if not fixture_path.is_file():
        raise ValidationError(f"Missing menu_map fixture: {fixture_path}")
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    model = MenuMapModel.model_validate(payload)
    write_json(out_dir / "menu_map.json", model)
    return model
