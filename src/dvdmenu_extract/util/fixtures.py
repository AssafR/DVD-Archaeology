from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def fixtures_dir() -> Path:
    return repo_root() / "tests" / "fixtures"


def expected_dir() -> Path:
    return fixtures_dir() / "expected"


def menu_buttons_dir() -> Path:
    return fixtures_dir() / "menu_buttons"
