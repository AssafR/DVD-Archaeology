from __future__ import annotations

"""Stage D: menu_images.

Produces per-entry image crops used for OCR. For non-DVD formats, this stage
generates placeholders when no fixture images are available.
"""

import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageChops, ImageStat
import pytesseract

from dvdmenu_extract.models.menu import (
    MenuImagesModel,
    MenuImageEntry,
    MenuEntryModel,
    MenuMapModel,
    RectModel,
)
from dvdmenu_extract.util.assertx import ValidationError, assert_in_out_dir
from dvdmenu_extract.util.fixtures import menu_buttons_dir
from dvdmenu_extract.util.io import read_json, write_json
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.util.btn_it_analyzer import (
    analyze_btn_it_structure,
    assign_buttons_to_pages,
    MenuPageAnalysis,
)
import base64


def _rect_area(rect: RectModel) -> int:
    return max(0, rect.w) * max(0, rect.h)


def _rect_intersection_area(a: RectModel, b: RectModel) -> int:
    left = max(a.x, b.x)
    top = max(a.y, b.y)
    right = min(a.x + a.w, b.x + b.w)
    bottom = min(a.y + a.h, b.y + b.h)
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def _overlap_ratio(a: RectModel, b: RectModel) -> float:
    inter = _rect_intersection_area(a, b)
    if inter == 0:
        return 0.0
    min_area = min(_rect_area(a), _rect_area(b))
    if min_area == 0:
        return 0.0
    return inter / min_area


def _rects_overlap_too_much(
    rects: list[tuple[str, RectModel]],
    max_overlap_ratio: float,
) -> bool:
    for idx, (_, rect) in enumerate(rects):
        for _, other_rect in rects[idx + 1 :]:
            if _overlap_ratio(rect, other_rect) > max_overlap_ratio:
                return True
    return False


def _assert_rects_have_low_overlap(
    menus: dict[str, list[tuple[str, RectModel]]],
    max_overlap_ratio: float = 0.2,
) -> None:
    for menu_id, menu_entries in menus.items():
        for idx, (entry_id, rect) in enumerate(menu_entries):
            for other_id, other_rect in menu_entries[idx + 1 :]:
                ratio = _overlap_ratio(rect, other_rect)
                if ratio > max_overlap_ratio:
                    raise ValidationError(
                        "menu_images: overlapping button rects detected "
                        f"menu_id={menu_id} {entry_id} vs {other_id} "
                        f"overlap_ratio={ratio:.2f} (max {max_overlap_ratio:.2f})"
                    )


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


def _extract_frame_at(vob_path: Path, output_png: Path, timestamp: float) -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(vob_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_png),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise ValidationError(
            f"ffmpeg failed to extract frame from {vob_path}: {e.stderr}"
        )


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


