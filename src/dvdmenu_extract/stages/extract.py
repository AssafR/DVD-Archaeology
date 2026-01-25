from __future__ import annotations

"""Stage G: extract.

Generates episode files from segment boundaries. In stub mode, this creates
empty placeholders named by entry_id to keep extraction independent of OCR.
"""

from dataclasses import dataclass
import subprocess
from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.manifest import ExtractEntryModel, ExtractModel
from dvdmenu_extract.models.segments import SegmentEntryModel, SegmentsModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.util.assertx import ValidationError, assert_in_out_dir
from dvdmenu_extract.util.io import read_json, write_json
from dvdmenu_extract.util.media import get_duration_seconds


@dataclass
class EntrySource:
    paths: list[Path]
    durations: list[float]
    offsets: list[float]


def _compute_offsets(durations: list[float]) -> list[float]:
    offsets: list[float] = []
    cumulative = 0.0
    for duration in durations:
        offsets.append(cumulative)
        cumulative += duration
    return offsets


def _build_entry_source(paths: list[Path], duration_cache: dict[Path, float]) -> EntrySource:
    durations: list[float] = []
    for path in paths:
        if path not in duration_cache:
            duration_cache[path] = get_duration_seconds(path)
        durations.append(duration_cache[path])
    return EntrySource(
        paths=paths,
        durations=durations,
        offsets=_compute_offsets(durations),
    )


def _build_entry_source_by_size(
    paths: list[Path], total_duration: float
) -> EntrySource:
    total_bytes = sum(path.stat().st_size for path in paths)
    if total_bytes <= 0 or total_duration <= 0:
        raise ValidationError("Cannot derive duration mapping from file sizes")
    durations = [
        total_duration * (path.stat().st_size / total_bytes) for path in paths
    ]
    return EntrySource(
        paths=paths,
        durations=durations,
        offsets=_compute_offsets(durations),
    )


def _build_entry_source_by_sectors(
    paths: list[Path],
    total_duration: float,
    sector_min: int,
    sector_max: int,
) -> EntrySource:
    sector_size = 2048
    total_sectors = sector_max - sector_min + 1
    if total_sectors <= 0:
        raise ValidationError("Invalid sector range for title")

    durations: list[float] = []
    offsets: list[float] = []
    cumulative = 0.0
    current_sector = 0

    for path in paths:
        sector_count = path.stat().st_size // sector_size
        file_start = current_sector
        file_end = current_sector + sector_count - 1
        current_sector += sector_count

        overlap_start = max(file_start, sector_min)
        overlap_end = min(file_end, sector_max)
        if overlap_end < overlap_start:
            durations.append(0.0)
            offsets.append(cumulative)
            continue

        overlap_sectors = overlap_end - overlap_start + 1
        duration = total_duration * (overlap_sectors / total_sectors)
        durations.append(duration)
        offsets.append(cumulative)
        cumulative += duration

    return EntrySource(paths=paths, durations=durations, offsets=offsets)


def _build_vob_sector_map(paths: list[Path]) -> list[tuple[Path, int, int]]:
    sector_size = 2048
    mappings: list[tuple[Path, int, int]] = []
    current_sector = 0
    for path in paths:
        sector_count = path.stat().st_size // sector_size
        start = current_sector
        end = current_sector + sector_count - 1
        mappings.append((path, start, end))
        current_sector += sector_count
    return mappings


def _collect_entry_sector_ranges(
    entry_id: str, menu_entries: dict[str, object], nav: NavigationModel
) -> list[tuple[int, int]] | None:
    entry = menu_entries.get(entry_id)
    if entry is None or nav.dvd is None:
        return None
    target = entry.target
    if target.kind not in {"dvd_pgc", "dvd_cell"}:
        return None
    title = next((t for t in nav.dvd.titles if t.title_id == target.title_id), None)
    if title is None:
        return None
    if target.kind == "dvd_pgc":
        pgc = next((p for p in title.pgcs if p.pgc_id == target.pgc_id), None)
        if pgc is None:
            return None
        ranges: list[tuple[int, int]] = []
        for cell in pgc.cells:
            if cell.first_sector is None or cell.last_sector is None:
                return None
            ranges.append((cell.first_sector, cell.last_sector))
        return ranges
    pgc = next((p for p in title.pgcs if p.pgc_id == target.pgc_id), None)
    if pgc is None:
        return None
    cell = next((c for c in pgc.cells if c.cell_id == target.cell_id), None)
    if cell is None or cell.first_sector is None or cell.last_sector is None:
        return None
    return [(cell.first_sector, cell.last_sector)]


