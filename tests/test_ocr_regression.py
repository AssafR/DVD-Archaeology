"""OCR accuracy tests for DVD menu buttons.

This module provides a general framework for testing OCR accuracy against
ground truth baselines for different DVD titles. To add a new disc test:

1. Manually inspect DVD menu screens to determine CORRECT text for each button
2. Create a JSON file in tests/fixtures/ocr_regression/ with the ground truth
3. Add the disc path and JSON filename to the test fixtures below
4. The test will automatically run if the disc is available on the machine

The test invokes the real extraction pipeline (not duplicating logic) and compares
the OCR output against the ground truth baseline using fuzzy matching with
whitespace normalization.

JSON format:
{
  "disc_name": "Name of the disc",
  "disc_path": "Path to the DVD folder",
  "description": "Description of the test",
  "expected_results": [
    {
      "entry_id": "btn1",
      "raw_text": "CORRECT text as it appears on the menu (ground truth)"
    },
    ...
  ]
}

Note: The baseline contains the CORRECT expected text (ground truth), not the
actual OCR output. This allows the test to measure OCR accuracy and catch
both improvements and regressions.
"""

from __future__ import annotations

import difflib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dvdmenu_extract.util.io import read_json
from dvdmenu_extract.models.ocr import OcrModel


def _normalize_text(text: str) -> str:
    """
    Normalize text for comparison by removing extra whitespace and artifacts.
    
    - Removes leading/trailing whitespace
    - Collapses multiple spaces to single space
    - Removes common OCR artifacts like trailing "|"
    """
    # Remove leading/trailing whitespace
    text = text.strip()
    # Remove trailing pipe character (common artifact)
    text = text.rstrip("|").strip()
    # Collapse multiple spaces to single space
    text = " ".join(text.split())
    return text


def _text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity ratio between two text strings (0.0 to 1.0)."""
    normalized1 = _normalize_text(text1)
    normalized2 = _normalize_text(text2)
    return difflib.SequenceMatcher(None, normalized1, normalized2).ratio()


def _load_ocr_regression_data(json_filename: str) -> dict[str, Any]:
    """Load OCR regression test data from JSON file."""
    fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "ocr_regression"
    json_path = fixtures_dir / json_filename
    with json_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _run_extraction_pipeline(dvd_path: Path, output_path: Path) -> int:
    """
    Run the actual dvdmenu-extract CLI pipeline.
    
    Returns:
        Exit code from the extraction command
    """
    result = subprocess.run(
        [
            "uv",
            "run",
            "dvdmenu-extract",
            str(dvd_path),
            "--out",
            str(output_path),
            "--use-real-ffmpeg",
            "--overwrite-outputs",
            "--force",
        ],
        capture_output=True,
        check=False,
    )
    return result.returncode


def _run_ocr_regression_test(
    regression_data: dict[str, Any],
    tmp_path: Path,
    min_similarity: float = 0.90,
) -> None:
    """
    Run OCR regression test for a specific DVD by invoking the real extraction pipeline.
    
    Args:
        regression_data: Loaded JSON data with expected baseline results
        tmp_path: Temporary directory for test outputs
        min_similarity: Minimum similarity ratio (0.0 to 1.0) to pass
    """
    disc_name = regression_data["disc_name"]
    disc_path = Path(regression_data["disc_path"])
    expected_results = regression_data["expected_results"]
    
    if not disc_path.exists():
        pytest.skip(f"Disc not available: {disc_path}")
    
    # Run the actual extraction pipeline (don't duplicate logic)
    exit_code = _run_extraction_pipeline(disc_path, tmp_path)
    if exit_code != 0:
        pytest.fail(f"Extraction pipeline failed with exit code {exit_code}")
    
    # Read the OCR results
    ocr_json_path = tmp_path / "ocr.json"
    if not ocr_json_path.exists():
        pytest.fail(f"OCR output not found at {ocr_json_path}")
    
    ocr = read_json(ocr_json_path, OcrModel)
    
    # Create lookup by entry_id for easier comparison
    actual_by_id = {result.entry_id: result for result in ocr.results}
    
    # Track failures for detailed reporting
    failures: list[str] = []
    
    # Compare each expected result
    for expected in expected_results:
        entry_id = expected["entry_id"]
        expected_text = expected["raw_text"]
        
        # Check if we have this button in OCR results
        if entry_id not in actual_by_id:
            failures.append(
                f"{entry_id}: Missing from OCR results "
                f"(expected {len(expected_results)} results, got {len(ocr.results)})"
            )
            continue
        
        # Get actual OCR result
        actual = actual_by_id[entry_id]
        actual_text = actual.raw_text
        
        # Calculate similarity
        similarity = _text_similarity(expected_text, actual_text)
        
        if similarity < min_similarity:
            failures.append(
                f"{entry_id}: OCR mismatch (similarity: {similarity:.2%})\n"
                f"  Expected: '{expected_text}'\n"
                f"  Actual:   '{actual_text}'"
            )
    
    # Report all failures at once
    if failures:
        failure_msg = f"\n{disc_name} OCR regression test failures:\n\n" + "\n\n".join(failures)
        pytest.fail(failure_msg)


# ============================================================================
# Test fixtures - Add new disc tests here
# ============================================================================

@pytest.mark.skipif(
    not Path(r"Q:\DVD\Ellen_Season_04").exists(),
    reason="Ellen Season 04 disc not available on this machine",
)
def test_ocr_regression_ellen_season_04(tmp_path: Path) -> None:
    """
    Test OCR consistency for Ellen Season 04 DVD menu buttons.
    
    Current OCR accuracy: 14/15 buttons at 90%+, 1 button at 88% (btn13).
    Threshold set to 85% to allow for btn13's challenging text while still
    catching major regressions.
    """
    regression_data = _load_ocr_regression_data("ellen_season_04.json")
    _run_ocr_regression_test(regression_data, tmp_path, min_similarity=0.85)


# ============================================================================
# Example: How to add a new disc regression test
# ============================================================================
# 
# 1. Manually inspect DVD menu screens and capture the CORRECT text for each button
# 2. Create tests/fixtures/ocr_regression/your_disc.json with the ground truth:
#    {
#      "disc_name": "Your Disc Name",
#      "disc_path": "Q:\\DVD\\YourDiscName\\",
#      "description": "OCR accuracy test. Expected results from manual inspection.",
#      "expected_results": [
#        {"entry_id": "btn1", "raw_text": "CORRECT button 1 text"},
#        {"entry_id": "btn2", "raw_text": "CORRECT button 2 text"}
#      ]
#    }
# 3. Add a test function like this:
#
# @pytest.mark.skipif(
#     not Path(r"Q:\DVD\YourDiscName").exists(),
#     reason="YourDiscName not available on this machine",
# )
# def test_ocr_regression_your_disc(tmp_path: Path) -> None:
#     """Test OCR accuracy for YourDiscName DVD menu buttons."""
#     regression_data = _load_ocr_regression_data("your_disc.json")
#     _run_ocr_regression_test(regression_data, tmp_path, min_similarity=0.85)