def _probe_video_duration(vob_path: Path) -> float | None:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(vob_path),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _connected_components(mask: Image.Image) -> list[tuple[int, int, int, int]]:
    width, height = mask.size
    pixels = mask.load()
    visited = [[False for _ in range(width)] for _ in range(height)]
    rects: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if visited[y][x] or pixels[x, y] == 0:
                continue
            stack = [(x, y)]
            visited[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            while stack:
                cx, cy = stack.pop()
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for nx, ny in (
                    (cx - 1, cy),
                    (cx + 1, cy),
                    (cx, cy - 1),
                    (cx, cy + 1),
                ):
                    if 0 <= nx < width and 0 <= ny < height:
                        if not visited[ny][nx] and pixels[nx, ny] != 0:
                            visited[ny][nx] = True
                            stack.append((nx, ny))
            rects.append((min_x, min_y, max_x, max_y))
    return rects


def _detect_menu_rects_from_video(
    vob_path: Path,
    output_dir: Path,
    expected: int,
    frame_count: int = 6,
) -> tuple[list[tuple[int, int, int, int]], bool]:
    duration = _probe_video_duration(vob_path)
    if duration is None or duration <= 0:
        return [], True
    step = max(0.5, duration / max(1, frame_count))
    timestamps = [min(duration - 0.01, i * step) for i in range(frame_count)]
    frame_paths: list[Path] = []
    temp_dir = output_dir / "_menu_detect"
    temp_dir.mkdir(parents=True, exist_ok=True)
    for idx, ts in enumerate(timestamps, start=1):
        frame_path = temp_dir / f"{vob_path.stem}_frame_{idx:02d}.png"
        _extract_frame_at(vob_path, frame_path, ts)
        frame_paths.append(frame_path)

    aggregate = None
    max_pair_diff = 0.0
    for idx in range(1, len(frame_paths)):
        prev = Image.open(frame_paths[idx - 1]).convert("RGB")
        curr = Image.open(frame_paths[idx]).convert("RGB")
        diff = ImageChops.difference(prev, curr).convert("L")
        stat = ImageStat.Stat(diff)
        max_pair_diff = max(max_pair_diff, stat.mean[0])
        if aggregate is None:
            aggregate = diff
        else:
            aggregate = ImageChops.lighter(aggregate, diff)

    if aggregate is None:
        return [], True
    if max_pair_diff < 5.0:
        return [], True
    # Threshold the aggregate diff to isolate highlight regions.
    mask = aggregate.point(lambda p: 255 if p > 20 else 0)
    rects = _connected_components(mask)
    if not rects:
        return [], False

    rects = sorted(
        rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), reverse=True
    )
    rects = rects[:expected]

    # Merge highly-overlapping boxes to avoid full-frame masks.
    def _merge_rects(input_rects: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
        merged: list[tuple[int, int, int, int]] = []
        for rect in input_rects:
            x1, y1, x2, y2 = rect
            replaced = False
            for idx, (mx1, my1, mx2, my2) in enumerate(merged):
                ix1 = max(x1, mx1)
                iy1 = max(y1, my1)
                ix2 = min(x2, mx2)
                iy2 = min(y2, my2)
                if ix2 >= ix1 and iy2 >= iy1:
                    area = (x2 - x1 + 1) * (y2 - y1 + 1)
                    marea = (mx2 - mx1 + 1) * (my2 - my1 + 1)
                    inter = (ix2 - ix1 + 1) * (iy2 - iy1 + 1)
                    if inter / min(area, marea) > 0.9:
                        merged[idx] = (
                            min(x1, mx1),
                            min(y1, my1),
                            max(x2, mx2),
                            max(y2, my2),
                        )
                        replaced = True
                        break
            if not replaced:
                merged.append(rect)
        return merged

    def _filter_rects(
        input_rects: list[tuple[int, int, int, int]]
    ) -> list[tuple[int, int, int, int]]:
        width, height = aggregate.size
        min_area = width * height * 0.005
        max_area = width * height * 0.5
        filtered = []
        for rect in input_rects:
            area = (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)
            if min_area <= area <= max_area:
                filtered.append(rect)
        # Dedupe highly-overlapping rects.
        deduped: list[tuple[int, int, int, int]] = []
        for rect in filtered:
            x1, y1, x2, y2 = rect
            area = (x2 - x1 + 1) * (y2 - y1 + 1)
            keep = True
            for ox1, oy1, ox2, oy2 in deduped:
                ix1 = max(x1, ox1)
                iy1 = max(y1, oy1)
                ix2 = min(x2, ox2)
                iy2 = min(y2, oy2)
                if ix2 >= ix1 and iy2 >= iy1:
                    inter = (ix2 - ix1 + 1) * (iy2 - iy1 + 1)
                    oarea = (ox2 - ox1 + 1) * (oy2 - oy1 + 1)
                    if inter / min(area, oarea) > 0.9:
                        keep = False
                        break
            if keep:
                deduped.append(rect)
        return deduped

    rects = _merge_rects(rects)
    rects = _filter_rects(rects)
    rects = sorted(rects, key=lambda r: (r[1], r[0]))
    return rects, False


def _rects_are_similar(
    rect1: tuple[int, int, int, int],
    rect2: tuple[int, int, int, int],
    position_threshold: int = 50,
    size_threshold: float = 0.3,
) -> bool:
    """Check if two rectangles represent the same button (similar position and size)."""
    x1_1, y1_1, x2_1, y2_1 = rect1
    x1_2, y1_2, x2_2, y2_2 = rect2
    
    # Check center position similarity
    cx1 = (x1_1 + x2_1) / 2
    cy1 = (y1_1 + y2_1) / 2
    cx2 = (x1_2 + x2_2) / 2
    cy2 = (y1_2 + y2_2) / 2
    
    center_dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
    if center_dist > position_threshold:
        return False
    
    # Check size similarity
    w1 = x2_1 - x1_1 + 1
    h1 = y2_1 - y1_1 + 1
    w2 = x2_2 - x1_2 + 1
    h2 = y2_2 - y1_2 + 1
    
    area1 = w1 * h1
    area2 = w2 * h2
    
    if area1 == 0 or area2 == 0:
        return False
    
    area_ratio = min(area1, area2) / max(area1, area2)
    if area_ratio < (1.0 - size_threshold):
        return False
    
    return True


def _detect_rects_from_image_file(
    frame_path: Path, expected: int
) -> list[tuple[int, int, int, int]]:
    """
    Detect button rectangles from a single frame image file.
    
    Uses the same block-based dark region detection as _detect_menu_rects_from_static_frame.
    """
    from PIL import Image
    import logging
    logger = logging.getLogger(__name__)
    
    image = Image.open(frame_path).convert("L")
    width, height = image.size
    pixels = image.load()
    
    # Block-based dark region detection (same as _detect_menu_rects_from_static_frame)
    dark_block_size = 8
    dark_blocks = []
    for by in range(0, height, dark_block_size):
        for bx in range(0, width // 2, dark_block_size):  # Search left half
            values = []
            for y in range(by, min(by + dark_block_size, height)):
                for x in range(bx, min(bx + dark_block_size, width)):
                    values.append(pixels[x, y])
            if not values:
                continue
            mean_val = sum(values) / len(values)
            # Dark threshold for thumbnail content
            if mean_val < 65:
                dark_blocks.append((bx, by, bx + dark_block_size - 1, by + dark_block_size - 1))
    
    if not dark_blocks:
        return []
    
    # Merge adjacent dark blocks iteratively
    merged = []
    used = set()
    for idx, (x1, y1, x2, y2) in enumerate(dark_blocks):
        if idx in used:
            continue
        current = [x1, y1, x2, y2]
        changed = True
        while changed:
            changed = False
            for jdx, (ox1, oy1, ox2, oy2) in enumerate(dark_blocks):
                if jdx in used or jdx == idx:
                    continue
                # Strictly adjacent (within 1 block size, no gaps)
                if (abs(ox1 - current[2]) <= dark_block_size and 
                    not (oy2 < current[1] or oy1 > current[3])):
                    # Horizontally adjacent
                    current = [
                        min(current[0], ox1),
                        min(current[1], oy1),
                        max(current[2], ox2),
                        max(current[3], oy2),
                    ]
                    used.add(jdx)
                    changed = True
                elif (abs(oy1 - current[3]) <= dark_block_size and 
                      not (ox2 < current[0] or ox1 > current[2])):
                    # Vertically adjacent - merge with strict height limit
                    new_height = max(current[3], oy2) - min(current[1], oy1) + 1
                    if new_height <= 120:  # Max single thumbnail height
                        current = [
                            min(current[0], ox1),
                            min(current[1], oy1),
                            max(current[2], ox2),
                            max(current[3], oy2),
                        ]
                        used.add(jdx)
                        changed = True
        merged.append(tuple(current))
    
    # Filter by thumbnail size and compactness
    thumbnails = []
    merged_sorted = sorted(merged, key=lambda r: (r[2]-r[0]+1) * (r[3]-r[1]+1), reverse=True)
    
    for rect in merged_sorted:
        x1, y1, x2, y2 = rect
        w = x2 - x1 + 1
        h = y2 - y1 + 1
        bbox_area = w * h
        
        # Count actual dark pixels in this bounding box
        dark_pixel_count = 0
        for y in range(y1, min(y2 + 1, height)):
            for x in range(x1, min(x2 + 1, width)):
                if pixels[x, y] < 65:  # Match the detection threshold
                    dark_pixel_count += 1
        
        compactness = dark_pixel_count / bbox_area if bbox_area > 0 else 0
        
        # Thumbnail candidates: reasonable size, decent compactness
        if (50 <= w <= 300 and 50 <= h <= 300 and 
            2500 <= bbox_area <= 90000 and compactness > 0.25):
            thumbnails.append(rect)
    
    if not thumbnails:
        return []
    
    # Filter out edge rects (including bottom edge to avoid navigation UI)
    edge_margin = 20
    bottom_margin = 100  # Larger margin at bottom to avoid navigation UI
    # height variable is already defined from image dimensions above
    filtered_thumbnails = [
        rect for rect in thumbnails
        if (rect[0] > edge_margin and rect[1] > edge_margin and 
            rect[3] < height - bottom_margin)  # Exclude rects near bottom edge
    ]
    
    # Dedupe by vertical position
    def _thumbnail_score(rect):
        w = rect[2] - rect[0] + 1
        h = rect[3] - rect[1] + 1
        aspect = w / h if h > 0 else 0
        aspect_score = 1.0 - abs(aspect - 1.0)
        size_score = 1.0 if 80 <= w <= 140 and 80 <= h <= 200 else 0.5
        return aspect_score + size_score
    
    deduped = []
    for rect in sorted(filtered_thumbnails, key=_thumbnail_score, reverse=True):
        y_center = (rect[1] + rect[3]) / 2
        overlaps = False
        for existing in deduped:
            existing_y_center = (existing[1] + existing[3]) / 2
            if abs(y_center - existing_y_center) < 100:
                overlaps = True
                break
        if not overlaps:
            deduped.append(rect)
    
    # Sort by vertical position
    deduped.sort(key=lambda r: (r[1], r[0]))
    return deduped[:expected] if deduped else []


def _detect_menu_rects_multi_page(
    vob_path: Path,
    output_dir: Path,
    expected: int,
    sample_interval: float = 3.0,
) -> dict[int, tuple[Path, tuple[int, int, int, int]]]:
    """
    Detect button rectangles across multiple menu pages by sampling frames.
    
    Extracts frames at regular intervals throughout the menu duration,
    runs detection on each frame, and maps each button to its best frame.
    
    Args:
        vob_path: Path to menu VOB file
        output_dir: Directory for temporary files
        expected: Expected number of buttons
        sample_interval: Seconds between frame samples (default: 3.0)
    
    Returns:
        dict mapping button_index (0-based) -> (frame_path, rect_tuple)
        where rect_tuple is (x1, y1, x2, y2)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Get menu duration
    duration = _probe_video_duration(vob_path)
    if duration is None or duration <= 0:
        logger.warning(f"Cannot determine duration for {vob_path}, falling back to single frame")
        return {}
    
    # Extract and detect on frames
    temp_dir = output_dir / "_menu_detect_multipage"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    frame_detections: list[tuple[Path, list[tuple[int, int, int, int]]]] = []
    
    # For very short VOBs (menu VOBs often have unreliable timing),
    # extract ALL frames instead of sampling by timestamp
    if duration < 0.5:
        logger.info(f"menu_images: VOB duration very short ({duration:.3f}s), extracting all frames")
        
        # Extract all frames from VOB
        all_frames_pattern = temp_dir / f"{vob_path.stem}_frame_%03d.png"
        import subprocess
        cmd = [
            "ffmpeg", "-i", str(vob_path),
            str(all_frames_pattern),
            "-y"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Find all extracted frames
        extracted_frames = sorted(temp_dir.glob(f"{vob_path.stem}_frame_*.png"))
        logger.info(f"  Extracted {len(extracted_frames)} frames from VOB")
        
        # Run detection on each frame
        for idx, frame_path in enumerate(extracted_frames):
            try:
                rects = _detect_rects_from_image_file(frame_path, expected)
                if rects:
                    logger.info(f"  Frame {idx}: detected {len(rects)} rects: {rects}")
                    frame_detections.append((frame_path, rects))
                else:
                    logger.debug(f"  Frame {idx}: no rects detected")
            except Exception as e:
                logger.warning(f"Failed to detect in frame {idx}: {e}")
                continue
    else:
        # For longer VOBs, sample by timestamp
        max_time = max(0.5, duration - 0.5)
        timestamps = []
        t = 0.1
        while t < max_time:
            timestamps.append(t)
            t += sample_interval
        
        if not timestamps:
            timestamps = [0.1]
        
        logger.info(f"menu_images: multi-page detection: sampling {len(timestamps)} frames from {vob_path.name} "
                    f"(duration={duration:.1f}s, interval={sample_interval}s)")
        
        for idx, ts in enumerate(timestamps):
            frame_path = temp_dir / f"{vob_path.stem}_page_{idx:02d}_t{ts:.1f}s.png"
            try:
                _extract_frame_at(vob_path, frame_path, ts)
                # Run detection on this frame
                rects = _detect_rects_from_image_file(frame_path, expected)
                if rects:
                    logger.info(f"  Frame {idx} (t={ts:.1f}s): detected {len(rects)} rects: {rects}")
                    frame_detections.append((frame_path, rects))
                else:
                    logger.debug(f"  Frame {idx} (t={ts:.1f}s): no rects detected")
            except Exception as e:
                logger.warning(f"Failed to extract/detect frame at t={ts:.1f}s: {e}")
                continue
    
    if not frame_detections:
        logger.warning("No buttons detected in any sampled frames")
        return {}
    
    # Now match buttons across frames
    # Strategy: For each button position, find the "best" frame that has it
    button_map: dict[int, tuple[Path, tuple[int, int, int, int]]] = {}
    
    # Collect all unique button positions across all frames
    all_rects: list[tuple[Path, tuple[int, int, int, int]]] = []
    for frame_path, rects in frame_detections:
        for rect in rects:
            all_rects.append((frame_path, rect))
    
    # Group similar rectangles (same button appearing in multiple frames)
    used_rects = set()
    button_idx = 0
    
    for frame_path, rect in all_rects:
        if (frame_path, rect) in used_rects:
            continue
        
        # Find all similar rects across all frames (same button)
        similar_rects = [(frame_path, rect)]
        used_rects.add((frame_path, rect))
        
        for other_frame, other_rect in all_rects:
            if (other_frame, other_rect) in used_rects:
                continue
            # Check if this is the same button (similar position and size)
            # Use stricter threshold (30px) for vertically-stacked buttons
            if _rects_are_similar(rect, other_rect, position_threshold=30, size_threshold=0.3):
                similar_rects.append((other_frame, other_rect))
                used_rects.add((other_frame, other_rect))
        
        # Pick the "best" frame for this button (highest quality/clarity)
        # For now, just use the first occurrence
        best_frame, best_rect = similar_rects[0]
        button_map[button_idx] = (best_frame, best_rect)
        logger.info(f"  Button {button_idx}: found in {len(similar_rects)} frame(s), using {best_frame.name} at {best_rect}")
        button_idx += 1
        
        if button_idx >= expected:
            break
    
    return button_map


def _detect_menu_rects_from_static_frame(
    vob_path: Path,
    output_dir: Path,
    expected: int,
    block_size: int = 16,
) -> list[tuple[int, int, int, int]]:
    import logging

    logger = logging.getLogger(__name__)
    duration = _probe_video_duration(vob_path)
    if duration is None or duration <= 0:
        return []
    timestamp = max(0.0, min(duration - 0.01, duration * 0.1))
    temp_dir = output_dir / "_menu_detect"
    temp_dir.mkdir(parents=True, exist_ok=True)
    frame_path = temp_dir / f"{vob_path.stem}_static.png"
    _extract_frame_at(vob_path, frame_path, timestamp)
    image = Image.open(frame_path).convert("L")
    width, height = image.size
    pixels = image.load()

    # First try: detect dark rectangular thumbnail regions (common in DVD menus)
    dark_block_size = 8
    dark_blocks = []
    for by in range(0, height, dark_block_size):
        for bx in range(0, width // 2, dark_block_size):  # Search left half
            values = []
            for y in range(by, min(by + dark_block_size, height)):
                for x in range(bx, min(bx + dark_block_size, width)):
                    values.append(pixels[x, y])
            if not values:
                continue
            mean_val = sum(values) / len(values)
            # Dark threshold for thumbnail content (not too aggressive)
            if mean_val < 65:
                dark_blocks.append((bx, by, bx + dark_block_size - 1, by + dark_block_size - 1))

    if dark_blocks:
        # Merge adjacent dark blocks iteratively
        merged = []
        used = set()
        for idx, (x1, y1, x2, y2) in enumerate(dark_blocks):
            if idx in used:
                continue
            current = [x1, y1, x2, y2]
            changed = True
            while changed:
                changed = False
                for jdx, (ox1, oy1, ox2, oy2) in enumerate(dark_blocks):
                    if jdx in used or jdx == idx:
                        continue
                    # Strictly adjacent (within 1 block size, no gaps)
                    if (abs(ox1 - current[2]) <= dark_block_size and 
                        not (oy2 < current[1] or oy1 > current[3])):
                        # Horizontally adjacent
                        current = [
                            min(current[0], ox1),
                            min(current[1], oy1),
                            max(current[2], ox2),
                            max(current[3], oy2),
                        ]
                        used.add(jdx)
                        changed = True
                    elif (abs(oy1 - current[3]) <= dark_block_size and 
                          not (ox2 < current[0] or ox1 > current[2])):
                        # Vertically adjacent - merge but with strict height limit
                        # This lets one thumbnail grow fully but prevents merging separate buttons
                        new_height = max(current[3], oy2) - min(current[1], oy1) + 1
                        if new_height <= 120:  # Max single thumbnail height (was 180, too permissive)
                            current = [
                                min(current[0], ox1),
                                min(current[1], oy1),
                                max(current[2], ox2),
                                max(current[3], oy2),
                            ]
                            used.add(jdx)
                            changed = True
            merged.append(tuple(current))

        # Filter by thumbnail size and compactness
        thumbnails = []
        # Sort by size to see largest candidates first
        merged_sorted = sorted(merged, key=lambda r: (r[2]-r[0]+1) * (r[3]-r[1]+1), reverse=True)
        logger.info("menu_images: merged dark regions (showing first 15 by size): %s", 
                    [(r, (r[2]-r[0]+1, r[3]-r[1]+1)) for r in merged_sorted[:15]])
        
        for rect in merged_sorted:
            x1, y1, x2, y2 = rect
            w = x2 - x1 + 1
            h = y2 - y1 + 1
            bbox_area = w * h
            
            # Count actual dark pixels in this bounding box
            dark_pixel_count = 0
            for y in range(y1, min(y2 + 1, height)):
                for x in range(x1, min(x2 + 1, width)):
                    if pixels[x, y] < 65:  # Match the detection threshold
                        dark_pixel_count += 1
            
            compactness = dark_pixel_count / bbox_area if bbox_area > 0 else 0
            
            # Thumbnail candidates: reasonable size, decent compactness (solid rectangles)
            # Relaxed compactness to 0.25 to catch more candidates
            if (50 <= w <= 300 and 50 <= h <= 300 and 
                2500 <= bbox_area <= 90000 and compactness > 0.25):
                thumbnails.append(rect)
                logger.info("menu_images: thumbnail candidate: rect=%s size=(%d,%d) compactness=%.2f", 
                           rect, w, h, compactness)

        if thumbnails:
            # Filter out edge rects (too close to frame borders)
            edge_margin = 20
            bottom_margin = 100  # Larger margin at bottom to avoid navigation UI
            filtered_thumbnails = [
                rect for rect in thumbnails
                if (rect[0] > edge_margin and rect[1] > edge_margin and 
                    rect[3] < height - bottom_margin)  # Exclude rects near bottom edge
            ]
            logger.info("menu_images: %d thumbnails after edge filter: %s", len(filtered_thumbnails), filtered_thumbnails)
            
            # Dedupe by vertical position (may return fewer than expected for multi-page menus)
            # Remove vertically overlapping duplicates (keep most thumbnail-like)
            def _thumbnail_score(rect):
                """Score how thumbnail-like a rect is (higher = more thumbnail-like)"""
                w = rect[2] - rect[0] + 1
                h = rect[3] - rect[1] + 1
                aspect = w / h if h > 0 else 0
                area = w * h
                # Prefer: aspect close to 1.0, size 80-140px, compact shape
                aspect_score = 1.0 - abs(aspect - 1.0)  # 1.0 best for square
                size_score = 1.0 if 80 <= w <= 140 and 80 <= h <= 200 else 0.5
                return aspect_score + size_score
            
            deduped = []
            for rect in sorted(filtered_thumbnails, key=_thumbnail_score, reverse=True):
                y_center = (rect[1] + rect[3]) / 2
                overlaps = False
                for existing in deduped:
                    existing_y_center = (existing[1] + existing[3]) / 2
                    if abs(y_center - existing_y_center) < 100:  # Same row threshold
                        overlaps = True
                        break
                if not overlaps:
                    deduped.append(rect)
            # Sort by vertical position
            deduped.sort(key=lambda r: (r[1], r[0]))
            logger.info("menu_images: static frame detected %d thumbnail(s) after dedup (expected %d): %s", 
                       len(deduped), expected, deduped)
            # Return what we found (may be less than expected for multi-page menus)
            if len(deduped) > 0:
                return deduped
            
            # Fallback: use original thumbnails
            thumbnails.sort(key=lambda r: (r[1], r[0]))  # Top to bottom
            logger.info("menu_images: static frame detected %d thumbnail(s): %s", len(thumbnails), thumbnails)
            return thumbnails[:expected]
        else:
            logger.info("menu_images: static frame found %d dark regions but none matched thumbnail size", len(merged))

    # Fallback: variance-based detection
    mask = Image.new("L", (width, height), 0)
    mask_pixels = mask.load()
    for y in range(0, height, block_size):
        for x in range(0, width, block_size):
            crop = image.crop((x, y, min(width, x + block_size), min(height, y + block_size)))
            stat = ImageStat.Stat(crop)
            if stat.var[0] > 200.0:
                for yy in range(y, min(height, y + block_size)):
                    for xx in range(x, min(width, x + block_size)):
                        mask_pixels[xx, yy] = 255

    rects = _connected_components(mask)
    if not rects:
        return []
    min_area = width * height * 0.005
    max_area = width * height * 0.5
    rects = [
        rect
        for rect in rects
        if min_area
        <= (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)
        <= max_area
    ]
    rects = sorted(
        rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), reverse=True
    )
    # Dedupe highly-overlapping rects.
    deduped: list[tuple[int, int, int, int]] = []
    for rect in rects:
        x1, y1, x2, y2 = rect
        area = (x2 - x1 + 1) * (y2 - y1 + 1)
        keep = True
        for ox1, oy1, ox2, oy2 in deduped:
            ix1 = max(x1, ox1)
            iy1 = max(y1, oy1)
            ix2 = min(x2, ox2)
            iy2 = min(y2, oy2)
            if ix2 >= ix1 and iy2 >= iy1:
                inter = (ix2 - ix1 + 1) * (iy2 - iy1 + 1)
                oarea = (ox2 - ox1 + 1) * (oy2 - oy1 + 1)
                if inter / min(area, oarea) > 0.9:
                    keep = False
                    break
        if keep:
            deduped.append(rect)
    rects = deduped
    rects = rects[:expected]
    rects = sorted(rects, key=lambda r: (r[1], r[0]))
    return rects


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


def _refine_cropped_image(path: Path) -> None:
    try:
        image = Image.open(path)
    except Exception:
        return
    width, height = image.size
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except Exception:
        return
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for text, x, y, w, h in zip(
        data.get("text", []),
        data.get("left", []),
        data.get("top", []),
        data.get("width", []),
        data.get("height", []),
        strict=False,
    ):
        if not text or not text.strip():
            continue
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)
    if max_x <= min_x or max_y <= min_y:
        return
    pad = max(2, int(min(width, height) * 0.05))
    left = max(0, min_x - pad)
    top = max(0, min_y - pad)
    right = min(width, max_x + pad)
    bottom = min(height, max_y + pad)
    if right - left < 2 or bottom - top < 2:
        return
    cropped = image.crop((left, top, right, bottom))
    cropped.save(path)


def _match_reference_rect(bg_path: Path, reference_path: Path) -> RectModel | None:
    try:
        bg = Image.open(bg_path).convert("L")
        ref = Image.open(reference_path).convert("L")
    except Exception:
        return None
    scale = 0.5
    bg_small = bg.resize(
        (max(1, int(bg.width * scale)), max(1, int(bg.height * scale)))
    )
    ref_small = ref.resize(
        (max(1, int(ref.width * scale)), max(1, int(ref.height * scale)))
    )
    bw, bh = bg_small.size
    rw, rh = ref_small.size
    if rw >= bw or rh >= bh:
        return None
    best_score = None
    best_xy = (0, 0)
    step = 2
    for y in range(0, bh - rh + 1, step):
        for x in range(0, bw - rw + 1, step):
            patch = bg_small.crop((x, y, x + rw, y + rh))
            diff = ImageChops.difference(patch, ref_small)
            stat = ImageStat.Stat(diff)
            score = stat.mean[0]
            if best_score is None or score < best_score:
                best_score = score
                best_xy = (x, y)
    if best_score is None:
        return None
    full_x = int(best_xy[0] / scale)
    full_y = int(best_xy[1] / scale)
    return RectModel(x=full_x, y=full_y, w=ref.width, h=ref.height)


def _ocr_line_rects(bg_path: Path) -> list[RectModel]:
    try:
        image = Image.open(bg_path)
    except Exception:
        return []
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except Exception:
        return []
    lines: dict[tuple[int, int, int], dict[str, int]] = {}
    for text, left, top, width, height, block, par, line in zip(
        data.get("text", []),
        data.get("left", []),
        data.get("top", []),
        data.get("width", []),
        data.get("height", []),
        data.get("block_num", []),
        data.get("par_num", []),
        data.get("line_num", []),
        strict=False,
    ):
        if not text or not text.strip():
            continue
        key = (int(block), int(par), int(line))
        entry = lines.get(key)
        if entry is None:
            lines[key] = {
                "left": int(left),
                "top": int(top),
                "right": int(left + width),
                "bottom": int(top + height),
            }
        else:
            entry["left"] = min(entry["left"], int(left))
            entry["top"] = min(entry["top"], int(top))
            entry["right"] = max(entry["right"], int(left + width))
            entry["bottom"] = max(entry["bottom"], int(top + height))
    rects: list[RectModel] = []
    for bounds in lines.values():
        w = bounds["right"] - bounds["left"]
        h = bounds["bottom"] - bounds["top"]
        if w < 10 or h < 10:
            continue
        rects.append(
            RectModel(x=bounds["left"], y=bounds["top"], w=w, h=h)
        )
    rects.sort(key=lambda r: (r.y, r.x))
    return rects


def _choose_ocr_rect(
    rects: list[RectModel],
    entry_id: str,
) -> RectModel | None:
    if not rects:
        return None
    try:
        index = int(entry_id.replace("btn", "")) - 1
    except ValueError:
        return None
    if 0 <= index < len(rects):
        return rects[index]
    return None


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


def _shrink_rect(rect: RectModel, ratio: float) -> RectModel:
    if ratio >= 1.0:
        return rect
    new_w = max(1, round(rect.w * ratio))
    new_h = max(1, round(rect.h * ratio))
    dx = (rect.w - new_w) // 2
    dy = (rect.h - new_h) // 2
    return RectModel(
        x=rect.x + dx,
        y=rect.y + dy,
        w=new_w,
        h=new_h,
    )


def _adjust_rect_for_text(
    rect: RectModel,
    width_ratio: float,
    top_ratio: float,
    bottom_ratio: float,
    left_shift: int = 0,
) -> RectModel:
    new_w = max(1, round(rect.w * width_ratio))
    top_pad = round(rect.h * top_ratio)
    bottom_pad = round(rect.h * bottom_ratio)
    new_h = rect.h + top_pad + bottom_pad
    return RectModel(
        x=max(0, rect.x + left_shift),
        y=max(0, rect.y - top_pad),
        w=new_w,
        h=new_h,
    )


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
    use_reference_guidance: bool = False,
) -> MenuImagesModel:
    menu_map = read_json(menu_map_path, MenuMapModel)
    def _entry_sort_key(entry: MenuEntryModel) -> tuple[int, str]:
        if entry.playback_order is not None:
            return (entry.playback_order, entry.entry_id)
        digits = "".join(ch for ch in entry.entry_id if ch.isdigit())
        return (int(digits) if digits else 0, entry.entry_id)
    ordered_entries = sorted(menu_map.entries, key=_entry_sort_key)
    output_dir = out_dir / "menu_images"
    output_dir.mkdir(parents=True, exist_ok=True)
    menu_overlap_flags: dict[str, bool] = {}
    menu_rects: dict[str, list[tuple[str, RectModel]]] = {}
    logger = logging.getLogger(__name__)
    for entry in ordered_entries:
        rect = entry.selection_rect or entry.highlight_rect or entry.rect
        if rect is None:
            continue
        menu_id = entry.menu_id or "unknown_menu"
        menu_rects.setdefault(menu_id, []).append((entry.entry_id, rect))
    for menu_id, rects in menu_rects.items():
        menu_overlap_flags[menu_id] = _rects_overlap_too_much(rects, 0.2)

    # Cache for extracted menu backgrounds to avoid redundant ffmpeg calls
    # menu_id -> background_png_path
    menu_backgrounds: dict[str, Path] = {}
    menu_sizes: dict[str, Tuple[int, int]] = {}
    pgc_vob_map: dict[tuple[int, int], int] = {}

    nav_path = out_dir / "nav.json"
    if nav_path.is_file():
        nav = read_json(nav_path, NavigationModel)
        for title in nav.dvd.titles:
            for pgc in title.pgcs:
                if pgc.cells:
                    vob_id = pgc.cells[0].vob_id
                    if vob_id is not None:
                        pgc_vob_map[(title.title_id, pgc.pgc_id)] = int(vob_id)

    entries: list[MenuImageEntry] = []
    menu_ocr_rects: dict[str, list[RectModel]] = {}
    used_rects: dict[str, list[tuple[str, RectModel]]] = {}
    placeholder_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+7VZkAAAAASUVORK5CYII="
    )
    if use_real_ffmpeg and video_ts_path is None and reference_dir is None:
        raise ValidationError("menu_images requires VIDEO_TS path or reference images")

    fallback_rects: dict[str, list[tuple[int, int, int, int]]] = {}
    fallback_entries: set[str] = set()  # Track entries using fallback rects
    button_frame_map: dict[str, dict[int, Path]] = {}  # menu_id -> button_index -> frame_path
    btn_it_analysis: dict[str, MenuPageAnalysis] = {}  # menu_id -> BTN_IT page analysis
    button_to_page: dict[str, dict[int, int]] = {}  # menu_id -> button_idx -> page_num
    if use_real_ffmpeg and video_ts_path:
        entries_by_menu: dict[str, list[MenuEntryModel]] = {}
        for entry in ordered_entries:
            menu_id = entry.menu_id or "unknown_menu"
            entries_by_menu.setdefault(menu_id, []).append(entry)
        for menu_id, menu_entries in entries_by_menu.items():
            if any(
                entry.selection_rect or entry.highlight_rect or entry.rect
                for entry in menu_entries
            ):
                continue
            menu_base = _menu_base_id(menu_id)
            vob_path = None
            if menu_base and menu_base.upper().startswith("VTSM"):
                # VTSM menus are in VTS_XX_0.VOB (menu VOB), not VTS_XX_1.VOB (title VOB)
                parts = menu_base.split("_")
                if len(parts) >= 2 and parts[1].isdigit():
                    vob_path = video_ts_path / f"VTS_{parts[1]}_0.VOB"
            elif menu_base and menu_base.upper().startswith("VMGM"):
                # VMGM menus are in VIDEO_TS.VOB
                vob_path = video_ts_path / "VIDEO_TS.VOB"
            elif menu_base == "dvd_root" or menu_id == "dvd_root":
                # "dvd_root" typically means main menu in VIDEO_TS.VOB
                vob_path = video_ts_path / "VIDEO_TS.VOB"
            if vob_path is None or not vob_path.is_file():
                # Fallback: try VIDEO_TS.VOB first, then any VTS menu VOB
                candidates = [video_ts_path / "VIDEO_TS.VOB"]
                candidates.extend(sorted(video_ts_path.glob("VTS_*_0.VOB")))
                for candidate in candidates:
                    if candidate.is_file():
                        vob_path = candidate
                        break
            if vob_path and vob_path.is_file():
                # Analyze BTN_IT structure for page detection
                page_analysis = analyze_btn_it_structure(vob_path)
                if page_analysis:
                    btn_it_analysis[menu_id] = page_analysis
                    logger.info(
                        f"menu_images: BTN_IT analysis found {page_analysis.page_count} page(s) "
                        f"for {menu_id}"
                    )
                
                # NEW: Try multi-page detection first for better page 2+ coverage
                multipage_map = _detect_menu_rects_multi_page(
                    vob_path, output_dir, expected=len(menu_entries), sample_interval=3.0
                )
                
                rects = []
                if multipage_map and len(multipage_map) >= len(menu_entries):
                    # Multi-page detection succeeded! Use those results
                    logger.info(f"menu_images: multi-page detection found {len(multipage_map)} buttons for {menu_id}")
                    # Extract rects and store frame mappings
                    button_frame_map[menu_id] = {}
                    for btn_idx in sorted(multipage_map.keys()):
                        frame_path, rect = multipage_map[btn_idx]
                        rects.append(rect)
                        button_frame_map[menu_id][btn_idx] = frame_path
                        logger.info(f"    Button {btn_idx}: {rect} from {frame_path.name}")
                else:
                    # Fallback to single-frame detection
                    logger.info(f"menu_images: falling back to single-frame detection for {menu_id}")
                    static_rects = _detect_menu_rects_from_static_frame(
                        vob_path, output_dir, expected=len(menu_entries)
                    )
                    if len(static_rects) >= len(menu_entries):
                        rects = static_rects
                    else:
                        # Fall back to video-based (frame differencing) detection
                        rects, is_static = _detect_menu_rects_from_video(
                            vob_path, output_dir, expected=len(menu_entries)
                        )
                        if len(static_rects) > len(rects):
                            rects = static_rects
                
                if rects:
                    logger.info(
                        "menu_images: raw detected rects for %s: %s",
                        menu_id,
                        rects,
                    )
                    # Expand rects to include adjacent text if needed.
                    # IMPORTANT: For vertically stacked buttons (column layout):
                    # - Buttons can expand horizontally without limit (to capture text)
                    # - Only prevent expansion if another button is on SAME ROW
                    # - Buttons above/below do NOT restrict horizontal expansion
                    # - For multi-page menus, skip overlap checks (buttons on different pages can overlap)
                    is_multipage = menu_id in button_frame_map
                    sorted_rects = sorted(rects, key=lambda r: (r[1], r[0]))  # Sort by y, then x
                    expanded_rects = []
                    for idx, rect in enumerate(sorted_rects):
                        x1, y1, x2, y2 = rect
                        w = x2 - x1 + 1
                        h = y2 - y1 + 1
                        # Heuristic: if rect is roughly square and < 30% of frame width,
                        # likely a thumbnail; expand right to capture adjacent text.
                        aspect = w / h if h > 0 else 1.0
                        if 0.5 <= aspect <= 2.0 and w < 720 * 0.3:
                            expansion = int(w * 2.5)
                            max_x2 = min(719, x2 + expansion)
                            
                            # Check for buttons to the right on the same row (prevent overlap)
                            # Skip this check for multi-page menus (buttons on different pages can overlap)
                            if not is_multipage:
                                # Note: Buttons above/below (different rows) are ignored
                                for other_idx, other_rect in enumerate(sorted_rects):
                                    if other_idx == idx:
                                        continue
                                    other_x1, other_y1, other_x2, other_y2 = other_rect
                                    
                                    # If on similar vertical position (same row), limit expansion
                                    if abs(other_y1 - y1) < 50:  # Same row threshold
                                        # Leave a 10px gap to prevent overlap
                                        max_x2 = min(max_x2, other_x1 - 10)
                                    # Note: buttons stacked vertically (same x, different y)
                                    # should NOT limit each other's horizontal expansion
                            
                            expanded_rects.append((x1, y1, max(x2, max_x2), y2))
                        else:
                            expanded_rects.append(rect)
                    logger.info(
                        "menu_images: expanded rects for %s: %s",
                        menu_id,
                        expanded_rects,
                    )
                    # Restore original order by button index
                    original_order_rects = []
                    for orig_rect in rects:
                        for exp_rect in expanded_rects:
                            if exp_rect[0] == orig_rect[0] and exp_rect[1] == orig_rect[1]:
                                original_order_rects.append(exp_rect)
                                break
                    fallback_rects[menu_id] = original_order_rects
                    logger.info(
                        "menu_images: detected %d rects from video for %s",
                        len(expanded_rects),
                        menu_id,
                    )
                elif is_static:
                    logger.warning(
                        "menu_images: video frames appear static for %s; "
                        "dynamic highlight detection may be unavailable",
                        menu_id,
                    )
    
    # Assign buttons to pages using BTN_IT analysis
    if btn_it_analysis:
        logger.info("menu_images: assigning buttons to pages using BTN_IT data")
        for menu_id, menu_entries in entries_by_menu.items():
            if menu_id not in btn_it_analysis:
                continue
            
            page_analysis = btn_it_analysis[menu_id]
            detected_rects = fallback_rects.get(menu_id, [])
            detected_indices = list(range(len(detected_rects)))
            
            button_to_page[menu_id] = assign_buttons_to_pages(
                expected_button_count=len(menu_entries),
                detected_button_indices=detected_indices,
                page_analysis=page_analysis,
            )

    for entry in ordered_entries:
        dst = output_dir / f"{entry.entry_id}.png"
        assert_in_out_dir(dst, out_dir)
        menu_id = entry.menu_id or "unknown_menu"
        crop_rect = entry.selection_rect or entry.highlight_rect or entry.rect
        if crop_rect is None and menu_id in fallback_rects:
            rects = fallback_rects[menu_id]
            index = 0
            try:
                index = int(entry.entry_id.replace("btn", "")) - 1
            except ValueError:
                index = 0
            if 0 <= index < len(rects):
                x1, y1, x2, y2 = rects[index]
                crop_rect = RectModel(x=x1, y=y1, w=x2 - x1 + 1, h=y2 - y1 + 1)
            elif len(rects) > 0:
                # For buttons beyond detected rects (e.g., on other menu pages),
                # use a simple fallback that won't be expanded
                # Place it in a safe region where text might be
                crop_rect = RectModel(x=350, y=350, w=300, h=100)
                fallback_entries.add(entry.entry_id)
                
                # Check if we know which page this button is on from BTN_IT
                page_info = ""
                if menu_id in button_to_page:
                    btn_idx = index
                    if btn_idx in button_to_page[menu_id]:
                        page_num = button_to_page[menu_id][btn_idx]
                        total_pages = btn_it_analysis[menu_id].page_count if menu_id in btn_it_analysis else 1
                        page_info = f" [BTN_IT: page {page_num + 1}/{total_pages}]"
                
                logger.warning(
                    f"menu_images: {entry.entry_id} using fallback rect{page_info}"
                )

        # 1. Reference images for explicit test runs (optional)
        if use_real_ffmpeg and reference_dir is not None:
            src_reference = reference_dir / f"{entry.entry_id}.png"
            if not src_reference.is_file():
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
        elif use_real_ffmpeg and video_ts_path:
            # 3. Try real extraction from DVD VOBs
            # IMPORTANT: Extract from MENU VOB (where button image is), NOT target VOB (where button leads)
            menu_base = _menu_base_id(entry.menu_id)
            vob_path = None
            
            # First priority: use menu_id to find the menu VOB
            if menu_base and menu_base.upper() == "VMGM":
                vob_path = video_ts_path / "VIDEO_TS.VOB"
            elif menu_base and menu_base.upper().startswith("VTSM"):
                # Expecting something like VTSM_01
                parts = menu_base.split("_")
                if len(parts) >= 2 and parts[1].isdigit():
                    vob_path = video_ts_path / f"VTS_{parts[1]}_0.VOB"
            elif menu_base == "dvd_root" or menu_id == "dvd_root":
                # "dvd_root" typically means main menu in VIDEO_TS.VOB
                vob_path = video_ts_path / "VIDEO_TS.VOB"
            
            # Fallback to VIDEO_TS.VOB or first menu VOB found
            if vob_path is None or not vob_path.is_file():
                fallback = video_ts_path / "VIDEO_TS.VOB"
                if fallback.is_file():
                    vob_path = fallback
                else:
                    # Try VTS menu VOBs (VTS_XX_0.VOB)
                    candidates = sorted(video_ts_path.glob("VTS_*_0.VOB"))
                    if candidates:
                        vob_path = candidates[0]

            if vob_path and vob_path.is_file():
                # Check if this button has a specific frame from multi-page detection
                button_index = None
                try:
                    button_index = int(entry.entry_id.replace("btn", "")) - 1
                except ValueError:
                    pass
                
                if (menu_id in button_frame_map and 
                    button_index is not None and 
                    button_index in button_frame_map[menu_id]):
                    # Use button-specific frame from multi-page detection
                    bg_path = button_frame_map[menu_id][button_index]
                    bg_size = _probe_image_size(bg_path)
                    logger.info(f"menu_images: using multi-page frame {bg_path.name} for {entry.entry_id}")
                else:
                    # Use default menu background frame
                    bg_cache_path = output_dir / f"bg_{entry.menu_id}.png"
                    if entry.menu_id not in menu_backgrounds:
                        # Always extract frame (overwrite if exists to avoid stale cache)
                        _extract_frame(vob_path, bg_cache_path)
                        menu_backgrounds[entry.menu_id] = bg_cache_path
                        menu_sizes[entry.menu_id] = _probe_image_size(bg_cache_path)
                    bg_path = menu_backgrounds[entry.menu_id]
                    bg_size = menu_sizes[entry.menu_id]
                needs_overlap_fix = menu_overlap_flags.get(menu_id, False)
                used_guidance = False
                if (use_reference_guidance or needs_overlap_fix) and entry.menu_id:
                    if entry.menu_id not in menu_ocr_rects:
                        menu_ocr_rects[entry.menu_id] = _ocr_line_rects(bg_path)
                    ocr_rects = menu_ocr_rects.get(entry.menu_id, [])
                    chosen = _choose_ocr_rect(ocr_rects, entry.entry_id)
                    if chosen is not None:
                        crop_rect = chosen
                        used_guidance = True
                    elif use_reference_guidance and src_reference is not None:
                        guided_rect = _match_reference_rect(bg_path, src_reference)
                        if guided_rect is not None:
                            crop_rect = guided_rect
                            used_guidance = True
                if not crop_rect:
                    raise ValidationError(
                        f"Missing button rect for entry_id {entry.entry_id} even after fallback"
                    )

                crop_rect = _normalize_rect_to_image(crop_rect, bg_size)
                # Skip text adjustment for fallback entries (multi-page menu buttons)
                if (
                    use_real_ffmpeg
                    and not use_reference_guidance
                    and entry.entry_id not in fallback_entries
                    and crop_rect.w > 100
                    and crop_rect.h < 90
                ):
                    rect_center_x = crop_rect.x + (crop_rect.w / 2)
                    if rect_center_x > (bg_size[0] * 0.45):
                        crop_rect = _adjust_rect_for_text(
                            crop_rect, 0.88, 0.0, 0.0, left_shift=-8
                        )
                    else:
                        if crop_rect.y > 200:
                            crop_rect = _adjust_rect_for_text(
                                crop_rect, 0.88, 0.2, 0.05
                            )
                        else:
                            crop_rect = _adjust_rect_for_text(
                                crop_rect, 0.88, 0.35, 0.1
                            )
                if use_reference_guidance and crop_rect.w > 100 and crop_rect.h > 50:
                    crop_rect = _shrink_rect(crop_rect, 0.85)
                if (
                    crop_rect.x + crop_rect.w > bg_size[0]
                    or crop_rect.y + crop_rect.h > bg_size[1]
                ):
                    raise ValidationError(
                        f"Invalid crop rect for entry_id {entry.entry_id}: "
                        f"{crop_rect} exceeds {bg_size[0]}x{bg_size[1]}"
                    )
                _crop_image(bg_path, dst, crop_rect)
                if use_reference_guidance and used_guidance:
                    _refine_cropped_image(dst)
            else:
                raise ValidationError(
                    f"Missing menu VOB for entry_id {entry.entry_id}"
                )
        elif src_reference is not None and use_real_ffmpeg and not use_reference_guidance:
            shutil.copyfile(src_reference, dst)

        if crop_rect is not None and entry.entry_id not in fallback_entries:
            # Only track non-fallback rects for overlap checking
            used_rects.setdefault(menu_id, []).append((entry.entry_id, crop_rect))
        entries.append(
            MenuImageEntry(
                entry_id=entry.entry_id,
                image_path=str(dst),
                menu_id=entry.menu_id,
                selection_rect=entry.selection_rect,
                highlight_rect=entry.highlight_rect,
                target=entry.target,
                playback_order=entry.playback_order,
            )
        )

    # Skip overlap check for menus with multi-page detection
    # (buttons on different pages can have overlapping coordinates)
    menus_to_check = {
        menu_id: rects for menu_id, rects in used_rects.items()
        if menu_id not in button_frame_map
    }
    _assert_rects_have_low_overlap(menus_to_check)
    model = MenuImagesModel(images=entries)
    write_json(out_dir / "menu_images.json", model)
    return model
