from __future__ import annotations

import argparse
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageStat
except Exception as exc:  # pragma: no cover - environment-specific
    raise SystemExit("Pillow is required to run this script.") from exc

from dvdmenu_extract.util.libdvdread_spu import iter_spu_packets


def _ffprobe_duration(path: Path) -> float | None:
    result = subprocess.run(
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
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _extract_frame(vob_path: Path, timestamp: float, out_path: Path) -> None:
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
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed for {vob_path} @ {timestamp:.3f}s: {result.stderr}"
        )


def _mean_diff(a: Image.Image, b: Image.Image) -> float:
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    return sum(stat.mean) / max(1, len(stat.mean))


def _scan_spu_substreams(vob_path: Path, sectors: int) -> dict[int, int]:
    with vob_path.open("rb") as handle:
        data = handle.read(sectors * 2048)
    counts: Counter[int] = Counter()
    sizes: dict[int, int] = defaultdict(int)
    for substream_id, payload in iter_spu_packets(data):
        counts[substream_id] += 1
        sizes[substream_id] += len(payload)
    if not counts:
        return {}
    return {sub_id: sizes[sub_id] for sub_id in sorted(counts)}


def _analyze_vob(vob_path: Path, out_dir: Path, frame_count: int) -> None:
    duration = _ffprobe_duration(vob_path)
    if duration is None or duration <= 0:
        print(f"[{vob_path.name}] Unable to probe duration.")
        return

    step = max(0.5, duration / max(1, frame_count))
    timestamps = [min(duration - 0.01, i * step) for i in range(frame_count)]
    frame_paths: list[Path] = []

    for idx, ts in enumerate(timestamps, start=1):
        frame_path = out_dir / f"{vob_path.stem}_frame_{idx:02d}.png"
        _extract_frame(vob_path, ts, frame_path)
        frame_paths.append(frame_path)

    diffs: list[float] = []
    for idx in range(1, len(frame_paths)):
        prev = Image.open(frame_paths[idx - 1]).convert("RGB")
        curr = Image.open(frame_paths[idx]).convert("RGB")
        diffs.append(_mean_diff(prev, curr))

    print(f"[{vob_path.name}] duration={duration:.2f}s frames={len(frame_paths)}")
    if diffs:
        avg_diff = sum(diffs) / len(diffs)
        max_diff = max(diffs)
        print(f"[{vob_path.name}] frame diff avg={avg_diff:.3f} max={max_diff:.3f}")
    else:
        print(f"[{vob_path.name}] not enough frames to diff.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-ts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--spu-sectors", type=int, default=4000)
    args = parser.parse_args()

    video_ts = args.video_ts
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    for name in ("VIDEO_TS.VOB",):
        path = video_ts / name
        if path.is_file():
            candidates.append(path)
    candidates.extend(sorted(video_ts.glob("VTS_*_0.VOB")))
    candidates.extend(sorted(video_ts.glob("VTS_*_1.VOB")))
    if not candidates:
        raise SystemExit("No VOBs found to analyze.")

    for vob in candidates:
        _analyze_vob(vob, out_dir, args.frames)
        substreams = _scan_spu_substreams(vob, args.spu_sectors)
        if substreams:
            print(f"[{vob.name}] SPU substreams (bytes): {substreams}")
        else:
            print(f"[{vob.name}] No SPU substreams detected in scan.")


if __name__ == "__main__":
    main()
