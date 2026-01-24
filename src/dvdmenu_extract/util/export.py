from __future__ import annotations

import shutil
from pathlib import Path

from dvdmenu_extract.util.assertx import assert_dir_exists


def export_json_artifacts(out_dir: Path, input_root: Path) -> None:
    assert_dir_exists(out_dir, "out_dir must exist before exporting JSON")
    assert_dir_exists(input_root, "input_root must exist before exporting JSON")

    target_root = input_root / "dvdmenu_extract_json"
    target_root.mkdir(parents=True, exist_ok=True)

    for json_path in out_dir.rglob("*.json"):
        if not json_path.is_file():
            continue
        rel_path = json_path.relative_to(out_dir)
        target_path = target_root / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(json_path, target_path)
