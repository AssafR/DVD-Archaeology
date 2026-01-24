from __future__ import annotations

import re
from pathlib import Path


def sanitize_filename(label: str) -> str:
    cleaned = re.sub(r"[<>:\"/\\\\|?*]+", "", label)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = cleaned.strip("._")
    return cleaned or "untitled"


def ensure_inside_out_dir(path: Path, out_dir: Path) -> Path:
    resolved = path.resolve()
    base = out_dir.resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError(f"Path must be inside out_dir: {path}")
    return resolved
