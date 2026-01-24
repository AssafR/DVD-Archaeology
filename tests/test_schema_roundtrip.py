from __future__ import annotations

from pathlib import Path

from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.nav import NavModel
from dvdmenu_extract.models.ocr import OcrModel
from dvdmenu_extract.models.segments import SegmentsModel
from dvdmenu_extract.util.io import read_json, write_json
from tests.helpers import load_expected_json


def test_schema_roundtrip_nav(tmp_path: Path) -> None:
    model = NavModel.model_validate(load_expected_json("nav.json"))
    write_json(tmp_path / "nav.json", model)
    roundtrip = read_json(tmp_path / "nav.json", NavModel)
    assert roundtrip.model_dump(mode="json") == model.model_dump(mode="json")


def test_schema_roundtrip_menu_map(tmp_path: Path) -> None:
    model = MenuMapModel.model_validate(load_expected_json("menu_map.json"))
    write_json(tmp_path / "menu_map.json", model)
    roundtrip = read_json(tmp_path / "menu_map.json", MenuMapModel)
    assert roundtrip.model_dump(mode="json") == model.model_dump(mode="json")


def test_schema_roundtrip_segments(tmp_path: Path) -> None:
    model = SegmentsModel.model_validate(load_expected_json("segments.json"))
    write_json(tmp_path / "segments.json", model)
    roundtrip = read_json(tmp_path / "segments.json", SegmentsModel)
    assert roundtrip.model_dump(mode="json") == model.model_dump(mode="json")


def test_schema_roundtrip_ocr(tmp_path: Path) -> None:
    model = OcrModel.model_validate(load_expected_json("ocr.json"))
    write_json(tmp_path / "ocr.json", model)
    roundtrip = read_json(tmp_path / "ocr.json", OcrModel)
    assert roundtrip.model_dump(mode="json") == model.model_dump(mode="json")
