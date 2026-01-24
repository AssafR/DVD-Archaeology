from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.models.enums import DiscFormat


def list_video_tracks(input_path: Path, disc_format: DiscFormat) -> list[Path]:
    if disc_format == DiscFormat.DVD:
        video_ts = input_path / "VIDEO_TS"
        vobs = sorted(video_ts.glob("VTS_*_[1-9].VOB"))
        return vobs
    if disc_format == DiscFormat.SVCD:
        return sorted((input_path / "MPEG2").glob("AVSEQ*.MPG"))
    if disc_format == DiscFormat.VCD:
        return sorted((input_path / "MPEGAV").glob("AVSEQ*.DAT"))
    return []
