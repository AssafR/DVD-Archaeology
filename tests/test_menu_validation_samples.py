from __future__ import annotations

from pathlib import Path

import pytest

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.menu_validation import MenuValidationModel
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.menu_validation import run as menu_validation_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.util.io import read_json
from tests.sample_paths import SAMPLE_PATHS


@pytest.mark.parametrize("spec", SAMPLE_PATHS[DiscFormat.DVD])
def test_menu_validation_on_dvd_samples(tmp_path: Path, spec) -> None:
    if not spec.path.exists():
        pytest.skip(f"Sample path missing: {spec.path}")
    ingest_run(spec.path, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path, allow_dvd_ifo_fallback=True)
    menu_map_run(tmp_path / "nav.json", tmp_path)
    menu_validation_run(tmp_path / "nav.json", tmp_path / "menu_map.json", tmp_path)

    validation = read_json(tmp_path / "menu_validation.json", MenuValidationModel)
    assert validation.ok is True
    assert validation.menu_entry_count > 0
    assert validation.menu_counts
    assert validation.target_kind_counts