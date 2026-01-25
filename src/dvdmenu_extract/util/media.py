from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.process import run_process


def get_duration_seconds(path: Path) -> float:
    result = run_process(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout_sec=30,
    )
    value = result.stdout.strip()
    try:
        duration = float(value)
    except ValueError as exc:
        raise ValidationError(f"Invalid ffprobe duration: {value}") from exc
    if duration <= 0:
        raise ValidationError(f"ffprobe returned non-positive duration for {path}")
    return duration
