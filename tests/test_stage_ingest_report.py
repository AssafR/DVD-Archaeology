from __future__ import annotations

from pathlib import Path

import pytest

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.util.video_tracks import list_video_tracks
from tests.sample_paths import SAMPLE_PATHS, SampleSpec


def _count_tracks(spec: SampleSpec, disc_format: DiscFormat) -> int:
    if spec.count_globs:
        return sum(len(list(spec.path.glob(pattern))) for pattern in spec.count_globs)
    return len(list_video_tracks(spec.path, disc_format))


@pytest.mark.parametrize("disc_format", [DiscFormat.DVD, DiscFormat.SVCD, DiscFormat.VCD])
def test_ingest_disc_report_fields(tmp_path: Path, disc_format: DiscFormat) -> None:
    specs = SAMPLE_PATHS[disc_format]
    if not specs:
        pytest.skip(f"No sample paths configured for {disc_format}")

    for spec in specs:
        if not spec.path.exists():
            pytest.skip(f"Sample path missing: {spec.path}")
        ingest = ingest_run(spec.path, tmp_path)

        assert ingest.disc_report is not None
        assert ingest.disc_report.disc_format == disc_format
        assert ingest.disc_report.file_count > 0
        assert ingest.disc_report.total_bytes > 0
        assert len(ingest.disc_report.directories) >= 1
        assert (tmp_path / "disc_report.json").is_file()

        track_count = _count_tracks(spec, disc_format)
        if spec.expected_tracks is not None:
            assert track_count == spec.expected_tracks
            assert ingest.disc_report.video_track_count == spec.expected_tracks
        assert ingest.disc_report.video_track_count == len(
            ingest.disc_report.video_track_files
        )