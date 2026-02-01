# OCR Regression Testing Summary

## What Was Built

A general-purpose OCR accuracy testing framework that verifies the DVD extraction pipeline produces accurate OCR results by comparing against ground truth baselines.

## Key Principles

1. **Tests invoke the actual extraction pipeline (via CLI), not duplicate logic.**
   - Ensures tests verify real product behavior
   - No logic duplication between test and product
   - Changes to the pipeline are automatically tested

2. **Baselines contain CORRECT expected text (ground truth), not OCR output.**
   - Expected text is manually verified from menu screenshots
   - Tests measure OCR accuracy against ground truth
   - Tests catch when OCR regresses or improves

3. **Whitespace-normalized comparison**
   - Ignores extra spaces, leading/trailing whitespace
   - Removes common artifacts like trailing "|"
   - Focuses on content accuracy, not formatting

## Current Test Coverage

### Ellen Season 04
- **Disc**: `Q:\DVD\Ellen_Season_04\`
- **Buttons**: 15 menu buttons (10 on page 1, 5 on page 2)
- **Baseline**: Ground truth from manual inspection of menu screens
- **Status**: ✅ PASSING (85% similarity threshold)
- **Current Accuracy**: 14/15 buttons at 90%+, 1 button (btn13) at 88%

## How It Works

1. Test invokes: `uv run dvdmenu-extract <disc> --out <tmp> --use-real-ffmpeg --overwrite-outputs --force`
2. Test reads the generated `ocr.json` file
3. Test compares each button's `raw_text` against the CORRECT expected text using fuzzy matching
4. Test reports any OCR results below similarity threshold (default 85%)

## Current OCR Issues (Ellen Season 04)

The test identifies where OCR accuracy falls short:
- **btn13**: 88% accuracy - OCR reads "Tf. 4-15 C0378 22 Jan 9/ Makin' Whoopie" instead of "77. 4-15 C378 22 Jan 97 Makin' Whoopie"
  - "Tf." instead of "77."
  - "C0378" instead of "C378"
  - "22 Jan 9/" instead of "22 Jan 97"

All other buttons (14/15) achieve 90%+ accuracy.

## Adding New Tests

See `tests/fixtures/ocr_regression/README.md` for detailed instructions.

Quick steps:
1. Run extraction: `uv run dvdmenu-extract "Q:\DVD\YourDisc" --out "baseline" --use-real-ffmpeg --force`
2. Copy results from `baseline/ocr.json` to `tests/fixtures/ocr_regression/your_disc.json`
3. Add test function in `tests/test_ocr_regression.py`
4. Run: `uv run pytest tests/test_ocr_regression.py::test_ocr_regression_your_disc -v`

## Files Created

```
tests/
├── test_ocr_regression.py                          # Test framework and Ellen test
└── fixtures/
    └── ocr_regression/
        ├── README.md                                # How to add tests
        ├── SUMMARY.md                               # This file
        ├── ellen_season_04.json                     # Baseline OCR snapshot
        ├── ellen_season_04_page1.png               # Reference image (page 1)
        └── ellen_season_04_page2.png               # Reference image (page 2)

OCR_REGRESSION_TESTING.md                           # Full documentation
```

## Run Tests

```bash
# All OCR regression tests
uv run pytest tests/test_ocr_regression.py -v

# Specific disc
uv run pytest tests/test_ocr_regression.py::test_ocr_regression_ellen_season_04 -v

# Collect without running
uv run pytest tests/test_ocr_regression.py --collect-only
```

## Future Enhancements

- Add more disc tests as needed
- Consider parametrized tests for multiple discs
- Add CI/CD integration to run on every commit
- Add visual diff generation for failures
- Track OCR improvements over time
