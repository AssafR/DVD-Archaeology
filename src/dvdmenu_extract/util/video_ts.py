from __future__ import annotations

from pathlib import Path
import re

from dvdmenu_extract.models.ingest import VideoTsFileEntry, VideoTsReport
from dvdmenu_extract.util.assertx import ValidationError, assert_dir_exists

_VTS_TITLE_RE = re.compile(r"^VTS_(\d{2})_0\.IFO$", re.IGNORECASE)


def build_video_ts_report(video_ts_dir: Path) -> VideoTsReport:
    assert_dir_exists(video_ts_dir, "VIDEO_TS directory is missing")

    required = {"VIDEO_TS.IFO", "VIDEO_TS.BUP", "VIDEO_TS.VOB"}
    present = {path.name.upper() for path in video_ts_dir.iterdir() if path.is_file()}
    missing = sorted(required - present)
    if missing:
        raise ValidationError(f"Missing required VIDEO_TS files: {missing}")

    files: list[VideoTsFileEntry] = []
    total_bytes = 0
    ifo_total = 0
    bup_total = 0
    vob_total = 0
    titles = set()

    for path in sorted(video_ts_dir.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue
        size = path.stat().st_size
        total_bytes += size
        suffix = path.suffix.upper()
        if suffix == ".IFO":
            ifo_total += size
        elif suffix == ".BUP":
            bup_total += size
        elif suffix == ".VOB":
            vob_total += size
        match = _VTS_TITLE_RE.match(path.name)
        if match:
            titles.add(match.group(1))
        files.append(VideoTsFileEntry(name=path.name, size_bytes=size))

    return VideoTsReport(
        file_count=len(files),
        total_bytes=total_bytes,
        vts_title_count=len(titles),
        ifo_total_bytes=ifo_total,
        bup_total_bytes=bup_total,
        vob_total_bytes=vob_total,
        files=files,
    )
