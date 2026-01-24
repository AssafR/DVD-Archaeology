from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.backends.svcd_vcdimager import VcdImagerCliBackend
from dvdmenu_extract.models.svcd_nav import SvcdNavModel
from dvdmenu_extract.util.process import ProcessResult
from tests.helpers import expected_dir


def test_vcd_info_parser() -> None:
    sample = (expected_dir() / "vcd_info_sample.txt").read_text(encoding="utf-8")
    backend = VcdImagerCliBackend()
    nav = backend.parse_vcd_info(sample)
    assert isinstance(nav, SvcdNavModel)
    assert len(nav.tracks) == 2
    assert nav.tracks[0].track_no == 1
    assert nav.tracks[0].file_name == "AVSEQ01.MPG"
    assert len(nav.entry_points) == 2


def test_svcd_backend_writes_artifacts(tmp_path: Path) -> None:
    sample = (expected_dir() / "vcd_info_sample.txt").read_text(encoding="utf-8")
    backend = VcdImagerCliBackend()

    def fake_run(_input: Path) -> ProcessResult:
        return ProcessResult(
            command=["vcd-info", str(_input)],
            stdout=sample,
            stderr="stub stderr",
            exit_code=0,
        )

    backend.run_vcd_info = fake_run  # type: ignore[assignment]
    nav = backend.build_svcd_nav(Path("X:/dummy"), tmp_path)
    assert (tmp_path / "svcd_nav.json").is_file()
    assert (tmp_path / "raw" / "vcd-info.stdout.txt").is_file()
    assert (tmp_path / "raw" / "vcd-info.stderr.txt").is_file()
    assert len(nav.tracks) == 2