def _write_sector_ranges(
    output_path: Path,
    vob_paths: list[Path],
    sector_ranges: list[tuple[int, int]],
) -> None:
    sector_size = 2048
    mappings = _build_vob_sector_map(vob_paths)
    chunk_size = 4 * 1024 * 1024
    with output_path.open("wb") as out_handle:
        for range_start, range_end in sector_ranges:
            if range_end < range_start:
                continue
            for path, file_start, file_end in mappings:
                overlap_start = max(range_start, file_start)
                overlap_end = min(range_end, file_end)
                if overlap_end < overlap_start:
                    continue
                offset_sectors = overlap_start - file_start
                length_sectors = overlap_end - overlap_start + 1
                bytes_to_read = length_sectors * sector_size
                with path.open("rb") as in_handle:
                    in_handle.seek(offset_sectors * sector_size)
                    remaining = bytes_to_read
                    while remaining > 0:
                        chunk = in_handle.read(min(chunk_size, remaining))
                        if not chunk:
                            break
                        out_handle.write(chunk)
                        remaining -= len(chunk)


def _build_slices(
    segment: SegmentEntryModel,
    source: EntrySource,
) -> list[tuple[Path, float, float]]:
    start = segment.start_time
    end = segment.end_time
    slices: list[tuple[Path, float, float]] = []
    for path, duration, offset in zip(source.paths, source.durations, source.offsets):
        file_start = offset
        file_end = offset + duration
        if file_end <= start:
            continue
        slice_start = max(0.0, start - file_start)
        slice_end = min(duration, end - file_start)
        slice_duration = slice_end - slice_start
        if slice_duration <= 0:
            continue
        slices.append((path, slice_start, slice_duration))
        if end <= file_end:
            break
    if not slices:
        raise ValidationError(
            f"segment {segment.entry_id} is outside the duration of its source files"
        )
    return slices


def _run_ffmpeg_command(command: list[str], log_messages: list[str]) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    log_messages.append(f"ffmpeg command: {' '.join(command)}")
    log_messages.append(f"exit_code: {completed.returncode}")
    log_messages.append(f"stdout:\n{completed.stdout}")
    log_messages.append(f"stderr:\n{completed.stderr}")
    return completed


