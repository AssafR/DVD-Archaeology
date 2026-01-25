from __future__ import annotations

from pathlib import Path

import pytest

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.models.nav_summary import NavSummaryModel
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.util.io import read_json
from tests.sample_paths import SAMPLE_PATHS, SampleSpec


def _run_nav_parse(tmp_path: Path, spec: SampleSpec) -> tuple[NavigationModel, NavSummaryModel]:
    ingest_run(spec.path, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path, allow_dvd_ifo_fallback=True)
    nav = read_json(tmp_path / "nav.json", NavigationModel)
    summary = read_json(tmp_path / "nav_summary.json", NavSummaryModel)
    return nav, summary


@pytest.mark.parametrize("disc_format", [DiscFormat.DVD, DiscFormat.SVCD, DiscFormat.VCD])
def test_nav_parse_samples(tmp_path: Path, disc_format: DiscFormat) -> None:
    specs = SAMPLE_PATHS[disc_format]
    if not specs:
        pytest.skip(f"No sample paths configured for {disc_format}")

    for spec in specs:
        if not spec.path.exists():
            pytest.skip(f"Sample path missing: {spec.path}")
        nav, summary = _run_nav_parse(tmp_path, spec)

        assert nav.disc_format == disc_format
        assert summary.disc_format == disc_format

        expected_tracks = (
            spec.expected_nav_tracks
            if spec.expected_nav_tracks is not None
            else spec.expected_tracks
        )
        if expected_tracks is not None:
            assert summary.tracks == expected_tracks

        if disc_format == DiscFormat.DVD:
            assert nav.dvd is not None
            assert summary.cells == summary.tracks
            assert summary.titles is not None
            assert summary.pgcs is not None
        if disc_format == DiscFormat.SVCD:
            assert nav.svcd is not None
            assert summary.control_files is not None
            assert summary.control_files.get("info") is True
            assert summary.control_files.get("entries") is True
        if disc_format == DiscFormat.VCD:
            assert nav.vcd is not None
            assert summary.control_files is not None
            assert summary.control_files.get("info") is True
            assert summary.control_files.get("entries") is True
