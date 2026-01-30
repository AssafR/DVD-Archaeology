from __future__ import annotations

"""Stage H: finalize.

Merges all stage outputs into a single manifest and applies OCR-based naming
to extracted files when possible.
"""

from pathlib import Path
import logging
import shutil

from dvdmenu_extract.models.manifest import ExtractModel, ManifestModel
from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.menu import MenuImagesModel, MenuMapModel
from dvdmenu_extract.models.menu_validation import MenuValidationModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.models.nav_summary import NavSummaryModel
from dvdmenu_extract.models.ocr import OcrModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.models.verify import VerifyModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.io import read_json, write_json


def run(
    out_dir: Path,
    stage_status: dict[str, str],
    overwrite_outputs: bool = False,
) -> ManifestModel:
    ingest = read_json(out_dir / "ingest.json", IngestModel)
    nav = read_json(out_dir / "nav.json", NavigationModel)
    nav_summary = read_json(out_dir / "nav_summary.json", NavSummaryModel)
    menu_map = read_json(out_dir / "menu_map.json", MenuMapModel)
    menu_validation = read_json(
        out_dir / "menu_validation.json", MenuValidationModel
    )
    menu_images = read_json(out_dir / "menu_images.json", MenuImagesModel)
    ocr = read_json(out_dir / "ocr.json", OcrModel)
    segments = read_json(out_dir / "segments.json", SegmentsModel)
    extract = read_json(out_dir / "extract.json", ExtractModel)
    verify = read_json(out_dir / "verify.json", VerifyModel)

    menu_entry_ids = {entry.entry_id for entry in menu_map.entries}
    ocr_ids = {entry.entry_id for entry in ocr.results}
    segment_ids = {entry.entry_id for entry in segments.segments}
    extract_ids = {entry.entry_id for entry in extract.outputs}

    if menu_entry_ids != ocr_ids:
        raise ValidationError("Mismatch between menu_map and ocr entry ids")
    if menu_entry_ids != segment_ids:
        raise ValidationError("Mismatch between menu_map and segments entry ids")
    if menu_entry_ids != extract_ids:
        raise ValidationError("Mismatch between menu_map and extract entry ids")

    ocr_by_id = {entry.entry_id: entry for entry in ocr.results}
    ordered_segments = sorted(
        segments.segments, key=lambda seg: (seg.playback_order or 0, seg.entry_id)
    )
    index_by_id = {seg.entry_id: idx + 1 for idx, seg in enumerate(ordered_segments)}
    logger = logging.getLogger(__name__)
    for output in extract.outputs:
        entry = ocr_by_id.get(output.entry_id)
        if not entry:
            continue
        index = index_by_id.get(output.entry_id)
        prefix = f"{index:02d}_" if index is not None else ""
        desired_name = f"{prefix}{entry.cleaned_label}.mkv"
        current_path = Path(output.output_path)
        target_path = current_path.with_name(desired_name)
        if current_path == target_path:
            continue
        if not current_path.is_file():
            raise ValidationError(f"Missing extracted file: {current_path}")
        if target_path.exists():
            if overwrite_outputs:
                if target_path.is_dir():
                    raise ValidationError(
                        f"Target path is a directory: {target_path}"
                    )
                target_path.unlink()
            else:
                raise ValidationError(f"Target filename already exists: {target_path}")
        logger.info("copying %s to %s", current_path.name, target_path.name)
        shutil.copy2(current_path, target_path)
        output.output_path = str(target_path)

    # Sync report: playback order -> output file -> OCR label
    extract_by_id = {entry.entry_id: entry for entry in extract.outputs}
    for seg in ordered_segments:
        ocr_entry = ocr_by_id.get(seg.entry_id)
        extract_entry = extract_by_id.get(seg.entry_id)
        if not ocr_entry or not extract_entry:
            continue
        label = ocr_entry.cleaned_label or ocr_entry.raw_text
        logger.info(
            "sync: %s -> %s -> %s",
            seg.entry_id,
            Path(extract_entry.output_path).name,
            label,
        )

    manifest = ManifestModel(
        inputs={"input_path": ingest.input_path, "out_dir": str(out_dir)},
        ingest=ingest,
        nav=nav,
        nav_summary=nav_summary,
        menu_map=menu_map,
        menu_validation=menu_validation,
        menu_images=menu_images,
        ocr=ocr,
        segments=segments,
        extract=extract,
        verify=verify,
        stage_status=stage_status,
    )
    write_json(out_dir / "manifest.json", manifest)
    return manifest
