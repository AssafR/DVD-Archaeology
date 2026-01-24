from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Sequence

from dvdmenu_extract.util.assertx import ValidationError


@dataclass(frozen=True)
class ProcessResult:
    command: list[str]
    stdout: str
    stderr: str
    exit_code: int


def run_process(command: Sequence[str], timeout_sec: int = 30) -> ProcessResult:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValidationError(f"Tool not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValidationError(f"Command timed out: {' '.join(command)}") from exc

    result = ProcessResult(
        command=list(command),
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
    )
    if result.exit_code != 0:
        raise ValidationError(
            f"Command failed ({result.exit_code}): {' '.join(result.command)}"
        )
    return result
