from __future__ import annotations

from pathlib import Path

import pytest

from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_images import run as menu_images_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.stages.ocr import run as ocr_run
from dvdmenu_extract.util.paths import sanitize_filename
from dvdmenu_extract.util.video_ts import build_video_ts_report


EXTERNAL_SAMPLE = Path(r"Q:\DVDs\UglyBetty_s01b")


@pytest.mark.skipif(
    not EXTERNAL_SAMPLE.exists(),
    reason="External sample not available on this machine",
)
def test_external_uglybetty_video_ts_report() -> None:
    video_ts = EXTERNAL_SAMPLE / "VIDEO_TS"
    assert video_ts.is_dir()

    report = build_video_ts_report(video_ts)
    assert report.file_count >= 6
    assert report.total_bytes > 0
    assert report.vts_title_count >= 1
    assert report.vob_total_bytes > 0

    vob_segments = sorted(video_ts.glob("VTS_01_*.VOB"))
    assert len(vob_segments) >= 3
    assert all(path.stat().st_size > 0 for path in vob_segments)


@pytest.mark.skipif(
    not EXTERNAL_SAMPLE.exists(),
    reason="External sample not available on this machine",
)
def test_external_uglybetty_ocr_reference(tmp_path: Path) -> None:
    reference_path = Path(__file__).resolve().parent / "UglyBettyText"
    reference_lines = [
        line.strip()
        for line in reference_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]

    ingest_run(EXTERNAL_SAMPLE, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path, allow_dvd_ifo_fallback=True)
    menu_map_run(tmp_path / "nav.json", tmp_path)
    menu_images_run(tmp_path / "menu_map.json", tmp_path)

    ocr = ocr_run(
        tmp_path / "menu_images.json",
        tmp_path,
        "eng+heb",
        False,
        reference_path,
    )

    assert len(ocr.results) == len(reference_lines)
    for entry, raw_text in zip(ocr.results, reference_lines, strict=False):
        assert entry.raw_text == raw_text
        assert entry.cleaned_label == sanitize_filename(raw_text)
        assert entry.source == "background"
        assert entry.background_attempted is True
        assert entry.spu_text_nonempty is False
