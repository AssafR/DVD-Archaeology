from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from dvdmenu_extract.models.menu import MenuImagesModel
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_images import run as menu_images_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.stages.ocr import run as ocr_run
from dvdmenu_extract.util.io import read_json
from dvdmenu_extract.util.paths import sanitize_filename
from dvdmenu_extract.util.video_ts import build_video_ts_report


EXTERNAL_SAMPLE = Path(r"Q:\DVDs\UglyBetty_s01b")
REFERENCE_DIR = EXTERNAL_SAMPLE / "Reference"
MIN_IMAGE_SSIM = 0.95


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _extract_ssim(text: str) -> float | None:
    for line in reversed(text.splitlines()):
        if "All:" in line:
            parts = line.strip().split()
            for part in parts:
                if part.startswith("All:"):
                    return float(part.split(":", maxsplit=1)[1])
    return None


def _image_ssim(left: Path, right: Path) -> float:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(left),
            "-i",
            str(right),
            "-filter_complex",
            "ssim=stats_file=-",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "ffmpeg ssim failed for "
            f"{left} vs {right}: {result.stderr.decode(errors='ignore')}"
        )
    stderr = result.stderr.decode(errors="ignore")
    stdout = result.stdout.decode(errors="ignore")
    ssim = _extract_ssim(stderr) or _extract_ssim(stdout)
    if ssim is not None:
        return ssim
    raise AssertionError(
        f"Unable to parse ssim for {left} vs {right}: {stderr}"
    )


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


@pytest.mark.skipif(
    not EXTERNAL_SAMPLE.exists(),
    reason="External sample not available on this machine",
)
@pytest.mark.skipif(
    not REFERENCE_DIR.exists(),
    reason="Reference images not available on this machine",
)
@pytest.mark.skipif(
    not _has_ffmpeg(),
    reason="ffmpeg not available on this machine",
)
def test_external_uglybetty_menu_images_reference_ssim(tmp_path: Path) -> None:
    ingest_run(EXTERNAL_SAMPLE, tmp_path)
    nav_parse_run(tmp_path / "ingest.json", tmp_path, allow_dvd_ifo_fallback=True)
    menu_map_run(tmp_path / "nav.json", tmp_path)
    menu_images_run(
        tmp_path / "menu_map.json",
        tmp_path,
        video_ts_path=EXTERNAL_SAMPLE / "VIDEO_TS",
        use_real_ffmpeg=True,
    )

    menu_images = read_json(tmp_path / "menu_images.json", MenuImagesModel)
    images_by_id = {entry.entry_id: Path(entry.image_path) for entry in menu_images.images}
    reference_files = sorted(REFERENCE_DIR.glob("*.png"))
    assert reference_files, "No reference images found"

    for reference_path in reference_files:
        entry_id = reference_path.stem
        assert entry_id in images_by_id, f"Missing menu image for {entry_id}"
        generated_path = images_by_id[entry_id]
        assert generated_path.is_file(), f"Missing generated image for {entry_id}"
        ssim = _image_ssim(generated_path, reference_path)
        assert ssim >= MIN_IMAGE_SSIM, (
            f"SSIM {ssim:.5f} below threshold for {entry_id}"
        )
