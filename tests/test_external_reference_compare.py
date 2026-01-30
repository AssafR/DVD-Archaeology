from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
import shutil
import warnings
import os

import pytest

from dvdmenu_extract.models.manifest import ExtractModel
from dvdmenu_extract.stages.extract import run as extract_run
from dvdmenu_extract.stages.ingest import run as ingest_run
from dvdmenu_extract.stages.menu_map import run as menu_map_run
from dvdmenu_extract.stages.nav_parse import run as nav_parse_run
from dvdmenu_extract.stages.segments import run as segments_run
from dvdmenu_extract.stages.timing import run as timing_run
from dvdmenu_extract.util.io import read_json


EXTERNAL_SAMPLE = Path(r"Q:\DVDs\UglyBetty_s01b")
REFERENCE_DIR = EXTERNAL_SAMPLE / "Reference"
MAX_FRAME_DRIFT = 5
SSIM_EARLY_STOP = 0.995
OUTPUT_DIR = Path(
    os.environ.get("OUT_DIR", str(EXTERNAL_SAMPLE / "chapters"))
)


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


_PROBE_CACHE: dict[Path, tuple[float, float, int]] = {}
_FAST_FRAME_COUNT = True
_PROBE_VERBOSE = False
_VALIDATE_FAST_FRAME_COUNT = True


def _probe_video_stats(path: Path) -> tuple[float, float, int]:
    cached = _PROBE_CACHE.get(path)
    if cached is not None:
        return cached
    if _PROBE_VERBOSE:
        print(f"  Starting probe: {path}")
    if _FAST_FRAME_COUNT:
        fast = _probe_video_stats_fast(path)
        if fast is not None:
            if _PROBE_VERBOSE:
                print(f"  Ending probe (fast): {path}")
            if _PROBE_VERBOSE and _VALIDATE_FAST_FRAME_COUNT:
                slow = _probe_video_stats_slow(path)
                if slow is not None and slow[2] != fast[2]:
                    print(
                        f"  Probe mismatch: fast_frames={fast[2]} slow_frames={slow[2]} "
                        f"for {path}"
                    )
                if slow is not None:
                    _PROBE_CACHE[path] = slow
                    return slow
            _PROBE_CACHE[path] = fast
            return fast
    slow = _probe_video_stats_slow(path)
    if slow is None:
        raise AssertionError(f"ffprobe failed for {path}")
    _PROBE_CACHE[path] = slow
    if _PROBE_VERBOSE:
        print(f"  Ending probe: {path}")
    return slow


def _probe_video_stats_slow(path: Path) -> tuple[float, float, int] | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=r_frame_rate,nb_read_frames",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout or "{}")
    fmt = (payload.get("format") or {})
    streams = payload.get("streams") or []
    stream = streams[0] if streams else {}
    duration_str = str(fmt.get("duration", "")).strip()
    fps_str = str(stream.get("r_frame_rate", "")).strip()
    frames_str = str(stream.get("nb_read_frames", "")).strip()

    if not duration_str:
        return None
    duration = float(duration_str)
    if "/" in fps_str:
        num, denom = fps_str.split("/", maxsplit=1)
        fps = float(num) / float(denom)
    else:
        fps = float(fps_str) if fps_str else 0.0
    if not frames_str.isdigit():
        return None
    frames = int(frames_str)
    return (duration, fps, frames)


def _probe_video_stats_fast(path: Path) -> tuple[float, float, int] | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate,nb_frames",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout or "{}")
    fmt = (payload.get("format") or {})
    streams = payload.get("streams") or []
    stream = streams[0] if streams else {}
    duration_str = str(fmt.get("duration", "")).strip()
    fps_str = str(stream.get("r_frame_rate", "")).strip()
    frames_str = str(stream.get("nb_frames", "")).strip()

    if not duration_str or not fps_str or not frames_str.isdigit():
        return None
    duration = float(duration_str)
    if "/" in fps_str:
        num, denom = fps_str.split("/", maxsplit=1)
        fps = float(num) / float(denom)
    else:
        fps = float(fps_str) if fps_str else 0.0
    frames = int(frames_str)
    if duration <= 0.0 or fps <= 0.0 or frames <= 0:
        return None
    return (duration, fps, frames)


