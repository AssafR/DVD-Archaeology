from __future__ import annotations

import re
from pathlib import Path


def sanitize_filename(label: str, max_length: int = 120) -> str:
    cleaned = re.sub(r"[<>:\"/\\\\|?*]+", "", label)
    cleaned = re.sub(r"[\x00-\x1f]+", "", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = cleaned.strip("._")
    if max_length > 0 and len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("._")
    return cleaned or "untitled"


def ensure_inside_out_dir(path: Path, out_dir: Path) -> Path:
    resolved = path.resolve()
    base = out_dir.resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError(f"Path must be inside out_dir: {path}")
    return resolved
