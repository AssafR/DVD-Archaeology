from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.models.manifest import ExtractModel, ManifestModel
from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.menu import MenuImagesModel, MenuMapModel
from dvdmenu_extract.models.nav import NavModel
from dvdmenu_extract.models.ocr import OcrModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.io import read_json, write_json


def run(out_dir: Path, stage_status: dict[str, str]) -> ManifestModel:
    ingest = read_json(out_dir / "ingest.json", IngestModel)
    nav = read_json(out_dir / "nav.json", NavModel)
    menu_map = read_json(out_dir / "menu_map.json", MenuMapModel)
    menu_images = read_json(out_dir / "menu_images.json", MenuImagesModel)
    ocr = read_json(out_dir / "ocr.json", OcrModel)
    segments = read_json(out_dir / "segments.json", SegmentsModel)
    extract = read_json(out_dir / "extract.json", ExtractModel)

    menu_button_ids = {
        button.button_id for menu in menu_map.menus for button in menu.buttons
    }
    ocr_ids = {entry.button_id for entry in ocr.results}
    segment_ids = {entry.button_id for entry in segments.segments}
    extract_ids = {entry.button_id for entry in extract.outputs}

    if menu_button_ids != ocr_ids:
        raise ValidationError("Mismatch between menu_map and ocr button ids")
    if menu_button_ids != segment_ids:
        raise ValidationError("Mismatch between menu_map and segments button ids")
    if menu_button_ids != extract_ids:
        raise ValidationError("Mismatch between menu_map and extract button ids")

    manifest = ManifestModel(
        inputs={"input_path": ingest.input_path, "out_dir": str(out_dir)},
        ingest=ingest,
        nav=nav,
        menu_map=menu_map,
        menu_images=menu_images,
        ocr=ocr,
        segments=segments,
        extract=extract,
        stage_status=stage_status,
    )
    write_json(out_dir / "manifest.json", manifest)
    return manifest
