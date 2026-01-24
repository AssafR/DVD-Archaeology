from __future__ import annotations

import logging
import time
from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.manifest import ExtractModel, ManifestModel
from dvdmenu_extract.models.menu import MenuImagesModel, MenuMapModel
from dvdmenu_extract.models.nav import NavigationModel
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
    timing as timing_stage,
)
from dvdmenu_extract.util.assertx import ValidationError, assert_file_exists
from dvdmenu_extract.util.export import export_json_artifacts
from dvdmenu_extract.util.io import StageMeta, read_json, utc_now_iso, write_stage_meta

LOGGER = logging.getLogger(__name__)

STAGES = [
    "ingest",
    "nav_parse",
    "menu_map",
    "timing",
    "segments",
    "extract",
    "menu_images",
    "ocr",
    "finalize",
]

STAGE_OUTPUTS = {
    "ingest": ["ingest.json", "video_ts_report.json", "disc_report.json"],
    "nav_parse": [
        "nav.json",
        "nav_summary.json",
        "svcd_nav.json",
        "vcd_nav.json",
        "raw/vcd-info.stdout.txt",
        "raw/vcd-info.stderr.txt",
    ],
    "menu_map": ["menu_map.json"],
    "timing": ["timing.json"],
    "menu_images": ["menu_images.json"],
    "ocr": ["ocr.json"],
    "segments": ["segments.json"],
    "extract": ["extract.json"],
    "finalize": ["manifest.json"],
}

STAGE_INPUTS = {
    "nav_parse": ["ingest.json"],
    "menu_map": ["nav.json"],
    "timing": ["nav.json"],
    "segments": ["menu_map.json", "timing.json"],
    "extract": ["segments.json"],
    "menu_images": ["menu_map.json"],
    "ocr": ["menu_images.json"],
    "finalize": [
        "ingest.json",
        "nav.json",
        "nav_summary.json",
        "menu_map.json",
        "menu_images.json",
        "ocr.json",
        "timing.json",
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
        json_out_root: bool,
        json_root_dir: bool,
    ) -> None:
        self.ocr_lang = ocr_lang
        self.use_real_ocr = use_real_ocr
        self.use_real_ffmpeg = use_real_ffmpeg
        self.repair = repair
        self.force = force
        self.json_out_root = json_out_root
        self.json_root_dir = json_root_dir


def _stage_root(out_dir: Path, input_path: Path, options: PipelineOptions) -> Path:
    if options.json_root_dir:
        return input_path / "dvdmenu_extract_json"
    return out_dir


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
    until: str | None = None,
) -> ManifestModel | None:
    if stage and stage not in STAGES:
        raise ValidationError(f"Unknown stage: {stage}")
    if until and until not in STAGES:
        raise ValidationError(f"Unknown stage: {until}")
    if stage and until:
        raise ValidationError("Use stage or until, not both")

    out_dir.mkdir(parents=True, exist_ok=True)
    stage_root = _stage_root(out_dir, input_path, options)
    stage_root.mkdir(parents=True, exist_ok=True)
    stage_status: dict[str, str] = {}

    if stage:
        selected = [stage]
    elif until:
        selected = STAGES[: STAGES.index(until) + 1]
    else:
        selected = STAGES

    manifest: ManifestModel | None = None
    for stage_name in selected:
        LOGGER.info("Stage start: %s", stage_name)
        if stage_name != "ingest" and input_path is not None:
            ingest_path = stage_root / "ingest.json"
            if ingest_path.is_file():
                ingest = read_json(ingest_path, IngestModel)
                if Path(ingest.input_path).resolve() != input_path.resolve():
                    raise ValidationError(
                        "ingest.json input_path does not match current input_path"
                    )
        _assert_required_inputs(stage_root, stage_name)
        outputs = [str(stage_root / name) for name in STAGE_OUTPUTS[stage_name]]
        inputs = [str(stage_root / name) for name in STAGE_INPUTS.get(stage_name, [])]
        start_time = time.time()
        started_at = utc_now_iso()

        if stage_name == "ingest":
            if not options.force and (stage_root / "ingest.json").is_file():
                read_json(stage_root / "ingest.json", IngestModel)
                stage_status[stage_name] = "cached"
            else:
                ingest_stage.run(input_path, stage_root)
                stage_status[stage_name] = "ok"
        elif stage_name == "nav_parse":
            if not options.force and (stage_root / "nav.json").is_file():
                read_json(stage_root / "nav.json", NavigationModel)
                stage_status[stage_name] = "cached"
            else:
                nav_parse_stage.run(stage_root / "ingest.json", stage_root)
                stage_status[stage_name] = "ok"
        elif stage_name == "menu_map":
            if not options.force and (stage_root / "menu_map.json").is_file():
                read_json(stage_root / "menu_map.json", MenuMapModel)
                stage_status[stage_name] = "cached"
            else:
                menu_map_stage.run(stage_root / "nav.json", stage_root)
                stage_status[stage_name] = "ok"
        elif stage_name == "menu_images":
            if not options.force and (stage_root / "menu_images.json").is_file():
                read_json(stage_root / "menu_images.json", MenuImagesModel)
                stage_status[stage_name] = "cached"
            else:
                menu_images_stage.run(stage_root / "menu_map.json", stage_root)
                stage_status[stage_name] = "ok"
        elif stage_name == "segments":
            if not options.force and (stage_root / "segments.json").is_file():
                read_json(stage_root / "segments.json", SegmentsModel)
                stage_status[stage_name] = "cached"
            else:
                segments_stage.run(
                    stage_root / "menu_map.json",
                    stage_root / "timing.json",
                    stage_root,
                )
                stage_status[stage_name] = "ok"
        elif stage_name == "timing":
            if not options.force and (stage_root / "timing.json").is_file():
                read_json(stage_root / "timing.json", SegmentsModel)
                stage_status[stage_name] = "cached"
            else:
                timing_stage.run(stage_root / "nav.json", stage_root)
                stage_status[stage_name] = "ok"
        elif stage_name == "extract":
            if not options.force and (stage_root / "extract.json").is_file():
                read_json(stage_root / "extract.json", ExtractModel)
                stage_status[stage_name] = "cached"
            else:
                extract_stage.run(
                    stage_root / "segments.json",
                    stage_root,
                    options.use_real_ffmpeg,
                    options.repair,
                )
                stage_status[stage_name] = "ok"
        elif stage_name == "ocr":
            if not options.force and (stage_root / "ocr.json").is_file():
                read_json(stage_root / "ocr.json", OcrModel)
                stage_status[stage_name] = "cached"
            else:
                ocr_stage.run(
                    stage_root / "menu_images.json",
                    stage_root,
                    options.ocr_lang,
                    options.use_real_ocr,
                )
                stage_status[stage_name] = "ok"
        elif stage_name == "finalize":
            stage_status[stage_name] = "ok"
            manifest = finalize_stage.run(stage_root, stage_status)

        _write_meta(stage_root, stage_name, start_time, started_at, inputs, outputs)
        if options.json_out_root:
            export_json_artifacts(stage_root, input_path)
        LOGGER.info("Stage end: %s", stage_name)

    if stage or until:
        return None
    if manifest is None:
        raise ValidationError("Finalize stage did not run in pipeline")
    return manifest
