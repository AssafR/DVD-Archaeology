from __future__ import annotations

from pathlib import Path

import pytest

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
