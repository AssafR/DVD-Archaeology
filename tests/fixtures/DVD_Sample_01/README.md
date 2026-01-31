# DVD_Sample_01 Test Fixtures

This directory contains reference images for regression testing of the DVD_Sample_01 sample disc.

## Contents

### menu_images/

Reference button images extracted from DVD_Sample_01 menu using SPU overlay extraction:

- **btn1.png** (36,376 bytes) - First button from menu page 1
- **btn2.png** (44,995 bytes) - Second button from menu page 1  
- **btn3.png** (38,984 bytes) - Third button from menu page 2

These images were generated on 2026-01-31 and represent the expected output of the SPU-based button extraction pipeline.

## Test Information

**Source DVD**: DVD_Sample_01  
**Location**: `C:\Users\Assaf\program\DVD-Archaeology\DVD_Sample_01\`  
**Menu Structure**: 2 pages, 3 buttons total (2 on page 1, 1 on page 2)

**Button Rectangles (from SPU overlays)**:
- Button 1: (150,176)→(262,265) size: 113x90 px (page 0)
- Button 2: (150,288)→(262,377) size: 113x90 px (page 0)
- Button 3: (150,176)→(262,265) size: 113x90 px (page 1)

**Extraction Method**: SPU (Sub-Picture Unit) overlay decoding with automatic page-to-frame mapping

## Regression Test

The regression test (`tests/test_dvd_sample_01_regression.py`) validates that:

1. The pipeline correctly extracts button images from DVD_Sample_01
2. Generated images match these reference images with ≥98% similarity
3. The full pipeline completes without errors

Run the test with:
```bash
uv run pytest tests/test_dvd_sample_01_regression.py -v
```

Note: The test is automatically skipped if DVD_Sample_01 is not present at the expected location.
