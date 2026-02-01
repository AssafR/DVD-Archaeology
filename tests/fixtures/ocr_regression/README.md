# OCR Regression Test Data

This directory contains baseline OCR snapshots for DVD menu button regression tests.

## Purpose

These tests verify that the OCR extraction pipeline consistently produces the same results across different DVD titles. They help catch regressions when changes are made to the OCR or image processing code.

The tests invoke the actual extraction pipeline (not duplicating logic) and compare the OCR output against a baseline snapshot.

## Adding a New Disc Test

### 1. Manually Inspect Menu Screens

Capture screenshots or manually inspect the DVD menu screens to determine the CORRECT text that should appear on each button.

### 2. Create JSON File with Expected Text

Create a new JSON file in this directory with the CORRECT expected text:

```json
{
  "disc_name": "Human-readable disc name",
  "disc_path": "Q:\\DVD\\DiscName\\",
  "description": "OCR regression test for DiscName. Expected results from manual inspection of menu screens.",
  "expected_results": [
    {
      "entry_id": "btn1",
      "raw_text": "The CORRECT text that should be read from button 1"
    },
    {
      "entry_id": "btn2",
      "raw_text": "The CORRECT text that should be read from button 2"
    }
  ]
}
```

**Fields:**
- `entry_id`: The button entry ID (btn1, btn2, etc.)
- `raw_text`: The CORRECT text as it appears on the menu (not OCR output)

**Important:** The baseline should contain the ground truth (what the text actually says), NOT the OCR output. The test will compare OCR results against this ground truth to measure accuracy.

### 3. Add Test Function

In `tests/test_ocr_regression.py`, add a new test function:

```python
@pytest.mark.skipif(
    not Path(r"Q:\DVD\YourDiscName").exists(),
    reason="YourDiscName not available on this machine",
)
def test_ocr_regression_your_disc(tmp_path: Path) -> None:
    """Test OCR consistency for YourDiscName DVD menu buttons."""
    regression_data = _load_ocr_regression_data("your_disc.json")
    _run_ocr_regression_test(regression_data, tmp_path, min_similarity=0.90)
```

### 4. Adjust Similarity Threshold

The `min_similarity` parameter controls how closely the actual OCR must match the baseline:
- `1.0` = Exact match required (100%)
- `0.90` = 90% similarity (default, catches major regressions)
- `0.85` = 85% similarity (more lenient)

Adjust this based on how stable the OCR is for your disc's text style.

## Running Tests

Run all OCR regression tests:
```bash
pytest tests/test_ocr_regression.py -v
```

Run a specific disc test:
```bash
pytest tests/test_ocr_regression.py::test_ocr_regression_ellen_season_04 -v
```

## Tips

- **Normalize whitespace**: The test automatically normalizes whitespace, so minor spacing differences won't cause failures
- **Test locally first**: Make sure the disc is accessible on your machine before committing the test
- **Multiple pages**: If buttons span multiple menu pages, group them by `menu_page` number
- **Button ordering**: Buttons are indexed sequentially across all pages (page 1 buttons 1-10, then page 2 buttons 1-5, etc.)
