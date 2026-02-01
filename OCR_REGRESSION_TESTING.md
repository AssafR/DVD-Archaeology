# OCR Regression Testing System

This document describes the OCR regression testing framework implemented for the DVD Menu Extraction project.

## Overview

The OCR regression testing system provides a general framework for verifying that the OCR extraction pipeline accurately extracts text from DVD menu buttons. This helps catch regressions when changes are made to the OCR or image processing code.

**Key principles:** 
1. Tests invoke the actual extraction pipeline (via CLI), not duplicate logic
2. Baselines contain CORRECT expected text (ground truth), not OCR output
3. Tests measure OCR accuracy using fuzzy matching with whitespace normalization

## Components

### 1. Test Data Storage (`tests/fixtures/ocr_regression/`)

Ground truth baselines are stored as JSON files in this directory. Each JSON file represents one DVD disc's expected results from manual inspection of menu screens.

**Structure:**
```json
{
  "disc_name": "Human-readable disc name",
  "disc_path": "Absolute path to the DVD folder",
  "description": "Brief description. Expected results from manual inspection of menu screens.",
  "expected_results": [
    {
      "entry_id": "btn1",
      "raw_text": "The CORRECT text as it appears on the menu (ground truth)"
    }
  ]
}
```

**Important:** The baseline contains the CORRECT expected text (ground truth), NOT the OCR output. This allows the test to measure OCR accuracy and catch both improvements and regressions.

### 2. Test Framework (`tests/test_ocr_regression.py`)

The test framework provides:
- **Real pipeline invocation**: Runs the actual `dvdmenu-extract` CLI command
- **Whitespace normalization**: Collapses multiple spaces, removes artifacts like trailing "|"
- **Fuzzy text matching**: Uses `difflib.SequenceMatcher` to compare OCR results with ground truth
- **Configurable similarity threshold**: Default 85% similarity required to pass
- **Detailed failure reporting**: Shows expected vs actual text and similarity percentage
- **Extensible design**: Easy to add new disc tests

### 3. Reference Images

Visual references are stored alongside the JSON data for documentation:
- `ellen_season_04_page1.png` - Menu page 1 buttons
- `ellen_season_04_page2.png` - Menu page 2 buttons

## Example: Ellen Season 04

The first regression test covers Ellen Season 04 DVD:
- **Menu Page 1**: 10 buttons (episodes 65-74)
- **Menu Page 2**: 5 buttons (episodes 75-79)
- **Total**: 15 expected OCR results
- **Current Accuracy**: 10/15 buttons perfect (67%), 5 buttons with minor issues

The test verifies that the OCR accurately extracts episode information in the format:
```
<number>. <season>-<episode>  <code>  <date>  <title>
```

Example ground truth: `66. 4-4 C368 16 Oct 96 The Parent Trap`

**Known OCR Issues** (5 buttons):
- **btn1**: "2 Oct" → "20 Oct" (extra "0" inserted)
- **btn12**: "15 Jan 97" → "15 Jan 9" (year truncation)
- **btn13**: "77." → "Tf.", "C378" → "C0378" (multiple errors, most problematic)
- **btn14**: "5 Feb" → "SFeb" (space missing)

**Test Status**: ✅ PASSING at 85% similarity threshold

For details on OCR preprocessing improvements and trade-offs, see `OCR_IMPROVEMENTS.md`.

## How to Add a New Disc Test

### Step 1: Manually Inspect Menu Screens

Capture screenshots of the DVD menu screens or view them directly to determine the CORRECT text that appears on each button.

### Step 2: Create JSON with Ground Truth

Create a new JSON file in `tests/fixtures/ocr_regression/your_disc.json` with the CORRECT expected text:

```json
{
  "disc_name": "Your Disc Name",
  "disc_path": "Q:\\DVD\\YourDiscName\\",
  "description": "OCR accuracy test for Your Disc Name. Expected results from manual inspection of menu screens.",
  "expected_results": [
    {
      "entry_id": "btn1",
      "raw_text": "CORRECT text as it appears on the menu"
    },
    {
      "entry_id": "btn2",
      "raw_text": "Another CORRECT text from the menu"
    }
  ]
}
```

**Important:** The baseline should contain the CORRECT text (ground truth) as it actually appears on the menu screens, NOT the OCR output. This allows the test to measure OCR accuracy.

### Step 3: Add Test Function

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

### Step 4: Run the Test

