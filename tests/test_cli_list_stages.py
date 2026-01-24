from __future__ import annotations

from typer.testing import CliRunner

from dvdmenu_extract.cli import app
from dvdmenu_extract.pipeline import STAGES


def test_cli_list_stages() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--list-stages"])
    assert result.exit_code == 0
    assert result.output.strip().splitlines() == STAGES
