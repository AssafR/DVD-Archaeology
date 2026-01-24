from __future__ import annotations

"""Stage E: timing.

Resolves timing information from the NavigationModel into a simple list of
entry_id -> start/end timestamps. This stage should not rename or extract
media; it only produces timing.json for downstream segments/extract stages.
"""

from pathlib import Path

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.io import read_json, write_json


def run(nav_path: Path, out_dir: Path) -> SegmentsModel:
    nav = read_json(nav_path, NavigationModel)

    if nav.disc_format == DiscFormat.DVD:
        if nav.dvd is None:
            raise ValidationError("DVD navigation missing dvd section")
        segments = []
        for title in nav.dvd.titles:
            for pgc in title.pgcs:
                for cell in pgc.cells:
                    entry_id = f"btn{cell.cell_id}"
                    segments.append(
                        {
                            "entry_id": entry_id,
                            "start_time": cell.start_time,
                            "end_time": cell.end_time,
                        }
                    )
        model = SegmentsModel.model_validate({"segments": segments})
        write_json(out_dir / "timing.json", model)
        return model

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
        write_json(out_dir / "timing.json", model)
        return model

    raise ValidationError("Timing stage does not support this disc format yet")
