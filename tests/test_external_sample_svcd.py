from __future__ import annotations

from pathlib import Path

import pytest

from dvdmenu_extract.stages.ingest import run as ingest_run


EXTERNAL_SVCD = Path(r"Q:\Old_Discs\0008 - SNL Steve Buscemi 1997 - CD")


@pytest.mark.skipif(
    not EXTERNAL_SVCD.exists(),
    reason="External SVCD sample not available on this machine",
)
def test_external_svcd_layout_and_ingest(tmp_path: Path) -> None:
    mpeg2_dir = EXTERNAL_SVCD / "MPEG2"
    assert mpeg2_dir.is_dir()
    mpeg_files = sorted(mpeg2_dir.glob("*.MPG"))
    assert mpeg_files, "Expected MPEG2/*.MPG files for SVCD sample"
    assert all(path.stat().st_size > 0 for path in mpeg_files)

    ingest = ingest_run(EXTERNAL_SVCD, tmp_path)
    assert ingest.has_video_ts is False
    assert ingest.disc_type_guess == "SVCD"
    assert ingest.disc_report is not None
    assert ingest.disc_report.disc_format == "SVCD"
    assert ingest.disc_report.mpeg2_file_count is not None
    assert ingest.disc_report.mpeg2_file_count >= 1


@pytest.mark.skipif(
    not EXTERNAL_SVCD.exists(),
    reason="External SVCD sample not available on this machine",
)
def test_external_svcd_pipeline_stub(tmp_path: Path) -> None:
    from dvdmenu_extract.pipeline import PipelineOptions, run_pipeline
    from dvdmenu_extract.util.io import read_json
    from dvdmenu_extract.models.nav import NavigationModel
    from dvdmenu_extract.models.menu import MenuMapModel
    from dvdmenu_extract.models.ingest import IngestModel
    from dvdmenu_extract.models.segments import SegmentsModel

    options = PipelineOptions(
        ocr_lang="eng+heb",
        use_real_ocr=False,
        use_real_ffmpeg=False,
        repair="off",
        force=True,
    )
    run_pipeline(input_path=EXTERNAL_SVCD, out_dir=tmp_path, options=options)
    nav = read_json(tmp_path / "nav.json", NavigationModel)
    assert nav.disc_format == "SVCD"
    assert (tmp_path / "manifest.json").is_file()

    ingest = read_json(tmp_path / "ingest.json", IngestModel)
    menu_map = read_json(tmp_path / "menu_map.json", MenuMapModel)
    segments = read_json(tmp_path / "segments.json", SegmentsModel)
    assert ingest.disc_report is not None
    assert ingest.disc_report.mpeg2_file_count == len(menu_map.entries)
    assert len(segments.segments) == len(menu_map.entries)