from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dvdmenu_extract.models.svcd_nav import SvcdEntryPoint, SvcdNavModel, SvcdTrack
from dvdmenu_extract.util.assertx import ValidationError, assert_in_out_dir
from dvdmenu_extract.util.process import ProcessResult, run_process
from dvdmenu_extract.util.io import write_json


@dataclass
class VcdImagerCliBackend:
    tool_name: str = "vcd-info"

    def run_vcd_info(self, input_path: Path) -> ProcessResult:
        return run_process([self.tool_name, str(input_path)])

    def parse_vcd_info(self, text: str) -> SvcdNavModel:
        tracks: list[SvcdTrack] = []
        entry_points: list[SvcdEntryPoint] = []

        for line in text.splitlines():
            track_match = re.search(r"Track\s+(\d+)\s*:\s*(AVSEQ\d+\.MPG)", line)
            if track_match:
                tracks.append(
                    SvcdTrack(
                        track_no=int(track_match.group(1)),
                        file_name=track_match.group(2),
                    )
                )
                continue
            entry_match = re.search(
                r"Entry\s+point\s*:\s*track\s+(\d+)\s+([0-9:]+)", line
            )
            if entry_match:
                entry_points.append(
                    SvcdEntryPoint(
                        track_no=int(entry_match.group(1)),
                        timecode=entry_match.group(2),
                    )
                )

        if not tracks:
            raise ValidationError("vcd-info output did not include any tracks")
        return SvcdNavModel(tracks=tracks, entry_points=entry_points)

    def build_svcd_nav(self, input_path: Path, out_dir: Path) -> SvcdNavModel:
        result = self.run_vcd_info(input_path)
        raw_dir = out_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = raw_dir / "vcd-info.stdout.txt"
        stderr_path = raw_dir / "vcd-info.stderr.txt"
        assert_in_out_dir(stdout_path, out_dir)
        assert_in_out_dir(stderr_path, out_dir)
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")

        svcd_nav = self.parse_vcd_info(result.stdout)
        write_json(out_dir / "svcd_nav.json", svcd_nav)
        return svcd_nav