def _frame_ssim(left: Path, left_idx: int, right: Path, right_idx: int) -> float:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(left),
            "-i",
            str(right),
            "-an",
            "-sn",
            "-dn",
            "-filter_complex",
            f"[0:v]select='eq(n\\,{left_idx})',setpts=PTS-STARTPTS,"
            "fps=25,format=yuv420p[v0];"
            f"[1:v]select='eq(n\\,{right_idx})',setpts=PTS-STARTPTS,"
            "fps=25,format=yuv420p[v1];"
            "[v0][v1]ssim=stats_file=-",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "ffmpeg ssim failed for "
            f"{left} vs {right}: {result.stderr.decode(errors='ignore')}"
        )
    def _extract_ssim(text: str) -> float | None:
        for line in reversed(text.splitlines()):
            if "All:" in line:
                parts = line.strip().split()
                for part in parts:
                    if part.startswith("All:"):
                        return float(part.split(":", maxsplit=1)[1])
        return None

    stderr = result.stderr.decode(errors="ignore")
    stdout = result.stdout.decode(errors="ignore")
    ssim = _extract_ssim(stderr) or _extract_ssim(stdout)
    if ssim is not None:
        return ssim
    raise AssertionError(
        f"Unable to parse ssim for {left} vs {right}: {stderr}"
    )


def _frame_hash(path: Path, frame_idx: int) -> str:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-an",
            "-sn",
            "-dn",
            "-filter_complex",
            f"[0:v]select='eq(n\\,{frame_idx})',setpts=PTS-STARTPTS,format=yuv420p",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "ppm",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise AssertionError(
            f"ffmpeg frame hash failed for {path}: {result.stderr.decode(errors='ignore')}"
        )
    return hashlib.sha256(result.stdout).hexdigest()


def _entry_sort_key(entry_id: str) -> int:
    digits = "".join(ch for ch in entry_id if ch.isdigit())
    return int(digits) if digits else 0


def _ref_sort_key(path: Path) -> int:
    digits = "".join(ch for ch in path.stem if ch.isdigit())
    return int(digits) if digits else 0


def _output_sort_key(path: Path) -> int:
    name = path.name
    if "_" in name:
        prefix = name.split("_", 1)[0]
        if prefix.isdigit():
            return int(prefix)
    digits = "".join(ch for ch in path.stem if ch.isdigit())
    return int(digits) if digits else 0


