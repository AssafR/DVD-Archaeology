from __future__ import annotations

"""Stage E: ocr.

Performs dual-path OCR (SPU then background) on menu entry images. OCR is
used only for labeling and should not affect segmentation.
"""

from pathlib import Path
from typing import Optional
import logging
import re

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
        raw_text = _cleanup_ocr_text(raw_text)
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
        from PIL import Image, ImageOps, ImageFilter, ImageStat
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

        # OCR Preprocessing Pipeline for DVD Menu Text
        # =============================================
        # This multi-stage preprocessing optimizes small, low-contrast DVD menu text
        # for Tesseract OCR. Each step addresses specific OCR challenges.
        
        # 1. GRAYSCALE CONVERSION
        # Convert to single-channel grayscale for consistent processing
        img = img.convert("L")
        
        # 2. UPSCALING (2x Magnification via Bicubic Interpolation)
        # Rationale: DVD menu text is typically small (12-16px). Tesseract performs
        # better on larger text (30-40px). 2x upscaling provides optimal balance:
        # - Improves character recognition for small fonts
        # - Preserves character edges without over-sharpening artifacts
        # - Faster than 3x/4x while maintaining accuracy
        # Testing Note: 3x magnification was tested but caused regressions
        # (breaking up "C370" → "C 3/0", "77" → "17"). 2x is the sweet spot.
        img = img.resize((img.width * 2, img.height * 2), Image.BICUBIC)
        
        # 3. AUTO CONTRAST ENHANCEMENT
        # Normalize brightness range to maximize text/background contrast
        img = ImageOps.autocontrast(img)
        
        # 4. UNSHARP MASKING (Edge Sharpening)
        # Enhances character edges for clearer recognition
        # - radius=1.2: Small radius for fine detail
        # - percent=180: Strong sharpening (180% of edge difference)
        # - threshold=2: Apply to all but nearly-flat regions
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=180, threshold=2))
        
        # 5. ADAPTIVE BINARIZATION (Black & White Thresholding)
        # Convert to pure black text on white background for optimal OCR
        # Threshold calculation: mean brightness + 20, clamped to [120, 200]
        # This adapts to varying menu background brightness levels
        mean = ImageStat.Stat(img).mean[0]
        threshold = max(120, min(200, mean + 20))
        img = img.point(lambda p: 255 if p > threshold else 0)

        # Tesseract OCR Configuration
        # ============================
        # --psm 7: Page Segmentation Mode 7 (Treat as single text line)
        #   DVD menu buttons typically contain one line of text. This mode
        #   prevents Tesseract from attempting multi-line detection which
        #   can cause word splitting or incorrect ordering.
        #
        # -c preserve_interword_spaces=1: Preserve spacing between words
        #   Critical for maintaining proper spacing in dates and titles
        #   (e.g., "16 Oct 96" not "16Oct96")
        #
        # -c tessedit_char_blacklist=|: Exclude "|" character from recognition
        #   DVD menus often have vertical lines/separators that Tesseract
        #   incorrectly interprets as "|" at line ends. Blacklisting this
        #   character prevents spurious trailing "|" in OCR output.
        #   Testing: Successfully removed "|" artifact from all buttons with
        #   no negative side effects.
        config = "--psm 7 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|"
        
        raw_text = pytesseract.image_to_string(
            img, lang=ocr_lang, config=config
        ).strip()
        
        # Fallback: If PSM 7 produces empty result, try PSM 6
        # PSM 6 (uniform text block) is more lenient and may succeed where
        # PSM 7's strict single-line mode fails (e.g., unexpected layouts)
        if not raw_text:
            config = "--psm 6 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|"
            raw_text = pytesseract.image_to_string(
                img, lang=ocr_lang, config=config
            ).strip()
        raw_text = _cleanup_ocr_text(raw_text)
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


def _cleanup_ocr_text(text: str) -> str:
    """Normalize OCR output by restoring common missing spaces."""
    if not text:
        return text
    cleaned = text.replace("\t", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"(\d)([A-Za-z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([A-Za-z])(\d)", r"\1 \2", cleaned)
    # Collapse spaced month abbreviations (e.g., "O ct" -> "Oct").
    month_fixes = {
        r"\bJ\s*a\s*n\b": "Jan",
        r"\bF\s*e\s*b\b": "Feb",
        r"\bM\s*a\s*r\b": "Mar",
        r"\bA\s*p\s*r\b": "Apr",
        r"\bM\s*a\s*y\b": "May",
        r"\bJ\s*u\s*n\b": "Jun",
        r"\bJ\s*u\s*l\b": "Jul",
        r"\bA\s*u\s*g\b": "Aug",
        r"\bS\s*e\s*p\b": "Sep",
        r"\bO\s*c\s*t\b": "Oct",
        r"\bO\s*0\s*c\s*t\b": "Oct",
        r"\bN\s*o\s*v\b": "Nov",
        r"\bD\s*e\s*c\b": "Dec",
    }
    for pattern, replacement in month_fixes.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    # Join common code patterns like "C 366" -> "C366".
    cleaned = re.sub(r"\b([A-Za-z])\s+(\d{2,4})\b", r"\1\2", cleaned)
    # Replace slashes used between day/month (e.g., "2/Nov" -> "2 Nov").
    cleaned = re.sub(r"\b(\d{1,2})\s*/\s*([A-Za-z]{3})\b", r"\1 \2", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
