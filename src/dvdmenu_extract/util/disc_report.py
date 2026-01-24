from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.ingest import DiscFileEntry, DiscReport, VideoTsReport
from dvdmenu_extract.util.assertx import assert_dir_exists
from dvdmenu_extract.util.video_ts import build_video_ts_report
from dvdmenu_extract.util.video_tracks import list_video_tracks


def build_disc_report(input_path: Path) -> DiscReport:
    assert_dir_exists(input_path, "Input path must be an existing directory")

    video_ts_dir = input_path / "VIDEO_TS"
    mpeg2_dir = input_path / "MPEG2"

    files: list[DiscFileEntry] = []
    seen_paths: set[str] = set()
    directories: list[str] = []
    total_bytes = 0

    def add_files(directory: Path, patterns: list[str]) -> int:
        nonlocal total_bytes
        count = 0
        if not directory.is_dir():
            return 0
        directories.append(str(directory))
        for pattern in patterns:
            for path in sorted(directory.glob(pattern)):
                if not path.is_file():
                    continue
                key = str(path.resolve()).casefold()
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                size = path.stat().st_size
                total_bytes += size
                files.append(DiscFileEntry(path=str(path), size_bytes=size))
                count += 1
        return count

    video_ts_report: VideoTsReport | None = None
    mpeg2_count = None
    mpeg2_total = None
    mpegav_count = None
    mpegav_total = None

    svcd_dir = input_path / "SVCD"
    segment_dir = input_path / "SEGMENT"
    ext_dir = input_path / "EXT"

    vcd_dir = input_path / "VCD"
    mpegav_dir = input_path / "MPEGAV"

    if video_ts_dir.is_dir():
        video_ts_report = build_video_ts_report(video_ts_dir)
        add_files(video_ts_dir, ["*.IFO", "*.BUP", "*.VOB"])
        disc_format = DiscFormat.DVD
    elif (
        svcd_dir.is_dir()
        and (svcd_dir / "INFO.SVD").is_file()
        and (svcd_dir / "ENTRIES.SVD").is_file()
        and mpeg2_dir.is_dir()
    ):
        add_files(svcd_dir, ["*.SVD", "*.DAT"])
        add_files(segment_dir, ["*.MPG", "*.mpg"])
        add_files(ext_dir, ["*.DAT"])
        mpeg2_count = add_files(mpeg2_dir, ["*.MPG", "*.mpg"])
        mpeg2_total = sum(
            entry.size_bytes
            for entry in files
            if Path(entry.path).parent.name.upper() == "MPEG2"
        )
        disc_format = DiscFormat.SVCD
    elif (
        vcd_dir.is_dir()
        and (vcd_dir / "INFO.VCD").is_file()
        and (vcd_dir / "ENTRIES.VCD").is_file()
        and mpegav_dir.is_dir()
    ):
        add_files(vcd_dir, ["*.VCD", "*.DAT"])
        mpegav_count = add_files(mpegav_dir, ["*.DAT", "*.dat"])
        mpegav_total = sum(
            entry.size_bytes
            for entry in files
            if Path(entry.path).parent.name.upper() == "MPEGAV"
        )
        disc_format = DiscFormat.VCD
    else:
        disc_format = DiscFormat.UNKNOWN

    video_tracks = list_video_tracks(input_path, disc_format)
    return DiscReport(
        disc_format=disc_format,
        file_count=len(files),
        total_bytes=total_bytes,
        directories=directories,
        files=files,
        video_ts_report=video_ts_report,
        mpeg2_file_count=mpeg2_count,
        mpeg2_total_bytes=mpeg2_total,
        mpegav_file_count=mpegav_count,
        mpegav_total_bytes=mpegav_total,
        video_track_count=len(video_tracks),
        video_track_files=[str(path) for path in video_tracks],
    )
