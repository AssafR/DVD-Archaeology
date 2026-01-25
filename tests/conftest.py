from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--reference-verbose",
        action="store_true",
        help="print verbose output for reference comparison tests",
    )
    parser.addoption(
        "--reference-skip-extract",
        action="store_true",
        help="skip running extract stage in reference comparison tests",
    )