```bash
# Run all OCR regression tests
uv run pytest tests/test_ocr_regression.py -v

# Run a specific disc test
uv run pytest tests/test_ocr_regression.py::test_ocr_regression_your_disc -v
```

## Features

### Fuzzy Text Matching

The test uses fuzzy string matching to handle minor OCR variations:
- Normalizes whitespace automatically (collapses multiple spaces)
- Removes common artifacts (trailing "|", etc.)
- Calculates similarity ratio (0.0 to 1.0)
- Configurable minimum similarity threshold (default: 0.85 / 85%)

### Multi-Button Testing

The test validates OCR across all menu buttons:
- Tests entire menu structure (15 buttons in Ellen Season 04)
- Compares actual OCR output against ground truth baseline
- Reports both perfect matches and near-misses

### Detailed Failure Reporting

When OCR results don't match expectations, the test provides:
- Button ID and entry location
- Similarity percentage
- Expected vs actual text comparison

Example failure output:
```
btn13: OCR mismatch (similarity: 88.31%)
  Expected: '77. 4-15 C378 22 Jan 97 Makin' Whoopie'
  Actual:   'Tf. 4-15 C0378 22 Jan 9/ Makin' Whoopie'
```

## Adjusting Similarity Threshold

The `min_similarity` parameter controls matching strictness:
- `1.0` = Exact match required (100%)
- `0.90` = 90% similarity (default, catches major regressions)
- `0.85` = 85% similarity (more lenient, allows minor variations)
- `0.70` = 70% similarity (very lenient, for unstable OCR)

Adjust based on the stability of OCR for your disc's text style. Higher thresholds catch smaller regressions but may have false positives if OCR is inherently unstable.

## Best Practices

1. **Test locally first**: Ensure the disc is accessible before committing the test
2. **Use descriptive names**: Name JSON files after the disc for easy identification
3. **Include reference images**: Save screenshots for visual documentation
4. **Document quirks**: Add notes in JSON `description` for unusual text formats
5. **Group by page**: Keep menu pages organized for clarity
6. **Run after changes**: Execute regression tests after modifying OCR or image processing code

## Benefits

- **Catch regressions**: Detect when OCR accuracy degrades
- **Validate improvements**: Verify that changes improve OCR results
- **Cross-platform consistency**: Ensure OCR works the same across different machines
- **Documentation**: Serves as examples of expected OCR output
- **Confidence**: Safe refactoring with automated verification

## Files Created

- `tests/fixtures/ocr_regression/ellen_season_04.json` - Expected OCR results
- `tests/fixtures/ocr_regression/ellen_season_04_page1.png` - Reference image (page 1)
- `tests/fixtures/ocr_regression/ellen_season_04_page2.png` - Reference image (page 2)
- `tests/fixtures/ocr_regression/README.md` - Quick reference guide
- `tests/test_ocr_regression.py` - Test framework and Ellen Season 04 test
- `OCR_REGRESSION_TESTING.md` - This documentation

## Running Tests

```bash
# Run all OCR regression tests
uv run pytest tests/test_ocr_regression.py -v

# Run specific test
uv run pytest tests/test_ocr_regression.py::test_ocr_regression_ellen_season_04 -v

# Collect tests without running
uv run pytest tests/test_ocr_regression.py --collect-only
```

## Recent Improvements (2026-02-01)

### OCR Preprocessing Enhancements
The OCR accuracy was improved through systematic testing and refinement:

1. **Vertical Padding Increase**: Doubled from 5% to 10% to prevent character clipping
2. **Character Blacklist**: Added "|" to eliminate spurious artifacts
3. **Magnification Analysis**: Tested 2x vs 3x, found 2x optimal (3x caused regressions)

**Results**: 
- Removed "|" artifact from all 15 buttons
- Maintained 67% perfect accuracy with no new regressions
- Comprehensive documentation added to codebase

See `OCR_IMPROVEMENTS.md` for detailed analysis and trade-offs.

## Future Enhancements

Possible improvements to the system:
- Post-processing rules for common patterns ("20 Oct" → "2 Oct", "SFeb" → "5 Feb")
- Additional regression tests for different DVD types (fonts, languages, layouts)
- Alternative OCR engines evaluation (EasyOCR, PaddleOCR)
- Custom trained models for DVD menu text
- Per-button adaptive preprocessing for problematic cases
- Visual diff generation for failed tests
- Confidence score validation
- Integration with CI/CD pipelines
