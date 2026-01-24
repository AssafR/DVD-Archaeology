from __future__ import annotations

from pathlib import Path

import pytest

from dvdmenu_extract.pipeline import PipelineOptions, run_pipeline
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.util.io import read_json


EXTERNAL_VCD = Path(r"S:\TV Shows\MadTV\0368 - Mad TV collection 7 - CD")


@pytest.mark.skipif(
    not EXTERNAL_VCD.exists(),
    reason="External VCD sample not available",
)
def test_external_vcd_layout_and_ingest(tmp_path: Path) -> None:
    mpegav_dir = EXTERNAL_VCD / "MPEGAV"
    assert mpegav_dir.is_dir()
    mpeg_files = sorted(mpegav_dir.glob("AVSEQ*.DAT"))
    assert mpeg_files, "Expected MPEGAV/AVSEQ*.DAT files for VCD sample"
    assert all(path.stat().st_size > 0 for path in mpeg_files)

    ingest = ingest_run(EXTERNAL_VCD, tmp_path)
    assert ingest.has_video_ts is False
    assert ingest.disc_type_guess == DiscFormat.VCD
    assert ingest.disc_report is not None
    assert ingest.disc_report.disc_format == DiscFormat.VCD


@pytest.mark.skipif(
    not EXTERNAL_VCD.exists(),
    reason="External VCD sample not available",
)
def test_external_vcd_pipeline_stub(tmp_path: Path) -> None:
    options = PipelineOptions(
        ocr_lang="eng+heb",
        use_real_ocr=False,
        use_real_ffmpeg=False,
        repair="off",
        force=True,
        json_out_root=False,
        json_root_dir=False,
    )
    run_pipeline(input_path=EXTERNAL_VCD, out_dir=tmp_path, options=options)

    nav = read_json(tmp_path / "nav.json", NavigationModel)
    ingest = read_json(tmp_path / "ingest.json", IngestModel)
    assert nav.disc_format == DiscFormat.VCD
    assert ingest.disc_report is not None
    assert ingest.disc_report.mpegav_file_count == len(nav.vcd.tracks)
