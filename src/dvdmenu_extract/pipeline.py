from __future__ import annotations

import logging
import time
from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.manifest import ExtractModel, ManifestModel
from dvdmenu_extract.models.menu import MenuImagesModel, MenuMapModel
from dvdmenu_extract.models.nav import NavModel
from dvdmenu_extract.models.ocr import OcrModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.stages import (
    extract as extract_stage,
    finalize as finalize_stage,
    ingest as ingest_stage,
    menu_images as menu_images_stage,
    menu_map as menu_map_stage,
    nav_parse as nav_parse_stage,
    ocr as ocr_stage,
    segments as segments_stage,
)
from dvdmenu_extract.util.assertx import ValidationError, assert_file_exists
from dvdmenu_extract.util.io import StageMeta, read_json, utc_now_iso, write_stage_meta

LOGGER = logging.getLogger(__name__)

STAGES = [
    "ingest",
    "nav_parse",
    "menu_map",
    "menu_images",
    "ocr",
    "segments",
    "extract",
    "finalize",
]

STAGE_OUTPUTS = {
    "ingest": ["ingest.json"],
    "nav_parse": ["nav.json"],
    "menu_map": ["menu_map.json"],
    "menu_images": ["menu_images.json"],
    "ocr": ["ocr.json"],
    "segments": ["segments.json"],
    "extract": ["extract.json"],
    "finalize": ["manifest.json"],
}

STAGE_INPUTS = {
    "nav_parse": ["ingest.json"],
    "menu_map": ["nav.json"],
    "menu_images": ["menu_map.json"],
    "ocr": ["menu_images.json"],
    "segments": ["menu_map.json", "nav.json"],
    "extract": ["segments.json", "ocr.json"],
    "finalize": [
        "ingest.json",
        "nav.json",
        "menu_map.json",
        "menu_images.json",
        "ocr.json",
        "segments.json",
        "extract.json",
    ],
}


class PipelineOptions:
    def __init__(
        self,
        ocr_lang: str,
        use_real_ocr: bool,
        use_real_ffmpeg: bool,
        repair: str,
        force: bool,
    ) -> None:
        self.ocr_lang = ocr_lang
        self.use_real_ocr = use_real_ocr
        self.use_real_ffmpeg = use_real_ffmpeg
        self.repair = repair
        self.force = force


def _assert_required_inputs(out_dir: Path, stage: str) -> None:
    for rel_path in STAGE_INPUTS.get(stage, []):
        path = out_dir / rel_path
        assert_file_exists(path, f"Missing required upstream artifact: {path}")


def _write_meta(
    out_dir: Path,
    stage: str,
    start_time: float,
    started_at: str,
    inputs: list[str],
    outputs: list[str],
) -> None:
    finished = time.time()
    meta = StageMeta(
        stage=stage,
        started_at=started_at,
        finished_at=utc_now_iso(),
        duration_ms=int((finished - start_time) * 1000),
        inputs=inputs,
        outputs=outputs,
    )
    write_stage_meta(out_dir, meta)


def run_pipeline(
    input_path: Path,
    out_dir: Path,
    options: PipelineOptions,
    stage: str | None = None,
) -> ManifestModel | None:
    if stage and stage not in STAGES:
        raise ValidationError(f"Unknown stage: {stage}")

    out_dir.mkdir(parents=True, exist_ok=True)
    stage_status: dict[str, str] = {}

    selected = [stage] if stage else STAGES

    manifest: ManifestModel | None = None
    for stage_name in selected:
        LOGGER.info("Stage start: %s", stage_name)
        _assert_required_inputs(out_dir, stage_name)
        outputs = [str(out_dir / name) for name in STAGE_OUTPUTS[stage_name]]
        inputs = [str(out_dir / name) for name in STAGE_INPUTS.get(stage_name, [])]
        start_time = time.time()
        started_at = utc_now_iso()

        if stage_name == "ingest":
            if not options.force and (out_dir / "ingest.json").is_file():
                read_json(out_dir / "ingest.json", IngestModel)
                stage_status[stage_name] = "cached"
            else:
                ingest_stage.run(input_path, out_dir)
                stage_status[stage_name] = "ok"
        elif stage_name == "nav_parse":
            if not options.force and (out_dir / "nav.json").is_file():
                read_json(out_dir / "nav.json", NavModel)
                stage_status[stage_name] = "cached"
            else:
                nav_parse_stage.run(out_dir / "ingest.json", out_dir)
                stage_status[stage_name] = "ok"
        elif stage_name == "menu_map":
            if not options.force and (out_dir / "menu_map.json").is_file():
                read_json(out_dir / "menu_map.json", MenuMapModel)
                stage_status[stage_name] = "cached"
            else:
                menu_map_stage.run(out_dir / "nav.json", out_dir)
                stage_status[stage_name] = "ok"
        elif stage_name == "menu_images":
            if not options.force and (out_dir / "menu_images.json").is_file():
                read_json(out_dir / "menu_images.json", MenuImagesModel)
                stage_status[stage_name] = "cached"
            else:
                menu_images_stage.run(out_dir / "menu_map.json", out_dir)
                stage_status[stage_name] = "ok"
        elif stage_name == "ocr":
            if not options.force and (out_dir / "ocr.json").is_file():
                read_json(out_dir / "ocr.json", OcrModel)
                stage_status[stage_name] = "cached"
            else:
                ocr_stage.run(
                    out_dir / "menu_images.json",
                    out_dir,
                    options.ocr_lang,
                    options.use_real_ocr,
                )
                stage_status[stage_name] = "ok"
        elif stage_name == "segments":
            if not options.force and (out_dir / "segments.json").is_file():
                read_json(out_dir / "segments.json", SegmentsModel)
                stage_status[stage_name] = "cached"
            else:
                segments_stage.run(
                    out_dir / "menu_map.json", out_dir / "nav.json", out_dir
                )
                stage_status[stage_name] = "ok"
        elif stage_name == "extract":
            if not options.force and (out_dir / "extract.json").is_file():
                read_json(out_dir / "extract.json", ExtractModel)
                stage_status[stage_name] = "cached"
            else:
                extract_stage.run(
                    out_dir / "segments.json",
                    out_dir / "ocr.json",
                    out_dir,
                    options.use_real_ffmpeg,
                    options.repair,
                )
                stage_status[stage_name] = "ok"
        elif stage_name == "finalize":
            stage_status[stage_name] = "ok"
            manifest = finalize_stage.run(out_dir, stage_status)

        _write_meta(out_dir, stage_name, start_time, started_at, inputs, outputs)
        LOGGER.info("Stage end: %s", stage_name)

    if stage:
        return None
    if manifest is None:
        raise ValidationError("Finalize stage did not run in pipeline")
    return manifest
