from __future__ import annotations

"""Stage D: menu_images.

Produces per-entry image crops used for OCR. For non-DVD formats, this stage
generates placeholders when no fixture images are available.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from dvdmenu_extract.models.menu import MenuImagesModel, MenuImageEntry, MenuMapModel, RectModel
from dvdmenu_extract.util.assertx import ValidationError, assert_in_out_dir
from dvdmenu_extract.util.fixtures import menu_buttons_dir
from dvdmenu_extract.util.io import read_json, write_json
import base64


def _extract_frame(vob_path: Path, output_png: Path) -> None:
    """Extracts the first frame from a VOB file using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(vob_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_png)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise ValidationError(f"ffmpeg failed to extract frame from {vob_path}: {e.stderr.decode()}")


def _probe_image_size(input_png: Path) -> Tuple[int, int]:
    """Returns (width, height) using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(input_png),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise ValidationError(
            f"ffprobe failed to read image size for {input_png}: {e.stderr}"
        )
    output = result.stdout.strip()
    if "x" not in output:
        raise ValidationError(f"ffprobe returned invalid size for {input_png}: {output}")
    width_str, height_str = output.split("x", 1)
    return int(width_str), int(height_str)


def _crop_image(input_png: Path, output_png: Path, rect: RectModel) -> None:
    """Crops an image using ffmpeg."""
    # ffmpeg crop filter: crop=w:h:x:y
    filter_str = f"crop={rect.w}:{rect.h}:{rect.x}:{rect.y}"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_png),
        "-vf", filter_str,
        str(output_png)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise ValidationError(
            f"ffmpeg failed to crop image {input_png}: {e.stderr.decode()}"
        )


def _normalize_rect_to_image(rect: RectModel, size: Tuple[int, int]) -> RectModel:
    """Normalize 0..1023 grid rects to actual image size."""
    width, height = size
    if rect.x + rect.w <= width and rect.y + rect.h <= height:
        return rect
    max_x = rect.x + rect.w
    max_y = rect.y + rect.h
    if max_x <= 1024 and max_y <= 1024:
        scale_x = width / 1024
        scale_y = height / 1024
        return RectModel(
            x=round(rect.x * scale_x),
            y=round(rect.y * scale_y),
            w=round(rect.w * scale_x),
            h=round(rect.h * scale_y),
        )
    return rect


def _menu_base_id(menu_id: str | None) -> str | None:
    if not menu_id:
        return None
    if "_pgc" in menu_id:
        return menu_id.split("_pgc", 1)[0]
    return menu_id


def run(
    menu_map_path: Path,
    out_dir: Path,
    video_ts_path: Optional[Path] = None,
    use_real_ffmpeg: bool = False,
    reference_dir: Optional[Path] = None,
) -> MenuImagesModel:
    menu_map = read_json(menu_map_path, MenuMapModel)
    output_dir = out_dir / "menu_images"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Cache for extracted menu backgrounds to avoid redundant ffmpeg calls
    # menu_id -> background_png_path
    menu_backgrounds: dict[str, Path] = {}
    menu_sizes: dict[str, Tuple[int, int]] = {}

    entries: list[MenuImageEntry] = []
    placeholder_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+7VZkAAAAASUVORK5CYII="
    )
    if use_real_ffmpeg and video_ts_path is None and reference_dir is None:
        raise ValidationError("menu_images requires VIDEO_TS path or reference images")

    for entry in menu_map.entries:
        dst = output_dir / f"{entry.entry_id}.png"
        assert_in_out_dir(dst, out_dir)

        # 1. Reference images for explicit test runs (optional)
        if use_real_ffmpeg and reference_dir is not None:
            src_reference = reference_dir / f"{entry.entry_id}.png"
            if src_reference.is_file():
                shutil.copyfile(src_reference, dst)
            else:
                src_reference = None
        else:
            src_reference = None

        if src_reference is None and not use_real_ffmpeg:
            # 2. Fixtures for tests/stubs
            src_fixture = menu_buttons_dir() / f"{entry.entry_id}.png"
            if src_fixture.is_file():
                shutil.copyfile(src_fixture, dst)
            else:
                dst.write_bytes(placeholder_png)
        elif src_reference is None and use_real_ffmpeg and video_ts_path:
            # 3. Try real extraction from DVD VOBs
            # Heuristic: VMGM menus are in VIDEO_TS.VOB, VTSM menus are in VTS_XX_0.VOB
            menu_base = _menu_base_id(entry.menu_id)
            vob_path = None
            if menu_base and menu_base.upper() == "VMGM":
                vob_path = video_ts_path / "VIDEO_TS.VOB"
            elif menu_base and menu_base.upper().startswith("VTSM"):
                # Expecting something like VTSM_01
                parts = menu_base.split("_")
                if len(parts) >= 2 and parts[1].isdigit():
                    vob_path = video_ts_path / f"VTS_{parts[1]}_0.VOB"
            if vob_path is None:
                fallback = video_ts_path / "VIDEO_TS.VOB"
                if fallback.is_file():
                    vob_path = fallback
                else:
                    candidates = sorted(video_ts_path.glob("VTS_*_0.VOB"))
                    if candidates:
                        vob_path = candidates[0]

            if vob_path and vob_path.is_file():
                bg_cache_path = output_dir / f"bg_{entry.menu_id}.png"
                if entry.menu_id not in menu_backgrounds:
                    if not bg_cache_path.is_file():
                        _extract_frame(vob_path, bg_cache_path)
                    menu_backgrounds[entry.menu_id] = bg_cache_path
                    menu_sizes[entry.menu_id] = _probe_image_size(bg_cache_path)

                bg_path = menu_backgrounds[entry.menu_id]
                bg_size = menu_sizes[entry.menu_id]
                crop_rect = entry.selection_rect or entry.highlight_rect or entry.rect
                if not crop_rect:
                    raise ValidationError(
                        f"Missing button rect for entry_id {entry.entry_id}"
                    )
                crop_rect = _normalize_rect_to_image(crop_rect, bg_size)
                if (
                    crop_rect.x + crop_rect.w > bg_size[0]
                    or crop_rect.y + crop_rect.h > bg_size[1]
                ):
                    raise ValidationError(
                        f"Invalid crop rect for entry_id {entry.entry_id}: "
                        f"{crop_rect} exceeds {bg_size[0]}x{bg_size[1]}"
                    )
                _crop_image(bg_path, dst, crop_rect)
            else:
                raise ValidationError(
                    f"Missing menu VOB for entry_id {entry.entry_id}"
                )
        elif src_reference is None and use_real_ffmpeg:
            raise ValidationError(
                f"Missing reference image for entry_id {entry.entry_id}"
            )

        entries.append(
            MenuImageEntry(
                entry_id=entry.entry_id,
                image_path=str(dst),
                menu_id=entry.menu_id,
                selection_rect=entry.selection_rect,
                highlight_rect=entry.highlight_rect,
                target=entry.target,
            )
        )

    model = MenuImagesModel(images=entries)
    write_json(out_dir / "menu_images.json", model)
    return model
