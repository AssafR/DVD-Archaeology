from __future__ import annotations

from pathlib import Path

import pytest

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.stages.segments import run as segments_run
from dvdmenu_extract.stages.timing import run as timing_run
from dvdmenu_extract.util.io import read_json
from tests.sample_paths import SAMPLE_PATHS


@pytest.mark.parametrize("spec", SAMPLE_PATHS[DiscFormat.DVD])
def test_segments_on_dvd_samples(tmp_path: Path, spec) -> None:
    if not spec.path.exists():
        pytest.skip(f"Sample path missing: {spec.path}")
    ingest_run(spec.path, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path, allow_dvd_ifo_fallback=True)
    menu_map_run(tmp_path / "nav.json", tmp_path)
    timing_run(
        tmp_path / "nav.json",
        tmp_path / "ingest.json",
        tmp_path / "menu_map.json",
        tmp_path,
        use_real_timing=False,
    )
    segments_run(tmp_path / "menu_map.json", tmp_path / "timing.json", tmp_path)

    menu_map = read_json(tmp_path / "menu_map.json", MenuMapModel)
    segments = read_json(tmp_path / "segments.json", SegmentsModel)
    assert len(segments.segments) == len(menu_map.entries)
