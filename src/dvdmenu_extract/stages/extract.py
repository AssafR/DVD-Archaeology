from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.models.manifest import ExtractEntryModel, ExtractModel
from dvdmenu_extract.models.ocr import OcrModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.assertx import ValidationError, assert_in_out_dir
from dvdmenu_extract.util.io import read_json, write_json


def run(
    segments_path: Path,
    ocr_path: Path,
    out_dir: Path,
    use_real_ffmpeg: bool,
    repair: str,
) -> ExtractModel:
    if use_real_ffmpeg:
        raise ValidationError("Real FFmpeg extraction not implemented in v0 stub")
    if repair not in {"off", "safe"}:
        raise ValidationError("repair must be one of: off, safe")

    segments = read_json(segments_path, SegmentsModel)
    ocr = read_json(ocr_path, OcrModel)
    ocr_by_id = {entry.button_id: entry for entry in ocr.results}

    episodes_dir = out_dir / "episodes"
    logs_dir = out_dir / "logs"
    episodes_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[ExtractEntryModel] = []
    for segment in segments.segments:
        ocr_entry = ocr_by_id.get(segment.button_id)
        if not ocr_entry:
            raise ValidationError("Missing OCR for button_id in extract stage")
        filename = f"{ocr_entry.cleaned_label}.mkv"
        output_path = episodes_dir / filename
        assert_in_out_dir(output_path, out_dir)
        output_path.write_bytes(b"")

        log_path = logs_dir / f"{segment.button_id}.log"
        assert_in_out_dir(log_path, out_dir)
        log_path.write_text(
            f"stub extract button={segment.button_id} repair={repair}\n",
            encoding="utf-8",
        )
        outputs.append(
            ExtractEntryModel(
                button_id=segment.button_id,
                output_path=str(output_path),
                status="stub",
            )
        )

    model = ExtractModel(outputs=outputs)
    write_json(out_dir / "extract.json", model)
    return model
