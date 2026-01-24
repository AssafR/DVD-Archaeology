from __future__ import annotations

"""Stage A: ingest.

Validates the input disc directory and writes format-neutral reports that
summarize the detected layout and video assets. This stage sets the initial
disc format guess and produces JSON artifacts for downstream stages.
"""

from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.util.assertx import assert_dir_exists
from dvdmenu_extract.util.io import utc_now_iso, write_json
from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.util.disc_report import build_disc_report
from dvdmenu_extract.util.video_ts import build_video_ts_report


def run(input_path: Path, out_dir: Path) -> IngestModel:
    assert_dir_exists(input_path, "Input path must be an existing directory")

    video_ts_path = input_path / "VIDEO_TS"
    has_video_ts = video_ts_path.is_dir()
    report = build_video_ts_report(video_ts_path) if has_video_ts else None
    disc_report = build_disc_report(input_path)
    if has_video_ts:
        disc_type_guess = DiscFormat.DVD
    elif disc_report.disc_format == DiscFormat.SVCD:
        disc_type_guess = DiscFormat.SVCD
    elif disc_report.disc_format == DiscFormat.VCD:
        disc_type_guess = DiscFormat.VCD
    else:
        disc_type_guess = DiscFormat.UNKNOWN

    model = IngestModel(
        input_path=str(input_path),
        video_ts_path=str(video_ts_path),
        disc_type_guess=disc_type_guess,
        has_video_ts=has_video_ts,
        created_at=utc_now_iso(),
        video_ts_report=report,
        disc_report=disc_report,
    )

    write_json(out_dir / "ingest.json", model)
    if report is not None:
        write_json(out_dir / "video_ts_report.json", report)
    write_json(out_dir / "disc_report.json", disc_report)
    return model
