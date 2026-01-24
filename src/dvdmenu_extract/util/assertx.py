from __future__ import annotations

from pathlib import Path


class ValidationError(RuntimeError):
    pass


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def assert_file_exists(path: Path, message: str | None = None) -> None:
    if not path.is_file():
        raise ValidationError(message or f"Expected file to exist: {path}")


def assert_dir_exists(path: Path, message: str | None = None) -> None:
    if not path.is_dir():
        raise ValidationError(message or f"Expected directory to exist: {path}")


def assert_in_out_dir(path: Path, out_dir: Path) -> None:
    try:
        resolved = path.resolve()
        base = out_dir.resolve()
    except FileNotFoundError:
        resolved = path.absolute()
        base = out_dir.absolute()
    if base not in resolved.parents and resolved != base:
        raise ValidationError(f"Path must be inside out_dir: {path}")
