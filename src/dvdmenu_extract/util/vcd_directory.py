from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.svcd_nav import SvcdEntryPoint, SvcdNavModel, SvcdTrack
from dvdmenu_extract.models.vcd_nav import VcdNavModel
from dvdmenu_extract.util.assertx import ValidationError


def _track_no_from_name(name: str, prefix: str) -> int | None:
    if not name.upper().startswith(prefix):
        return None
    digits = "".join(ch for ch in name[len(prefix) :] if ch.isdigit())
    return int(digits) if digits else None


def parse_svcd_directory(input_path: Path) -> SvcdNavModel:
    svcd_dir = input_path / "SVCD"
    mpeg2_dir = input_path / "MPEG2"
    if not (svcd_dir / "INFO.SVD").is_file() or not (svcd_dir / "ENTRIES.SVD").is_file():
        raise ValidationError("SVCD control files missing (INFO.SVD/ENTRIES.SVD)")
    if not mpeg2_dir.is_dir():
        raise ValidationError("SVCD MPEG2 directory missing")

    tracks: list[SvcdTrack] = []
    for path in sorted(mpeg2_dir.glob("AVSEQ*.MPG")):
        track_no = _track_no_from_name(path.name, "AVSEQ")
        if track_no is None:
            continue
        tracks.append(
            SvcdTrack(track_no=track_no, file_name=path.name, size_bytes=path.stat().st_size)
        )

    if not tracks:
        raise ValidationError("SVCD has no AVSEQ*.MPG tracks")

    control_files = {
        "info": True,
        "entries": True,
        "psd": (svcd_dir / "PSD.SVD").is_file(),
        "lot": (svcd_dir / "LOT.SVD").is_file(),
    }
    return SvcdNavModel(
        source="directory",
        control_files=control_files,
        tracks=tracks,
        entry_points=[],
    )


def parse_vcd_directory(input_path: Path) -> VcdNavModel:
    vcd_dir = input_path / "VCD"
    mpegav_dir = input_path / "MPEGAV"
    if not (vcd_dir / "INFO.VCD").is_file() or not (vcd_dir / "ENTRIES.VCD").is_file():
        raise ValidationError("VCD control files missing (INFO.VCD/ENTRIES.VCD)")
    if not mpegav_dir.is_dir():
        raise ValidationError("VCD MPEGAV directory missing")

    tracks: list[SvcdTrack] = []
    for path in sorted(mpegav_dir.glob("AVSEQ*.DAT")):
        track_no = _track_no_from_name(path.name, "AVSEQ")
        if track_no is None:
            continue
        tracks.append(
            SvcdTrack(track_no=track_no, file_name=path.name, size_bytes=path.stat().st_size)
        )

    if not tracks:
        raise ValidationError("VCD has no AVSEQ*.DAT tracks")

    control_files = {
        "info": True,
        "entries": True,
        "psd": (vcd_dir / "PSD.VCD").is_file(),
        "lot": (vcd_dir / "LOT.VCD").is_file(),
    }
    return VcdNavModel(
        source="directory",
        control_files=control_files,
        tracks=tracks,
        entry_points=[],
    )
