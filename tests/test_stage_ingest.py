from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.stages.ingest import run as ingest_run
from tests.helpers import fixtures_dir


def test_stage_ingest(tmp_path: Path) -> None:
    input_path = fixtures_dir() / "disc_minimal"
    result = ingest_run(input_path, tmp_path)

    assert (tmp_path / "ingest.json").is_file()
    assert isinstance(result, IngestModel)
    assert result.disc_type_guess == "DVD"
    assert result.has_video_ts is True
