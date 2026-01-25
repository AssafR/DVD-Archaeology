from __future__ import annotations

"""Stage E: timing.

Resolves timing information from the NavigationModel into a simple list of
entry_id -> start/end timestamps. This stage should not rename or extract
media; it only produces timing.json for downstream segments/extract stages.
"""

from pathlib import Path

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.media import get_duration_seconds
from dvdmenu_extract.util.io import read_json, write_json, write_raw_json
import logging


def run(
    nav_path: Path,
    ingest_path: Path,
    menu_map_path: Path,
    out_dir: Path,
    use_real_timing: bool,
) -> SegmentsModel:
    nav = read_json(nav_path, NavigationModel)
    ingest = read_json(ingest_path, IngestModel)
    menu_map = read_json(menu_map_path, MenuMapModel)
    logger = logging.getLogger(__name__)

    if nav.disc_format == DiscFormat.DVD:
        if nav.dvd is None:
            raise ValidationError("DVD navigation missing dvd section")
        segments = []
        use_nav_timing = not use_real_timing
        if use_real_timing:
            if ingest.disc_report is None:
                raise ValidationError("disc_report required for real timing")
            vobs = [
                Path(path)
                for path in ingest.disc_report.video_track_files
                if path.upper().endswith(".VOB")
            ]
            if not vobs:
                raise ValidationError("No VOB files available for timing")
            if len(vobs) == len(menu_map.entries):
                logger.info("Timing: using ffprobe for %d VOBs", len(vobs))
                try:
                    durations = [get_duration_seconds(path) for path in vobs]
                except ValidationError as exc:
                    write_raw_json(
                        out_dir / "timing_meta.json",
                        {
                            "mode": "real",
                            "source": "ffprobe",
                            "status": "error",
                            "error": str(exc),
                            "files": [str(path) for path in vobs],
                        },
                    )
                    logger.error("Timing: ffprobe failed (%s)", exc)
                    raise
                cumulative = 0.0
                for entry, duration in zip(menu_map.entries, durations, strict=False):
                    entry_id = entry.entry_id
                    segments.append(
                        {
                            "entry_id": entry_id,
                            "start_time": cumulative,
                            "end_time": cumulative + duration,
                        }
                    )
                    cumulative += duration
                write_raw_json(
                    out_dir / "timing_meta.json",
                    {
                        "mode": "real",
                        "source": "ffprobe",
                        "status": "ok",
                        "files": [str(path) for path in vobs],
                    },
                )
            else:
                logger.warning(
                    "Timing: skipping ffprobe (VOBs=%d, menu entries=%d)",
                    len(vobs),
                    len(menu_map.entries),
                )
                write_raw_json(
                    out_dir / "timing_meta.json",
                    {
                        "mode": "real",
                        "source": "ifo",
                        "status": "skipped",
                        "reason": "vob_count_mismatch",
                        "files": [str(path) for path in vobs],
                    },
                )
                use_nav_timing = True
        if use_nav_timing:
            logger.info("Timing: using nav-based PGC timings")
            pgc_index = {}
            pgc_offsets: dict[tuple[int, int], float] = {}
            for title in nav.dvd.titles:
                cumulative = 0.0
                for pgc in sorted(title.pgcs, key=lambda item: item.pgc_id):
                    pgc_index[(title.title_id, pgc.pgc_id)] = pgc
                    pgc_offsets[(title.title_id, pgc.pgc_id)] = cumulative
                    pgc_duration = max(cell.end_time for cell in pgc.cells) - min(
                        cell.start_time for cell in pgc.cells
                    )
                    cumulative += pgc_duration
            for entry in menu_map.entries:
                if entry.target.kind == "dvd_pgc":
                    key = (entry.target.title_id, entry.target.pgc_id)
                    pgc = pgc_index.get(key)
                    if pgc is None:
                        raise ValidationError("menu entry references unknown PGC")
                    offset = pgc_offsets.get(key, 0.0)
                    start = offset + min(cell.start_time for cell in pgc.cells)
                    end = offset + max(cell.end_time for cell in pgc.cells)
                    segments.append(
                        {"entry_id": entry.entry_id, "start_time": start, "end_time": end}
                    )
                elif entry.target.kind == "dvd_cell":
                    pgc = pgc_index.get((entry.target.title_id, entry.target.pgc_id))
                    if pgc is None:
                        raise ValidationError("menu entry references unknown PGC")
                    offset = pgc_offsets.get(
                        (entry.target.title_id, entry.target.pgc_id), 0.0
                    )
                    cell = next(
                        (c for c in pgc.cells if c.cell_id == entry.target.cell_id), None
                    )
                    if cell is None:
                        raise ValidationError("menu entry references unknown cell")
                    segments.append(
                        {
                            "entry_id": entry.entry_id,
                            "start_time": offset + cell.start_time,
                            "end_time": offset + cell.end_time,
                        }
                    )
                else:
                    raise ValidationError("DVD timing requires dvd_pgc or dvd_cell targets")
            write_raw_json(
                out_dir / "timing_meta.json",
                {"mode": "ifo", "source": "nav", "status": "ok", "files": []},
            )
        model = SegmentsModel.model_validate({"segments": segments})
        write_json(out_dir / "timing.json", model)
        return model

    if nav.disc_format in {DiscFormat.SVCD, DiscFormat.VCD}:
        nav_tracks = []
        if nav.disc_format == DiscFormat.SVCD and nav.svcd is not None:
            nav_tracks = nav.svcd.tracks
        if nav.disc_format == DiscFormat.VCD and nav.vcd is not None:
            nav_tracks = nav.vcd.tracks
        segments = [
            {
                "entry_id": f"track_{track.track_no:02d}",
                "start_time": 0.0,
                "end_time": 600.0,
            }
            for track in nav_tracks
        ]
        write_raw_json(
            out_dir / "timing_meta.json",
            {"mode": "stub", "source": "nav", "status": "ok", "files": []},
        )
        model = SegmentsModel.model_validate({"segments": segments})
        write_json(out_dir / "timing.json", model)
        return model

    raise ValidationError("Timing stage does not support this disc format yet")
