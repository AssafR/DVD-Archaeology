"""
Evaluate OCR preprocessing variants across all OCR regression datasets.

This script runs the dvdmenu-extract pipeline up to OCR for each dataset
in tests/fixtures/ocr_regression, then re-OCRs the cropped button images
with multiple preprocessing variants (primary, hue, several SPU modes,
and blend). It reports per-variant similarity stats against the dataset
ground truth so we can choose heuristics that don't regress any disc.

Usage:
    uv run python tools/ocr_variant_eval.py

Notes:
- Requires source paths in each dataset to exist (primary or backup).
- Writes temporary outputs under a temp directory; removes when done.
- Does not modify baselines; read-only evaluation.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import difflib
import sys

from dvdmenu_extract.models.menu import MenuImagesModel
from dvdmenu_extract.stages import ocr as ocr_stage
import pytesseract
from PIL import Image, ImageChops

# Ensure tesseract is configured
TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if TESSERACT_EXE.is_file():
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
else:
    print(
        "WARNING: Tesseract not found at expected path "
        f"({TESSERACT_EXE}). Ensure it is installed or adjust TESSERACT_EXE.",
        file=sys.stderr,
    )

DATASETS_DIR = Path("tests/fixtures/ocr_regression")


def discover_datasets() -> List[Path]:
    return sorted(
        p
        for p in DATASETS_DIR.glob("*.json")
        if p.stem not in {"dataset_schema", "README"}
    )


def load_dataset(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_available_source(dataset: dict) -> Path | None:
    source_paths = dataset.get("source_paths", {})
    primary = source_paths.get("primary")
    backup = source_paths.get("backup")
    for cand in [primary, backup]:
        if cand and Path(cand).exists():
            return Path(cand)
    return None


def run_pipeline(source: Path, out_dir: Path) -> None:
    cmd = [
        "uv",
        "run",
        "dvdmenu-extract",
        str(source),
        "--out",
        str(out_dir),
        "--until",
        "ocr",
        "--use-real-ffmpeg",
        "--overwrite-outputs",
        "--force",
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Pipeline failed for {source} (exit {result.returncode}):\n{result.stderr}"
        )


def text_similarity(a: str, b: str) -> float:
    na = ocr_stage._cleanup_ocr_text(a)
    nb = ocr_stage._cleanup_ocr_text(b)
    return difflib.SequenceMatcher(None, na, nb).ratio()


def make_hue_mask(rgb_img):
    return ocr_stage._make_color_dominant_mask(rgb_img)


@dataclass
class Variant:
    name: str
    fn: Callable[[Path, Path], str]


def variant_primary(rgb_path: Path, mask_path: Path | None) -> str:
    img = Image.open(rgb_path).convert("RGB")
    img_proc = ocr_stage._preprocess_for_tesseract(
        img,
        scale=2,
        thicken=False,
        threshold_bias=20,
    )
    return ocr_stage._cleanup_ocr_text(
        ocr_stage._run_tesseract(
            img_proc,
            "eng",
            "--psm 7 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|",
        )
    )


def variant_hue(rgb_path: Path, mask_path: Path | None) -> str:
    img = Image.open(rgb_path).convert("RGB")
    mask = make_hue_mask(img)
    if mask is None:
        return ""
    img_proc = ocr_stage._preprocess_for_tesseract(
        img,
        mask=mask,
        scale=3,
        thicken=True,
        threshold_bias=20,
    )
    return ocr_stage._cleanup_ocr_text(
        ocr_stage._run_tesseract(
            img_proc,
            "eng",
            "--psm 7 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|",
        )
    )


def variant_spu(rgb_path: Path, mask_path: Path | None, *, bias: int, strong: bool) -> str:
    if not mask_path or not Path(mask_path).is_file():
        return ""
    img = Image.open(rgb_path).convert("RGB")
    mask = Image.open(mask_path).convert("L")
    img_proc = ocr_stage._preprocess_for_tesseract(
        img,
        mask=mask,
        scale=3,
        thicken=True,
        threshold_bias=bias,
        extra_maxfilter=strong,
    )
    return ocr_stage._cleanup_ocr_text(
        ocr_stage._run_tesseract(
            img_proc,
            "eng",
            "--psm 7 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|",
        )
    )


def variant_blend(rgb_path: Path, mask_path: Path | None) -> str:
    if not mask_path or not Path(mask_path).is_file():
        return ""
    mask = Image.open(mask_path).convert("L")
    img = Image.open(rgb_path).convert("RGB")
    base = ocr_stage._preprocess_for_tesseract(
        img, scale=2, thicken=False, threshold_bias=20
    )
    blend = ImageChops.add(
        mask.resize(base.size).point(lambda p: int(p * 0.8)),
        base.point(lambda p: int(p * 0.2)),
    )
    blend_proc = ocr_stage._preprocess_for_tesseract(
        blend.convert("RGB"), scale=1, thicken=False, threshold_bias=15
    )
    return ocr_stage._cleanup_ocr_text(
        ocr_stage._run_tesseract(
            blend_proc,
            "eng",
            "--psm 7 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|",
        )
    )


VARIANTS: List[Variant] = [
    Variant("primary", lambda rgb, mask: variant_primary(rgb, mask)),
    Variant("hue", lambda rgb, mask: variant_hue(rgb, mask)),
    Variant("spu_soft", lambda rgb, mask: variant_spu(rgb, mask, bias=12, strong=False)),
    Variant("spu_normal", lambda rgb, mask: variant_spu(rgb, mask, bias=10, strong=False)),
    Variant("spu_strong", lambda rgb, mask: variant_spu(rgb, mask, bias=8, strong=True)),
    Variant("blend", lambda rgb, mask: variant_blend(rgb, mask)),
]


def evaluate_dataset(dataset_path: Path) -> dict:
    dataset = load_dataset(dataset_path)
    source = find_available_source(dataset)
    if not source:
        return {"dataset": dataset["disc_name"], "status": "skipped", "reason": "no source"}

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        run_pipeline(source, out_dir)
        menu_images_path = out_dir / "menu_images.json"
        if not menu_images_path.exists():
            return {"dataset": dataset["disc_name"], "status": "failed", "reason": "menu_images missing"}

        menu_images = ocr_stage.read_json(menu_images_path, MenuImagesModel)
        expected_map = {e["entry_id"]: e["raw_text"] for e in dataset["expected_results"]}

        # Gather per-button results
        per_button: Dict[str, Dict[str, dict]] = {}
        for img in menu_images.images:
            if img.entry_id not in expected_map:
                continue
            expected = expected_map[img.entry_id]
            per_button[img.entry_id] = {}
            for variant in VARIANTS:
                text = variant.fn(Path(img.image_path), img.mask_path)
                sim = text_similarity(expected, text) if text else 0.0
                quality = ocr_stage._text_quality_score(text)
                per_button[img.entry_id][variant.name] = {
                    "sim": sim,
                    "quality": quality,
                    "len": len(text),
                    "text": text,
                }

        # Aggregate variant stats
        variant_stats: Dict[str, Dict[str, float]] = {}
        for variant in VARIANTS:
            sims = [per_button[b][variant.name]["sim"] for b in per_button]
            if not sims:
                continue
            variant_stats[variant.name] = {
                "min": min(sims),
                "avg": sum(sims) / len(sims),
                "count": len(sims),
            }

        def _best_per_button_sim(data: dict[str, dict[str, dict]]):
            picks = {}
            for btn, variants in data.items():
                best = max(
                    variants.items(),
                    key=lambda kv: (kv[1]["sim"], kv[1]["len"]),
                )
                picks[btn] = best
            return picks

        def _margin_primary(data: dict[str, dict[str, dict]], margin: float = 0.01):
            picks = {}
            for btn, variants in data.items():
                primary = variants.get("primary", {"sim": 0.0, "len": 0})
                best = ("primary", primary)
                for name, vals in variants.items():
                    if name == "hue":
                        continue  # hue performed poorly; ignore
                    if vals["sim"] > primary["sim"] + margin:
                        if (
                            vals["sim"] > best[1]["sim"]
                            or (
                                vals["sim"] == best[1]["sim"]
                                and vals["len"] > best[1]["len"]
                            )
                        ):
                            best = (name, vals)
                picks[btn] = best
            return picks

        strategy_best = _best_per_button_sim(per_button)
        strategy_margin = _margin_primary(per_button, margin=0.01)

        def _strategy_stats(picks: dict[str, tuple[str, dict]]) -> dict[str, float]:
            sims = [v[1]["sim"] for v in picks.values()]
            return {
                "min": min(sims) if sims else 0.0,
                "avg": sum(sims) / len(sims) if sims else 0.0,
                "count": len(sims),
            }

        return {
            "dataset": dataset["disc_name"],
            "status": "ok",
            "per_button": per_button,
            "variant_stats": variant_stats,
            "strategy_best_stats": _strategy_stats(strategy_best),
            "strategy_margin_stats": _strategy_stats(strategy_margin),
            "strategy_best_picks": {b: v[0] for b, v in strategy_best.items()},
            "strategy_margin_picks": {b: v[0] for b, v in strategy_margin.items()},
        }


def main() -> None:
    results = []
    for ds in discover_datasets():
        try:
            res = evaluate_dataset(ds)
        except Exception as exc:
            res = {"dataset": ds.stem, "status": "error", "reason": str(exc)}
        results.append(res)

    # Report
    print("# OCR Variant Evaluation\n")
    for res in results:
        print(f"## {res.get('dataset')}")
        print(f"Status: {res.get('status')}")
        if res.get("status") != "ok":
            print(f"Reason: {res.get('reason','')}\n")
            continue
        print("\nVariant stats (min/avg):")
        for v, stats in res["variant_stats"].items():
            print(f"- {v}: min={stats['min']:.3f}, avg={stats['avg']:.3f} (n={stats['count']})")
        print("\nStrategy stats:")
        print(
            f"- best_per_button: min={res['strategy_best_stats']['min']:.3f}, "
            f"avg={res['strategy_best_stats']['avg']:.3f}"
        )
        print(
            f"- margin_primary(+0.01): min={res['strategy_margin_stats']['min']:.3f}, "
            f"avg={res['strategy_margin_stats']['avg']:.3f}"
        )
        print("\nPer-button best (by sim):")
        for btn, sims in res["per_button"].items():
            best = max(
                sims.items(),
                key=lambda kv: (kv[1]["sim"], kv[1]["len"]),
            )
            print(f"- {btn}: {best[0]} ({best[1]['sim']:.3f})")
        print("\nPer-button picks (margin_primary):")
        for btn, pick in res["strategy_margin_picks"].items():
            print(f"- {btn}: {pick}")
        print()


if __name__ == "__main__":
    main()
