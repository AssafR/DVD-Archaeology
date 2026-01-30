from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from dvdmenu_extract.models.menu import MenuImagesModel, MenuMapModel, RectModel
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
MIN_BUTTON_SSIM = 0.7
MIN_BUTTON_OVERLAP = 0.5


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
            "[1:v][0:v]scale2ref=flags=bicubic[ref][gen];[gen][ref]ssim=stats_file=-",
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


def _image_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"ffprobe failed for {path}: {result.stderr}"
        )
    output = result.stdout.strip()
    if "x" not in output:
        raise AssertionError(f"ffprobe returned invalid size for {path}: {output}")
    width, height = output.split("x", 1)
    return int(width), int(height)


def _normalize_text(text: str) -> str:
    return "".join(text.strip().split())


def _parse_reference_text(reference_path: Path) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for line in reference_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(".", maxsplit=1)
        if len(parts) != 2:
            continue
        try:
            key = int(parts[0].strip())
        except ValueError:
            continue
        if key not in mapping:
            mapping[key] = _normalize_text(line)
    return mapping


def _parse_button_coordinates(path: Path) -> dict[int, RectModel]:
    mapping: dict[int, RectModel] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        try:
            button_no = int(parts[0])
        except ValueError:
            continue
        coords = parts[1]
        if "-" not in coords:
            continue
        left, right = coords.split("-", maxsplit=1)
        x1, y1 = [int(v.strip()) for v in left.split(",")]
        x2, y2 = [int(v.strip()) for v in right.split(",")]
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        mapping[button_no] = RectModel(x=x1, y=y1, w=x2 - x1, h=y2 - y1)
    return mapping


def _has_tesseract() -> bool:
    try:
        import pytesseract
    except Exception:
        return False
    try:
        _ = pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def _overlap_ratio(a: RectModel, b: RectModel) -> float:
    left = max(a.x, b.x)
    top = max(a.y, b.y)
    right = min(a.x + a.w, b.x + b.w)
    bottom = min(a.y + a.h, b.y + b.h)
    if right <= left or bottom <= top:
        return 0.0
    inter = (right - left) * (bottom - top)
    min_area = min(a.w * a.h, b.w * b.h)
    return inter / min_area if min_area else 0.0


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

    failures: list[str] = []
    for reference_path in reference_files:
        entry_id = reference_path.stem
        assert entry_id in images_by_id, f"Missing menu image for {entry_id}"
        generated_path = images_by_id[entry_id]
        assert generated_path.is_file(), f"Missing generated image for {entry_id}"
        ssim = _image_ssim(generated_path, reference_path)
        if ssim < MIN_IMAGE_SSIM:
            gen_size = _image_size(generated_path)
            ref_size = _image_size(reference_path)
            failures.append(
                f"{entry_id}: ssim={ssim:.5f} "
                f"gen={gen_size[0]}x{gen_size[1]} "
                f"ref={ref_size[0]}x{ref_size[1]}"
            )
    if failures:
        pytest.fail(
            "Menu image SSIM below threshold:\n" + "\n".join(failures)
        )


@pytest.mark.skipif(
    not EXTERNAL_SAMPLE.exists(),
    reason="External sample not available on this machine",
)
@pytest.mark.skipif(
    not _has_ffmpeg(),
    reason="ffmpeg not available on this machine",
)
@pytest.mark.skipif(
    not _has_tesseract(),
    reason="tesseract not available on this machine",
)
def test_external_uglybetty_button_coords_overlap_and_ocr(tmp_path: Path) -> None:
    import pytesseract
    from PIL import Image

    coords_path = Path(__file__).resolve().parent / "UglyBettyButtonCoordinates"
    reference_path = Path(__file__).resolve().parent / "UglyBettyText"
    reference_text = _parse_reference_text(reference_path)
    coords = _parse_button_coordinates(coords_path)
    assert coords, "No button coordinates found"

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
    menu_map = read_json(tmp_path / "menu_map.json", MenuMapModel)
    map_by_id = {entry.entry_id: entry for entry in menu_map.entries}

    failures: list[str] = []
    for button_no, rect in coords.items():
        entry_id = f"btn{button_no}"
        expected = reference_text.get(button_no)
        if expected is None:
            failures.append(f"{entry_id}: missing expected OCR text")
            continue
        entry = map_by_id.get(entry_id)
        if entry is None:
            failures.append(f"{entry_id}: missing menu_map entry")
            continue
        crop_source = None
        menu_id = entry.menu_id or "unknown_menu"
        bg_path = tmp_path / "menu_images" / f"bg_{menu_id}.png"
        if bg_path.is_file():
            crop_source = bg_path
        if crop_source is None:
            failures.append(f"{entry_id}: missing background image for {menu_id}")
            continue

        base_image = Image.open(crop_source).convert("L")
        crop = base_image.crop(
            (rect.x, rect.y, rect.x + rect.w + 1, rect.y + rect.h + 1)
        )
        from PIL import ImageOps
        ocr_image = ImageOps.autocontrast(crop)
        ocr_image = ocr_image.point(lambda p: 255 if p > 140 else 0)
        config = "--psm 7 -c tessedit_char_whitelist=0123456789.aA"
        ocr_text = _normalize_text(
            pytesseract.image_to_string(ocr_image, lang="eng+heb", config=config)
        )
        if expected not in ocr_text:
            failures.append(
                f"{entry_id}: OCR mismatch expected='{expected}' got='{ocr_text}'"
            )

        source_rect = entry.selection_rect or entry.highlight_rect or entry.rect
        best_match_id = entry_id
        best_overlap = 0.0
        if source_rect is not None:
            best_overlap = _overlap_ratio(rect, source_rect)
        if best_overlap < MIN_BUTTON_OVERLAP:
            # If ordering differs, match by best overlap.
            for other in menu_map.entries:
                other_rect = other.selection_rect or other.highlight_rect or other.rect
                if other_rect is None:
                    continue
                overlap = _overlap_ratio(rect, other_rect)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match_id = other.entry_id
            if best_overlap < MIN_BUTTON_OVERLAP:
                failures.append(
                    f"{entry_id}: overlap below threshold ({best_overlap:.2f})"
                )

        generated = images_by_id.get(best_match_id)
        if generated is None or not generated.is_file():
            failures.append(f"{entry_id}: missing generated image for {best_match_id}")
            continue
        crop_path = tmp_path / f"{entry_id}_coord.png"
        crop.save(crop_path)
        ssim = _image_ssim(generated, crop_path)
        if ssim < MIN_BUTTON_SSIM:
            failures.append(f"{entry_id}: SSIM below threshold ({ssim:.3f})")

    if failures:
        pytest.fail(
            "UglyBetty button coordinate checks failed:\n" + "\n".join(failures)
        )
