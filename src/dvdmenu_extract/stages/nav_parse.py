from __future__ import annotations

import json
from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.nav import NavModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.fixtures import expected_dir
from dvdmenu_extract.util.io import read_json, write_json


def run(ingest_path: Path, out_dir: Path) -> NavModel:
    read_json(ingest_path, IngestModel)
    fixture_path = expected_dir() / "nav.json"
    if not fixture_path.is_file():
        raise ValidationError(f"Missing nav fixture: {fixture_path}")
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    model = NavModel.model_validate(payload)
    write_json(out_dir / "nav.json", model)
    return model
