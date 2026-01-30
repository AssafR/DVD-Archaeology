from __future__ import annotations

"""Stage F: segments.

Builds segment boundaries from the navigation and menu map. This stage is
format-neutral and must not rely on DVD-specific structures.
"""

from pathlib import Path
import logging
import shutil

from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.io import read_json, write_json


def run(menu_map_path: Path, timing_path: Path, out_dir: Path) -> SegmentsModel:
    menu_map = read_json(menu_map_path, MenuMapModel)
    timing = read_json(timing_path, SegmentsModel)

    menu_entry_ids = {entry.entry_id for entry in menu_map.entries}
    for entry in timing.segments:
        if entry.entry_id not in menu_entry_ids:
            raise ValidationError("segments include unknown entry_id")

    ordered_segments = sorted(
        timing.segments, key=lambda seg: (seg.start_time, seg.entry_id)
    )
    id_map = {
        seg.entry_id: f"btn{idx + 1}"
        for idx, seg in enumerate(ordered_segments)
    }
    changed = False
    for entry in menu_map.entries:
        new_id = id_map.get(entry.entry_id, entry.entry_id)
        if new_id != entry.entry_id:
            changed = True
            entry.entry_id = new_id
    for segment in timing.segments:
        new_id = id_map.get(segment.entry_id, segment.entry_id)
        if new_id != segment.entry_id:
            changed = True
            segment.entry_id = new_id
    timing.segments = [
        segment
        for segment in sorted(
            timing.segments, key=lambda seg: (seg.start_time, seg.entry_id)
        )
    ]
    def _entry_sort_key(entry_id: str) -> int:
        digits = "".join(ch for ch in entry_id if ch.isdigit())
        return int(digits) if digits else 0
    menu_map.entries = sorted(menu_map.entries, key=lambda e: _entry_sort_key(e.entry_id))

    model = SegmentsModel.model_validate(
        {"segments": [segment.model_dump(mode="json") for segment in timing.segments]}
    )
    write_json(out_dir / "menu_map.json", menu_map)
    write_json(out_dir / "segments.json", model)
    if changed:
        logger = logging.getLogger(__name__)
        logger.info("segments: entry_id mapping updated; invalidating menu images + ocr")
        menu_images_json = out_dir / "menu_images.json"
        ocr_json = out_dir / "ocr.json"
        menu_images_dir = out_dir / "menu_images"
        if menu_images_json.exists():
            menu_images_json.unlink()
        if ocr_json.exists():
            ocr_json.unlink()
        if menu_images_dir.exists():
            shutil.rmtree(menu_images_dir)
    return model
