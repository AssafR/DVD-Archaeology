from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.util.assertx import assert_dir_exists
from dvdmenu_extract.util.io import utc_now_iso, write_json


def run(input_path: Path, out_dir: Path) -> IngestModel:
    assert_dir_exists(input_path, "Input path must be an existing directory")

    video_ts_path = input_path / "VIDEO_TS"
    has_video_ts = video_ts_path.is_dir()
    disc_type_guess = "DVD" if has_video_ts else "UNKNOWN"

    model = IngestModel(
        input_path=str(input_path),
        video_ts_path=str(video_ts_path),
        disc_type_guess=disc_type_guess,
        has_video_ts=has_video_ts,
        created_at=utc_now_iso(),
    )

    write_json(out_dir / "ingest.json", model)
    return model
