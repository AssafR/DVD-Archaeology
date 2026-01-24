from __future__ import annotations

import json
from pathlib import Path


def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def expected_dir() -> Path:
    return fixtures_dir() / "expected"


def load_expected_json(name: str) -> dict:
    path = expected_dir() / name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
