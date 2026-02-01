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
- **Current Accuracy**: 14/15 buttons at 90%+, 1 button at 88%

The test verifies that the OCR accurately extracts episode information in the format:
```
<number>. <season>-<episode>  <code>  <date>  <title>
```

Example ground truth: `66. 4-4 C368 16 Oct 96 The Parent Trap`

**Known OCR Issue:**
- **btn13**: 88% accuracy - OCR reads "Tf." instead of "77.", "C0378" instead of "C378", "22 Jan 9/" instead of "22 Jan 97"

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
- Normalizes whitespace automatically
- Calculates similarity ratio (0.0 to 1.0)
- Configurable minimum similarity threshold (default: 0.85 / 85%)

### Multi-Page Menu Support

Buttons are organized by menu page:
- Each button has a `menu_page` number (1-based)
- Buttons are indexed sequentially within each page
- The test automatically groups and processes by page

### Detailed Failure Reporting

When OCR results don't match expectations, the test provides:
- Menu page and button ID
- Similarity percentage
- Expected vs actual text comparison

Example failure output:
```
Page 1, btn2: OCR mismatch (similarity: 78.50%)
  Expected: '66. 4-4  C368  16 Oct 96  The Parent Trap'
  Actual:   '66. 44  C368  16 Oct 96  The Parent Trap'
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

## Future Enhancements

Possible improvements to the system:
- Support for different OCR languages/configurations
- Visual diff generation for failed tests
- Confidence score validation
- Support for partial matches (substring matching)
- Performance benchmarking
- Integration with CI/CD pipelines