@pytest.mark.skipif(
    not EXTERNAL_SAMPLE.exists(),
    reason="External sample not available on this machine",
)
@pytest.mark.skipif(
    not REFERENCE_DIR.exists(),
    reason="Reference output not available on this machine",
)
@pytest.mark.skipif(
    not _has_ffmpeg(),
    reason="ffmpeg/ffprobe not available on this machine",
)
def test_reference_output_matches_samples(tmp_path: Path, request) -> None:
    out_dir = OUTPUT_DIR
    skip_extract = bool(request.config.getoption("--reference-skip-extract"))
    if not skip_extract:
        if out_dir.exists():
            for path in out_dir.glob("**/*"):
                if path.is_file():
                    path.unlink()
        out_dir.mkdir(parents=True, exist_ok=True)

    if not skip_extract:
        ingest_run(EXTERNAL_SAMPLE, out_dir)
        nav_parse_run(out_dir / "ingest.json", out_dir, allow_dvd_ifo_fallback=True)
        menu_map_run(out_dir / "nav.json", out_dir)
        timing_run(
            out_dir / "nav.json",
            out_dir / "ingest.json",
            out_dir / "menu_map.json",
            out_dir,
            use_real_timing=False,
        )
        segments_run(out_dir / "menu_map.json", out_dir / "timing.json", out_dir)
        extract_run(
            out_dir / "segments.json",
            out_dir / "ingest.json",
            out_dir / "menu_map.json",
            out_dir,
            use_real_ffmpeg=True,
            repair="safe",
        )

    output_files = [
        path
        for path in (out_dir / "episodes").glob("*.mkv")
        if path.name.split("_", 1)[0].isdigit()
    ]
    output_files = sorted(output_files, key=_output_sort_key)
    reference_files = sorted(REFERENCE_DIR.glob("*.ts"), key=_ref_sort_key)

    assert output_files, "No extracted outputs found"
    assert reference_files, "No reference .ts files found"
    assert len(output_files) == len(reference_files)

    sample_fracs = [0.1, 0.5, 0.9]
    verbose = bool(request.config.getoption("--reference-verbose"))
    global _PROBE_VERBOSE
    _PROBE_VERBOSE = verbose
    def vprint(message: str) -> None:
        if verbose:
            print(message)
    used_ssim_any = False
    for output_path, ref in zip(output_files, reference_files, strict=False):
        assert output_path.is_file()
        assert ref.is_file()
        vprint(f"  Comparing {output_path} to {ref}.")

        output_duration, output_fps, output_frames = _probe_video_stats(output_path)
        ref_duration, ref_fps, ref_frames = _probe_video_stats(ref)
        assert output_duration > 1.0 and ref_duration > 1.0
        assert output_fps > 0.0 and ref_fps > 0.0
        assert output_frames > 0 and ref_frames > 0

        for frac in sample_fracs:
            output_idx = min(output_frames - 1, int(output_frames * frac))
            ref_idx = min(ref_frames - 1, int(ref_frames * frac))
            offsets = [0]
            for step in range(1, MAX_FRAME_DRIFT + 1):
                offsets.extend([-step, step])
            vprint(
                f"    Sample @ {frac:.0%}: output_frame={output_idx} ref_frame={ref_idx}"
            )
            best_ssim = 0.0
            best_offset = 0
            hash_matched = False
            try:
                output_hash = _frame_hash(output_path, output_idx)
                ref_hash = _frame_hash(ref, ref_idx)
                if output_hash == ref_hash:
                    best_ssim = 1.0
                    best_offset = 0
                    hash_matched = True
                    vprint("       Hash match at offset +0 frames.")
                    vprint("       Skipping SSIM test.")
            except AssertionError as exc:
                vprint(f"       Hash check skipped: {exc}")

            if best_ssim < 1.0:
                used_ssim_any = True
                vprint(f"       Collecting {len(offsets)} frames.")
                for offset in offsets:
                    target_idx = max(0, min(output_frames - 1, output_idx + offset))
                    ssim = _frame_ssim(
                        output_path,
                        target_idx,
                        ref,
                        ref_idx,
                    )
                    if ssim > best_ssim:
                        best_ssim = ssim
                        best_offset = offset
                    vprint(f"       Offset {offset:+d} frames -> ssim={ssim:.5f}")
                    if best_ssim >= 1.0 - 1e-6:
                        vprint("       Perfect SSIM; stopping early.")
                        break
                    if best_ssim >= SSIM_EARLY_STOP:
                        vprint(
                            f"       SSIM {best_ssim:.5f} above {SSIM_EARLY_STOP:.3f}; stopping early."
                        )
                        break
            vprint("       Comparing frames.")
            assert best_ssim >= 0.98, f"Best SSIM {best_ssim:.5f} below threshold"
            if hash_matched:
                vprint(f"       Best offset {best_offset:+d} frames (hash match).")
                vprint("       Result: hash-only.")
            else:
                vprint(f"       Best offset {best_offset:+d} frames (ssim={best_ssim:.5f})")
                vprint("       Result: used SSIM.")
        vprint("    Success")
    if used_ssim_any:
        warnings.warn(
            "Reference compare used SSIM for at least one sample; review drift if needed.",
            RuntimeWarning,
            stacklevel=1,
        )
