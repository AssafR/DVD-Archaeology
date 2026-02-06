from __future__ import annotations

"""Stage E: ocr.

Performs dual-path OCR (SPU then background) on menu entry images. OCR is
used only for labeling and should not affect segmentation.
"""

from pathlib import Path
from typing import Optional
import logging
import re
from math import inf

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


def _text_quality_score(text: str) -> float:
    """
    Heuristic quality score for OCR output.
    
    Higher score = more alpha/number characters and fewer artifacts.
    Returns 0.0 for empty strings.
    """
    if not text:
        return 0.0
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?'-()")
    allowed_count = sum(1 for ch in text if ch in allowed)
    alpha_num_count = sum(ch.isalnum() for ch in text)
    length = len(text)
    return (allowed_count / length) * 0.6 + (alpha_num_count / length) * 0.4


def _make_color_dominant_mask(rgb_img):
    """
    Build a mask for the most chromatically dominant text-like hue on the image.
    
    This is color-agnostic (no hard-coded blue). It finds the hue with the
    highest weighted energy (saturation * value), then keeps pixels in that hue
    band that are both saturated and bright. Intended to capture SPU overlay
    glyphs rendered in a distinct color over textured backgrounds.
    
    Returns None if no meaningful dominant hue region is found.
    """
    from PIL import Image, ImageFilter

    hsv = rgb_img.convert("HSV")
    data = list(hsv.getdata())  # (h, s, v) 0-255

    # Build weighted hue histogram (weight = s * v)
    weights = [0] * 256
    for h, s, v in data:
        w = s * v
        if w:
            weights[h] += w

    # Find dominant hue
    dominant_hue = max(range(256), key=lambda i: weights[i])
    if weights[dominant_hue] == 0:
        return None

    # Build mask: pixels near dominant hue, sufficiently saturated/bright
    hue_band = 10  # +/- band around dominant hue
    mask_bytes = bytearray()
    count = 0
    sat_thresh = 80
    val_thresh = 80
    for h, s, v in data:
        dh = min((h - dominant_hue) % 256, (dominant_hue - h) % 256)
        if dh <= hue_band and s >= sat_thresh and v >= val_thresh:
            mask_bytes.append(255)
            count += 1
        else:
            mask_bytes.append(0)

    if count < 20:  # not enough pixels -> treat as no mask
        return None

    mask_pil = Image.frombytes("L", rgb_img.size, bytes(mask_bytes))
    # Smooth small gaps while keeping strokes thin
    mask_pil = mask_pil.filter(ImageFilter.MaxFilter(3))
    mask_pil = mask_pil.filter(ImageFilter.MinFilter(3))

    # Smooth small gaps while keeping strokes thin
    mask_pil = mask_pil.filter(ImageFilter.MaxFilter(3))
    mask_pil = mask_pil.filter(ImageFilter.MinFilter(3))
    return mask_pil


def _preprocess_for_tesseract(img, mask=None, *, scale: int = 2, thicken: bool = False):
    """
    Shared preprocessing used by both unmasked and masked passes.
    If mask is provided, non-mask areas are set to white before processing.
    """
    from PIL import ImageOps, ImageFilter, ImageStat, Image

    if mask is not None:
        # Use a mask-driven binary image: text where mask=1, white elsewhere.
        text_only = Image.new("L", img.size, 255)
        text_only.paste(0, mask=mask)
        img = text_only
    else:
        img = img.convert("L")

    # Upscale (default 2x; masked path may use 3x)
    img = img.resize((img.width * scale, img.height * scale), Image.BICUBIC)

    # Optional text thickening for masked path to restore stroke weight
    if thicken:
        img = img.filter(ImageFilter.MaxFilter(3))

    # Contrast and sharpen
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=180, threshold=2))

    # Adaptive binarization
    mean = ImageStat.Stat(img).mean[0]
    threshold = max(120, min(200, mean + 20))
    img = img.point(lambda p: 255 if p > threshold else 0)
    return img


def _run_tesseract(img, ocr_lang: str, config: str):
    import pytesseract
    return pytesseract.image_to_string(img, lang=ocr_lang, config=config).strip()


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

        # Load image (keep RGB for color-aware masking)
        orig_rgb = Image.open(image_path).convert("RGB")
        
        # Primary path: existing grayscale pipeline
        img_primary = _preprocess_for_tesseract(orig_rgb, scale=2, thicken=False)

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
        
        raw_text_primary = _run_tesseract(img_primary, ocr_lang, config)
        if not raw_text_primary:
            config_fallback = "--psm 6 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|"
            raw_text_primary = _run_tesseract(img_primary, ocr_lang, config_fallback)
        raw_text_primary = _cleanup_ocr_text(raw_text_primary)

        # Secondary path: provided SPU mask (if present) to suppress background.
        raw_text_masked_spu = ""
        provided_mask = None
        if image.mask_path:
            mask_path = Path(image.mask_path)
            if mask_path.is_file():
                try:
                    provided_mask = Image.open(mask_path).convert("L")
                except Exception:
                    provided_mask = None
        if provided_mask is not None:
            img_masked_spu = _preprocess_for_tesseract(orig_rgb, mask=provided_mask, scale=3, thicken=True)
            masked_text = _run_tesseract(img_masked_spu, ocr_lang, config)
            if not masked_text:
                config_fallback = "--psm 6 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|"
                masked_text = _run_tesseract(img_masked_spu, ocr_lang, config_fallback)
            raw_text_masked_spu = _cleanup_ocr_text(masked_text)

        # Tertiary path: color-aware dominant-hue mask to suppress textured backgrounds.
        raw_text_masked_hue = ""
        mask = _make_color_dominant_mask(orig_rgb)
        if mask is not None:
            img_masked = _preprocess_for_tesseract(orig_rgb, mask=mask, scale=3, thicken=True)
            masked_text = _run_tesseract(img_masked, ocr_lang, config)
            if not masked_text:
                config_fallback = "--psm 6 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|"
                masked_text = _run_tesseract(img_masked, ocr_lang, config_fallback)
            raw_text_masked_hue = _cleanup_ocr_text(masked_text)

        # Choose best candidate:
        # 1) If SPU-derived text exists, prefer it (authoritative overlay).
        # 2) Else, pick hue-masked if it improves quality over primary.
        # 3) Else, fallback to primary.
        chosen_text = raw_text_primary
        chosen_source = "primary"

        if raw_text_masked_spu:
            chosen_text = raw_text_masked_spu
            chosen_source = "spu"
        elif raw_text_masked_hue:
            hue_score = _text_quality_score(raw_text_masked_hue)
            primary_score = _text_quality_score(raw_text_primary)
            if hue_score > primary_score + 0.01:
                chosen_text = raw_text_masked_hue
                chosen_source = "hue"

        raw_text = chosen_text
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
