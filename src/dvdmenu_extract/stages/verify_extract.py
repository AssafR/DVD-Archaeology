from __future__ import annotations

"""Stage G2: verify_extract.

Verifies extracted media durations against segment timing using ffprobe.
Skips verification when extract outputs are stubbed.
"""

from pathlib import Path

from dvdmenu_extract.models.manifest import ExtractModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.models.verify import VerifyEntryModel, VerifyModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.io import read_json, write_json
from dvdmenu_extract.util.media import get_duration_seconds


def run(segments_path: Path, extract_path: Path, out_dir: Path) -> VerifyModel:
    segments = read_json(segments_path, SegmentsModel)
    extract = read_json(extract_path, ExtractModel)

    tolerance_sec = 1.0
    if all(output.status == "stub" for output in extract.outputs):
        model = VerifyModel(
            ok=True,
            skipped=True,
            tolerance_sec=tolerance_sec,
            results=[],
        )
        write_json(out_dir / "verify.json", model)
        return model

    segment_map = {segment.entry_id: segment for segment in segments.segments}
    results: list[VerifyEntryModel] = []
    ok = True

    for output in extract.outputs:
        segment = segment_map.get(output.entry_id)
        if segment is None:
            raise ValidationError(f"Missing segment for entry_id: {output.entry_id}")
        expected = segment.end_time - segment.start_time
        output_path = Path(output.output_path)
        if not output_path.is_file():
            ok = False
            results.append(
                VerifyEntryModel(
                    entry_id=output.entry_id,
                    expected_duration=expected,
                    actual_duration=None,
                    delta=None,
                    within_tolerance=None,
                    status="missing",
                )
            )
            continue
        try:
            actual = get_duration_seconds(output_path)
        except ValidationError as exc:
            ok = False
            results.append(
                VerifyEntryModel(
                    entry_id=output.entry_id,
                    expected_duration=expected,
                    actual_duration=None,
                    delta=None,
                    within_tolerance=None,
                    status=f"ffprobe_error: {exc}",
                )
            )
            continue
        delta = actual - expected
        within = abs(delta) <= tolerance_sec
        if not within:
            ok = False
        results.append(
            VerifyEntryModel(
                entry_id=output.entry_id,
                expected_duration=expected,
                actual_duration=actual,
                delta=delta,
                within_tolerance=within,
                status="ok" if within else "mismatch",
            )
        )

    model = VerifyModel(
        ok=ok,
        skipped=False,
        tolerance_sec=tolerance_sec,
        results=results,
    )
    write_json(out_dir / "verify.json", model)
    if not ok:
        raise ValidationError("Verification failed; see verify.json")
    return model
