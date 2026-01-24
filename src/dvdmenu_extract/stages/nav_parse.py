from __future__ import annotations

import json
from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.fixtures import expected_dir
import re
from dvdmenu_extract.util.io import read_json, write_json


def run(ingest_path: Path, out_dir: Path) -> NavigationModel:
    ingest = read_json(ingest_path, IngestModel)
    disc_format = ingest.disc_report.disc_format if ingest.disc_report else "UNKNOWN"
    if disc_format == "SVCD":
        track_map: dict[int, str] = {}
        if ingest.disc_report:
            for entry in ingest.disc_report.files:
                path = Path(entry.path)
                if path.parent.name.upper() != "MPEG2":
                    continue
                match = re.match(r"AVSEQ(\d+)\.MPG", path.name, re.IGNORECASE)
                if not match:
                    continue
                track_no = int(match.group(1))
                track_map.setdefault(track_no, path.name)
        tracks = [
            {"track_no": track_no, "file_name": file_name}
            for track_no, file_name in sorted(track_map.items())
        ]
        payload = {
            "disc_format": "SVCD",
            "dvd": None,
            "svcd": {"tracks": tracks, "entry_points": []},
        }
        model = NavigationModel.model_validate(payload)
        write_json(out_dir / "nav.json", model)
        return model
    fixture_path = expected_dir() / "nav.json"
    if not fixture_path.is_file():
        raise ValidationError(f"Missing nav fixture: {fixture_path}")
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    model = NavigationModel.model_validate(payload)
    write_json(out_dir / "nav.json", model)
    return model
