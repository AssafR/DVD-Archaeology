from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dvdmenu_extract.models.enums import DiscFormat


@dataclass(frozen=True)
class SampleSpec:
    path: Path
    expected_tracks: int | None = None
    count_globs: list[str] | None = None


SAMPLE_PATHS: dict[DiscFormat, list[SampleSpec]] = {
    DiscFormat.DVD: [
        SampleSpec(Path("DVD_Sample_01"), expected_tracks=3),
        SampleSpec(Path("DVD_Sample_02"), expected_tracks=1),
        SampleSpec(
            Path(r"Q:\DVDs\UglyBetty_s01b"),
            expected_tracks=4,
            count_globs=[
                "VIDEO_TS/VTS_01_[1-9].VOB",
                "VIDEO_TS/VTS_01_[1-9].MKV",
            ],
        ),
    ],
    DiscFormat.SVCD: [
        SampleSpec(Path(r"Q:\Old_Discs\0008 - SNL Steve Buscemi 1997 - CD"), expected_tracks=11),
    ],
    DiscFormat.VCD: [
        SampleSpec(Path(r"S:\TV Shows\MadTV\0368 - Mad TV collection 7 - CD"), expected_tracks=27),
    ],
}
