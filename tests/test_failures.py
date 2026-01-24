from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.pipeline import PipelineOptions, run_pipeline
from dvdmenu_extract.util.assertx import ValidationError


def test_missing_upstream_artifact_raises(tmp_path: Path) -> None:
    options = PipelineOptions(
        ocr_lang="eng+heb",
        use_real_ocr=False,
        use_real_ffmpeg=False,
        repair="off",
        force=False,
    )
    with pytest.raises(ValidationError):
        run_pipeline(input_path=tmp_path, out_dir=tmp_path, options=options, stage="menu_map")


def test_duplicate_button_ids_rejected(tmp_path: Path) -> None:
    payload = {
        "menus": [
            {
                "menu_id": "menu_root",
                "buttons": [
                    {
                        "button_id": "btn1",
                        "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
                        "target": {"title_id": 1, "pgc_id": 1, "cell_id": 1},
                    },
                    {
                        "button_id": "btn1",
                        "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
                        "target": {"title_id": 1, "pgc_id": 1, "cell_id": 2},
                    },
                ],
            }
        ]
    }
    with pytest.raises(PydanticValidationError):
        MenuMapModel.model_validate(payload)


def test_negative_timestamps_rejected(tmp_path: Path) -> None:
    payload = {"segments": [{"button_id": "btn1", "start_time": -1.0, "end_time": 1.0}]}
    with pytest.raises(PydanticValidationError):
        SegmentsModel.model_validate(payload)
