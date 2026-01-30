from __future__ import annotations

"""Stage E: ocr.

Performs dual-path OCR (SPU then background) on menu entry images. OCR is
used only for labeling and should not affect segmentation.
"""

from pathlib import Path
from typing import Optional
import logging

from dvdmenu_extract.models.menu import MenuImagesModel
from dvdmenu_extract.models.ocr import OcrEntryModel, OcrModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.fixtures import menu_buttons_dir
from dvdmenu_extract.util.io import read_json, write_json
from dvdmenu_extract.util.paths import sanitize_filename


def _load_reference_lines(
    out_dir: Path, reference_path: Optional[Path]
) -> list[str] | None:
    resolved = reference_path or (out_dir / "ocr_reference.txt")
    if not resolved.is_file():
        return None
    lines = [
        line.strip()
        for line in resolved.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    return lines or None


def _run_stub(
    menu_images: MenuImagesModel, out_dir: Path, reference_path: Optional[Path]
) -> OcrModel:
    entries: list[OcrEntryModel] = []
    reference_lines = _load_reference_lines(out_dir, reference_path)
    use_reference = False
    if reference_lines:
        if len(reference_lines) != len(menu_images.images):
            raise ValidationError(
                "OCR reference line count must match menu entry count"
            )
        use_reference = True
    reference_iter = iter(reference_lines) if use_reference else None
    def _entry_sort_key(entry_id: str) -> int:
        digits = "".join(ch for ch in entry_id if ch.isdigit())
        return int(digits) if digits else 0
    ordered_images = sorted(
        menu_images.images, key=lambda img: _entry_sort_key(img.entry_id)
    )
    for image in ordered_images:
        logging.info("performing OCR on %s.png", image.entry_id)
        txt_path = menu_buttons_dir() / f"{image.entry_id}.txt"
        reference_used = False
        if txt_path.is_file():
            raw_text = txt_path.read_text(encoding="utf-8-sig").strip()
        elif reference_iter is not None:
            raw_text = next(reference_iter)
            reference_used = True
        else:
            if image.menu_id and (
                image.menu_id.startswith("svcd") or image.menu_id.startswith("vcd")
            ):
                raw_text = ""
            else:
                raw_text = ""
        if reference_used:
            spu_text_nonempty = False
            background_attempted = True
            source = "background"
        else:
            spu_text_nonempty = raw_text != ""
            background_attempted = not spu_text_nonempty
            source = "spu" if spu_text_nonempty else "background"
        logging.info("OCR Result: %s", raw_text)
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
        from PIL import Image, ImageOps
    except Exception as exc:  # pragma: no cover - depends on external env
        raise ValidationError(
            "Real OCR requested but pytesseract/Pillow not available"
        ) from exc

    entries: list[OcrEntryModel] = []
    def _entry_sort_key(entry_id: str) -> int:
        digits = "".join(ch for ch in entry_id if ch.isdigit())
        return int(digits) if digits else 0
    ordered_images = sorted(
        menu_images.images, key=lambda img: _entry_sort_key(img.entry_id)
    )
    for image in ordered_images:
        logging.info("performing OCR on %s", image.image_path)
        image_path = Path(image.image_path)
        if not image_path.is_file():
            raise ValidationError(f"Missing menu image for OCR: {image_path}")
        
        import pytesseract
        from PIL import Image
        
        # Ensure tesseract is in path or explicitly set
        # For this environment, we know it's at C:\Program Files\Tesseract-OCR\tesseract.exe
        tesseract_exe = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if Path(tesseract_exe).is_file():
            pytesseract.pytesseract.tesseract_cmd = tesseract_exe

        # Load image and perform OCR
        img = Image.open(image_path)
        
        # Basic preprocessing: grayscale + contrast + binarize
        img = ImageOps.autocontrast(img.convert("L"))
        img = img.point(lambda p: 255 if p > 140 else 0)
        
        # Tesseract config:
        # --psm 7: Treat the image as a single text line.
        # --psm 6: Assume a single uniform block of text.
        # Restrict to digits/dot to reduce confusions.
        whitelist = "-c tessedit_char_whitelist=0123456789.aA"
        config = f"--psm 7 {whitelist}"
        
        raw_text = pytesseract.image_to_string(
            img, lang=ocr_lang, config=config
        ).strip()
        
        # If empty with psm 7, try psm 6
        if not raw_text:
            config = f"--psm 6 {whitelist}"
            raw_text = pytesseract.image_to_string(
                img, lang=ocr_lang, config=config
            ).strip()
        logging.info("OCR Result: %s", raw_text)

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
    ocr_reference_path: Optional[Path] = None,
) -> OcrModel:
    menu_images = read_json(menu_images_path, MenuImagesModel)
    logging.info("Starting OCR stage")
    model = (
        _run_real(menu_images, ocr_lang)
        if use_real_ocr
        else _run_stub(menu_images, out_dir, ocr_reference_path)
    )
    write_json(out_dir / "ocr.json", model)
    logging.info("Finished OCR stage")
    return model
