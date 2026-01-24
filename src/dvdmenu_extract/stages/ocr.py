from __future__ import annotations

from pathlib import Path
from typing import Optional

from dvdmenu_extract.models.menu import MenuImagesModel
from dvdmenu_extract.models.ocr import OcrEntryModel, OcrModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.fixtures import menu_buttons_dir
from dvdmenu_extract.util.io import read_json, write_json
from dvdmenu_extract.util.paths import sanitize_filename


def _run_stub(menu_images: MenuImagesModel) -> OcrModel:
    entries: list[OcrEntryModel] = []
    for image in menu_images.images:
        txt_path = menu_buttons_dir() / f"{image.entry_id}.txt"
        if txt_path.is_file():
            raw_text = txt_path.read_text(encoding="utf-8-sig").strip()
        else:
            if image.menu_id and image.menu_id.startswith("svcd"):
                raw_text = ""
            else:
                raise ValidationError(f"Missing OCR fixture: {txt_path}")
        spu_text_nonempty = raw_text != ""
        background_attempted = not spu_text_nonempty
        source = "spu" if spu_text_nonempty else "background"
        cleaned = (
            sanitize_filename(raw_text)
            if raw_text
            else sanitize_filename(f"untitled_{image.entry_id}")
        )
        entries.append(
            OcrEntryModel(
                entry_id=image.entry_id,
                raw_text=raw_text,
                cleaned_label=cleaned,
                confidence=0.9,
                source=source,
                background_attempted=background_attempted,
                spu_text_nonempty=spu_text_nonempty,
            )
        )
    return OcrModel(results=entries)


def _run_real(menu_images: MenuImagesModel, ocr_lang: str) -> OcrModel:
    try:
        import pytesseract
        from PIL import Image
    except Exception as exc:  # pragma: no cover - depends on external env
        raise ValidationError(
            "Real OCR requested but pytesseract/Pillow not available"
        ) from exc

    entries: list[OcrEntryModel] = []
    for image in menu_images.images:
        image_path = Path(image.image_path)
        if not image_path.is_file():
            raise ValidationError(f"Missing menu image for OCR: {image_path}")
        raw_text = pytesseract.image_to_string(
            Image.open(image_path), lang=ocr_lang
        ).strip()
        spu_text_nonempty = False
        background_attempted = True
        source = "background"
        cleaned = (
            sanitize_filename(raw_text)
            if raw_text
            else sanitize_filename(f"untitled_{image.entry_id}")
        )
        entries.append(
            OcrEntryModel(
                entry_id=image.entry_id,
                raw_text=raw_text,
                cleaned_label=cleaned,
                confidence=0.0,
                source=source,
                background_attempted=background_attempted,
                spu_text_nonempty=spu_text_nonempty,
            )
        )
    return OcrModel(results=entries)


def run(
    menu_images_path: Path,
    out_dir: Path,
    ocr_lang: str,
    use_real_ocr: bool,
) -> OcrModel:
    menu_images = read_json(menu_images_path, MenuImagesModel)
    model = _run_real(menu_images, ocr_lang) if use_real_ocr else _run_stub(menu_images)
    write_json(out_dir / "ocr.json", model)
    return model
