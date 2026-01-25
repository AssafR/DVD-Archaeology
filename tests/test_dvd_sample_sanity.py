from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.pipeline import PipelineOptions, run_pipeline
from dvdmenu_extract.stages.ingest import run as ingest_run


def _dvd_sample_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / name


def _assert_video_ts_layout(video_ts: Path) -> None:
    required = ["VIDEO_TS.BUP", "VIDEO_TS.IFO", "VIDEO_TS.VOB"]
    missing = [name for name in required if not (video_ts / name).is_file()]
    assert not missing, f"Missing VIDEO_TS files: {missing}"
    zero_size = [name for name in required if (video_ts / name).stat().st_size <= 0]
    assert not zero_size, f"Zero-size VIDEO_TS files: {zero_size}"

    vts_ifo = sorted(video_ts.glob("VTS_*_0.IFO"))
    vts_vob = sorted(video_ts.glob("VTS_*_1.VOB"))
    assert vts_ifo, "Expected at least one VTS_*_0.IFO file"
    assert vts_vob, "Expected at least one VTS_*_1.VOB file"

    for path in vts_ifo + vts_vob:
        assert path.stat().st_size > 0, f"Zero-size VTS file: {path.name}"


def test_dvd_sample_ingest(tmp_path: Path) -> None:
    sample_path = _dvd_sample_path("DVD_Sample_01")
    assert sample_path.is_dir()
    video_ts = sample_path / "VIDEO_TS"
    assert video_ts.is_dir()
    _assert_video_ts_layout(video_ts)

    ingest = ingest_run(sample_path, tmp_path)
    assert ingest.has_video_ts is True
    assert ingest.disc_type_guess == "DVD"
    assert ingest.video_ts_report is not None
    assert ingest.video_ts_report.file_count >= 12
    assert ingest.video_ts_report.vts_title_count >= 1
    assert ingest.video_ts_report.total_bytes > 0
    assert (tmp_path / "video_ts_report.json").is_file()
    assert ingest.disc_report is not None
    assert ingest.disc_report.disc_format == "DVD"
    assert (tmp_path / "disc_report.json").is_file()


def test_dvd_sample_pipeline_stub(tmp_path: Path) -> None:
    sample_path = _dvd_sample_path("DVD_Sample_01")
    assert sample_path.is_dir()
    _assert_video_ts_layout(sample_path / "VIDEO_TS")

    options = PipelineOptions(
        ocr_lang="eng+heb",
        use_real_ocr=False,
        use_real_ffmpeg=False,
        repair="off",
        force=True,
        json_out_root=False,
        json_root_dir=False,
        use_real_timing=False,
        allow_dvd_ifo_fallback=True,
    )
    run_pipeline(input_path=sample_path, out_dir=tmp_path, options=options)

    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "menu_images").is_dir()
    assert (tmp_path / "episodes").is_dir()


def test_dvd_sample_02_ingest(tmp_path: Path) -> None:
    sample_path = _dvd_sample_path("DVD_Sample_02")
    assert sample_path.is_dir()
    video_ts = sample_path / "VIDEO_TS"
    assert video_ts.is_dir()
    _assert_video_ts_layout(video_ts)

    ingest = ingest_run(sample_path, tmp_path)
    assert ingest.has_video_ts is True
    assert ingest.disc_type_guess == "DVD"
    assert ingest.video_ts_report is not None
    assert ingest.video_ts_report.file_count >= 6
    assert ingest.video_ts_report.vts_title_count >= 1
    assert ingest.video_ts_report.total_bytes > 0
    assert (tmp_path / "video_ts_report.json").is_file()
    assert ingest.disc_report is not None
    assert ingest.disc_report.disc_format == "DVD"
    assert (tmp_path / "disc_report.json").is_file()