def run(
    segments_path: Path,
    ingest_path: Path,
    menu_map_path: Path,
    out_dir: Path,
    use_real_ffmpeg: bool,
    repair: str,
) -> ExtractModel:
    if repair not in {"off", "safe"}:
        raise ValidationError("repair must be one of: off, safe")

    segments = read_json(segments_path, SegmentsModel)
    ingest = read_json(ingest_path, IngestModel)
    menu_map = read_json(menu_map_path, MenuMapModel)
    nav_path = out_dir / "nav.json"
    nav = read_json(nav_path, NavigationModel) if nav_path.is_file() else None

    episodes_dir = out_dir / "episodes"
    logs_dir = out_dir / "logs"
    temp_dir = episodes_dir / "_tmp"
    episodes_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    source_by_entry: dict[str, EntrySource] = {}
    if use_real_ffmpeg:
        track_files = ingest.disc_report.video_track_files
        if not track_files:
            raise ValidationError("No video track files available for extraction")

        menu_entries = menu_map.entries
        menu_entries_by_id = {entry.entry_id: entry for entry in menu_entries}
        segments_by_entry = {segment.entry_id: segment for segment in segments.segments}
        duration_cache: dict[Path, float] = {}
        vobs_by_title: dict[int, list[Path]] = {}
        if ingest.disc_report.disc_format == "DVD":
            vobs = [Path(path) for path in track_files if path.upper().endswith(".VOB")]
            by_title: dict[int, list[Path]] = {}
            for path in vobs:
                parts = path.name.split("_")
                if len(parts) >= 2 and parts[1].isdigit():
                    title_id = int(parts[1])
                    by_title.setdefault(title_id, []).append(path)
            for title_id, paths in by_title.items():
                by_title[title_id] = sorted(paths)
                vobs_by_title[title_id] = by_title[title_id]
            title_sources: dict[int, EntrySource] = {}
            title_durations: dict[int, float] = {}
            for entry in menu_entries:
                if entry.target.kind not in {"dvd_pgc", "dvd_cell"}:
                    continue
                if entry.target.title_id is None:
                    continue
                segment = segments_by_entry.get(entry.entry_id)
                if segment is None:
                    continue
                title_durations[entry.target.title_id] = title_durations.get(
                    entry.target.title_id, 0.0
                ) + (segment.end_time - segment.start_time)

            title_sector_ranges: dict[int, tuple[int, int]] = {}
            if nav is not None and nav.dvd is not None:
                for title in nav.dvd.titles:
                    sector_min: int | None = None
                    sector_max: int | None = None
                    for pgc in title.pgcs:
                        for cell in pgc.cells:
                            if cell.first_sector is None or cell.last_sector is None:
                                continue
                            sector_min = (
                                cell.first_sector
                                if sector_min is None
                                else min(sector_min, cell.first_sector)
                            )
                            sector_max = (
                                cell.last_sector
                                if sector_max is None
                                else max(sector_max, cell.last_sector)
                            )
                    if sector_min is not None and sector_max is not None:
                        title_sector_ranges[title.title_id] = (sector_min, sector_max)

            for title_id, paths in by_title.items():
                total_duration = title_durations.get(title_id, 0.0)
                sector_range = title_sector_ranges.get(title_id)
                if total_duration > 0 and sector_range is not None:
                    title_sources[title_id] = _build_entry_source_by_sectors(
                        paths,
                        total_duration,
                        sector_range[0],
                        sector_range[1],
                    )
                elif total_duration > 0:
                    title_sources[title_id] = _build_entry_source_by_size(
                        paths, total_duration
                    )
                else:
                    title_sources[title_id] = _build_entry_source(paths, duration_cache)

            for entry in menu_entries:
                if entry.target.kind not in {"dvd_pgc", "dvd_cell"}:
                    raise ValidationError("DVD extraction requires dvd_pgc/dvd_cell targets")
                if entry.target.title_id is None:
                    raise ValidationError("DVD extraction requires target.title_id")
                title_source = title_sources.get(entry.target.title_id)
                if title_source is None:
                    raise ValidationError(
                        f"No VOBs found for title {entry.target.title_id}"
                    )
                source_by_entry[entry.entry_id] = title_source
        else:
            if len(track_files) == 1:
                shared_source = _build_entry_source(
                    [Path(track_files[0])], duration_cache
                )
                source_by_entry = {
                    entry.entry_id: shared_source for entry in menu_entries
                }
            elif len(track_files) == len(menu_entries):
                source_by_entry = {
                    entry.entry_id: _build_entry_source([Path(path)], duration_cache)
                    for entry, path in zip(menu_entries, track_files, strict=False)
                }
            else:
                raise ValidationError(
                    "ffmpeg extraction requires either 1 source file or one per menu entry"
                )

        for source in source_by_entry.values():
            for path in source.paths:
                if not path.is_file():
                    raise ValidationError(f"Missing source file for extraction: {path}")

    outputs: list[ExtractEntryModel] = []
    for segment in segments.segments:
        filename = f"{segment.entry_id}.mkv"
        output_path = episodes_dir / filename
        assert_in_out_dir(output_path, out_dir)

        log_path = logs_dir / f"{segment.entry_id}.log"
        assert_in_out_dir(log_path, out_dir)
        print(f"  Starting {segment.entry_id}")
        if use_real_ffmpeg:
            source = source_by_entry.get(segment.entry_id)
            if source is None:
                raise ValidationError(
                    f"Missing source mapping for entry_id: {segment.entry_id}"
                )
            log_messages: list[str] = []
            sector_ranges: list[tuple[int, int]] | None = None
            if nav is not None and nav.dvd is not None:
                sector_ranges = _collect_entry_sector_ranges(
                    segment.entry_id, menu_entries_by_id, nav
                )
            if sector_ranges:
                entry = menu_entries_by_id.get(segment.entry_id)
                if entry is None or entry.target.title_id is None:
                    raise ValidationError("DVD sector slicing missing title_id")
                vob_paths = vobs_by_title.get(entry.target.title_id)
                if not vob_paths:
                    raise ValidationError(
                        f"No VOBs found for title {entry.target.title_id}"
                    )
                temp_path = temp_dir / f"{segment.entry_id}_sectors.vob"
                _write_sector_ranges(temp_path, vob_paths, sector_ranges)
                command = [
                    "ffmpeg",
                    "-hide_banner",
                    "-y",
                    "-fflags",
                    "+genpts",
                    "-err_detect",
                    "ignore_err",
                    "-probesize",
                    "100M",
                    "-analyzeduration",
                    "100M",
                    "-ignore_unknown",
                    "-copy_unknown",
                    "-avoid_negative_ts",
                    "make_zero",
                    "-i",
                    str(temp_path),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-map_metadata",
                    "0",
                    "-map_chapters",
                    "0",
                    "-c",
                    "copy",
                    "-start_at_zero",
                    "-max_interleave_delta",
                    "0",
                    str(output_path),
                ]
                completed = _run_ffmpeg_command(command, log_messages)
                if temp_path.exists():
                    temp_path.unlink()
                if completed.returncode != 0:
                    raise ValidationError(
                        f"ffmpeg extraction failed for {segment.entry_id}; see {log_path}"
                    )
                size = output_path.stat().st_size
                print(f"  Created file {output_path} of size {size}")
                log_path.write_text("\n".join(log_messages), encoding="utf-8")
                outputs.append(
                    ExtractEntryModel(
                        entry_id=segment.entry_id,
                        output_path=str(output_path),
                        status="ok",
                    )
                )
                continue
            slices = _build_slices(segment, source)
            slice_paths: list[Path] = []
            concat_list_path: Path | None = None
            status = "ok"
            try:
                if len(slices) == 1:
                    source_path, rel_start, duration = slices[0]
                    command = [
                        "ffmpeg",
                        "-hide_banner",
                        "-y",
                        "-ss",
                        f"{rel_start:.3f}",
                        "-fflags",
                        "+genpts",
                        "-err_detect",
                        "ignore_err",
                        "-probesize",
                        "100M",
                        "-analyzeduration",
                        "100M",
                        "-ignore_unknown",
                        "-copy_unknown",
                        "-avoid_negative_ts",
                        "make_zero",
                        "-i",
                        str(source_path),
                        "-t",
                        f"{duration:.3f}",
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a?",
                        "-map_metadata",
                        "0",
                        "-map_chapters",
                        "0",
                        "-c",
                        "copy",
                        "-start_at_zero",
                        "-max_interleave_delta",
                        "0",
                        str(output_path),
                    ]
                    completed = _run_ffmpeg_command(command, log_messages)
                    if completed.returncode != 0:
                        raise ValidationError(
                            f"ffmpeg extraction failed for {segment.entry_id}; see {log_path}"
                        )
                else:
                    for idx, (source_path, rel_start, duration) in enumerate(slices):
                        slice_path = logs_dir / f"{segment.entry_id}_slice_{idx}.ts"
                        command = [
                            "ffmpeg",
                            "-hide_banner",
                            "-y",
                            "-ss",
                            f"{rel_start:.3f}",
                            "-fflags",
                            "+genpts",
                            "-err_detect",
                            "ignore_err",
                            "-probesize",
                            "100M",
                            "-analyzeduration",
                            "100M",
                            "-ignore_unknown",
                            "-copy_unknown",
                            "-avoid_negative_ts",
                            "make_zero",
                            "-i",
                            str(source_path),
                            "-t",
                            f"{duration:.3f}",
                            "-map",
                            "0:v:0",
                            "-map",
                            "0:a?",
                            "-map_metadata",
                            "0",
                            "-map_chapters",
                            "0",
                            "-c",
                            "copy",
                            "-start_at_zero",
                            "-max_interleave_delta",
                            "0",
                            str(slice_path),
                        ]
                        completed = _run_ffmpeg_command(command, log_messages)
                        if completed.returncode != 0:
                            raise ValidationError(
                                f"ffmpeg extraction failed for {segment.entry_id}; see {log_path}"
                            )
                        slice_paths.append(slice_path)
                    concat_list_path = logs_dir / f"concat_{segment.entry_id}_parts.txt"
                    lines = "\n".join(
                        f"file '{path.resolve().as_posix()}'" for path in slice_paths
                    )
                    concat_list_path.write_text(lines + "\n", encoding="utf-8")
                    command = [
                        "ffmpeg",
                        "-hide_banner",
                        "-y",
                        "-fflags",
                        "+genpts",
                        "-err_detect",
                        "ignore_err",
                        "-probesize",
                        "100M",
                        "-analyzeduration",
                        "100M",
                        "-ignore_unknown",
                        "-copy_unknown",
                        "-avoid_negative_ts",
                        "make_zero",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(concat_list_path),
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a?",
                        "-map_metadata",
                        "0",
                        "-map_chapters",
                        "0",
                        "-c",
                        "copy",
                        "-start_at_zero",
                        "-max_interleave_delta",
                        "0",
                        str(output_path),
                    ]
                    completed = _run_ffmpeg_command(command, log_messages)
                    if completed.returncode != 0:
                        raise ValidationError(
                            f"ffmpeg extraction failed for {segment.entry_id}; see {log_path}"
                        )
            finally:
                for part in slice_paths:
                    if part.exists():
                        part.unlink()
                if concat_list_path and concat_list_path.exists():
                    concat_list_path.unlink()
                log_path.write_text(
                    "\n".join(log_messages),
                    encoding="utf-8",
                )
        else:
            output_path.write_bytes(b"")
            log_path.write_text(
                f"stub extract entry={segment.entry_id} repair={repair}\n",
                encoding="utf-8",
            )
            status = "stub"
        size = output_path.stat().st_size
        print(f"  Created file {output_path} of size {size}")
        outputs.append(
            ExtractEntryModel(
                entry_id=segment.entry_id,
                output_path=str(output_path),
                status=status,
            )
        )

    model = ExtractModel(outputs=outputs)
    write_json(out_dir / "extract.json", model)
    return model
