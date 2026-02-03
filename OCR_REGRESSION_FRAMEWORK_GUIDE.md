# OCR Regression Testing Framework - Complete Guide

**Date**: 2026-02-01  
**Status**: ✅ Production Ready - Generalized & Auto-Discovering

## Overview

This framework provides automated OCR accuracy regression testing with:
- **Auto-discovery**: Just drop in JSON files, tests automatically discover them
- **Parametrized testing**: Each disc runs as separate pytest test
- **Primary + backup paths**: Fallback support for multiple source locations
- **Baseline management**: Ground truth data with approval tracking
- **Detailed reporting**: JSON + Markdown reports per test run
- **Known issues tracking**: Document expected OCR problems per button

## Quick Start

### Adding a New Test

**Step 1**: Create `tests/fixtures/ocr_regression/your_disc.json`:

```json
{
  "disc_name": "Your Disc Name",
  "description": "What this test covers",
  "source_paths": {
    "primary": "Q:\\DVD\\YourDisc\\",
    "backup": "C:\\path\\to\\extracted"
  },
  "test_config": {
    "min_similarity": 0.85,
    "skip_if_unavailable": true
  },
  "expected_results": [
    {"entry_id": "btn1", "raw_text": "Ground truth from manual inspection"},
    {"entry_id": "btn2", "raw_text": "Another button text"}
  ],
  "known_issues": [
    {
      "entry_id": "btn1",
      "issue": "Known OCR problem description",
      "expected_similarity": 0.90
    }
  ],
  "metadata": {
    "created_date": "2026-02-01",
    "approved_by": "Your Name"
  }
}
```

**Step 2**: Run tests:

```bash
uv run pytest tests/test_ocr_regression.py -v
```

**That's it!** The test automatically discovers and runs your dataset.

## Architecture

### Components

1. **Dataset Schema** (`dataset_schema.json`)
   - JSON Schema defining dataset format
   - Reference documentation for fields
   - Validation guide

2. **Test Datasets** (`*.json` files)
   - One file per disc
   - Contains ground truth baselines
   - Source paths and configuration
   - Known issues documentation

3. **Test Framework** (`test_ocr_regression.py`)
   - Auto-discovers datasets
   - Runs extraction pipeline
   - Compares OCR vs baseline
   - Generates detailed reports

4. **Test Reports** (generated in tmp_path)
   - `ocr_report_<disc>.json` - Machine-readable
   - `ocr_report_<disc>.md` - Human-readable

### Data Flow

```
1. Test discovers dataset JSON files
   ↓
2. Tries primary source path, falls back to backup
   ↓
3. Runs dvdmenu-extract pipeline
   ↓
4. Reads ocr.json output
   ↓
5. Compares against expected_results baseline
   ↓
6. Generates JSON + Markdown reports
   ↓
7. Test passes/fails based on similarity thresholds
```

## Dataset Format Reference

### Required Fields

```json
{
  "disc_name": "string",          // Human-readable disc name
  "source_paths": {
    "primary": "string"           // Primary DVD/directory path
  },
  "expected_results": [           // Ground truth baseline
    {
      "entry_id": "string",       // Button ID (btn1, btn2, ...)
      "raw_text": "string"        // CORRECT text from manual inspection
    }
  ]
}
```

### Optional Fields

```json
{
  "description": "string",        // Test description
  "source_paths": {
    "backup": "string"            // Fallback path if primary unavailable
  },
  "test_config": {
    "min_similarity": 0.85,       // Global similarity threshold (0.0-1.0)
    "skip_if_unavailable": true   // Skip if no sources found
  },
  "known_issues": [               // Document expected OCR problems
    {
      "entry_id": "string",       // Button with issue
      "issue": "string",          // Problem description
      "expected_similarity": 0.90 // Custom threshold for this button
    }
  ],
  "metadata": {                   // Optional tracking info
    "created_date": "YYYY-MM-DD",
    "last_updated": "YYYY-MM-DD",
    "baseline_version": "string",
    "approved_by": "string"
  }
}
```

## Key Features Explained

### 1. Auto-Discovery

Tests automatically find and run against ALL `*.json` files in `tests/fixtures/ocr_regression/` (except `dataset_schema.json`).

**No need to**:
- Manually add test functions
- Update imports
- Modify test code

**Just**:
- Drop in a JSON file
- Run pytest

### 2. Primary + Backup Source Paths

Specify multiple source locations with automatic fallback:

```json
"source_paths": {
  "primary": "Q:\\DVD\\DiscName\\",        // Try this first
  "backup": "C:\\Temp\\DiscName_extracted" // Use if primary unavailable
}
```

**Use cases**:
- **Primary**: Network drive that may be offline
- **Backup**: Local extracted copy for fast testing
- **Multiple machines**: Different paths per environment

### 3. Known Issues Tracking

Document expected OCR problems with custom thresholds:

```json
"known_issues": [
  {
    "entry_id": "btn13",
    "issue": "OCR reads '77' as 'Tf' due to character clipping",
    "expected_similarity": 0.88
  }
]
```

**Benefits**:
- Test still passes for documented issues
- Issue appears in reports with explanation
- Custom threshold per button
- Tracks what needs improvement

### 4. Baseline Management

**Ground Truth Baselines**: The `expected_results` array contains the CORRECT text as it appears on the DVD menu, manually verified by inspection.

**Important Rules**:
1. **DO NOT auto-update** baselines from OCR output
2. **ONLY update** after manual re-inspection finds errors
3. **TRACK updates** in metadata (approved_by, dates)
4. **VERSION baselines** if OCR preprocessing changes

**Example Workflow**:

```json
{
  "metadata": {
    "created_date": "2026-01-15",
    "last_updated": "2026-02-01",
    "baseline_version": "v2 - OCR preprocessing improvements",
    "approved_by": "Manual re-inspection after OCR update"
  }
}
```

### 5. Detailed Test Reports

Each test run generates two reports:

#### JSON Report (`ocr_report_<disc>.json`)
```json
{
  "disc_name": "Ellen Season 04",
  "timestamp": "2026-02-01T13:26:55",
  "summary": {
    "total_buttons": 15,
    "perfect_matches": 11,
    "passing": 15,
    "failing": 0,
    "pass_rate": 1.0,
    "average_similarity": 0.9879
  },
  "results": [...]
}
```

#### Markdown Report (`ocr_report_<disc>.md`)
```markdown
# OCR Test Report: Ellen Season 04

**Pass Rate**: 15/15 (100.0%)
**Average Similarity**: 98.79%

| Button | Similarity | Status | Expected | Actual | Notes |
|--------|------------|--------|----------|--------|-------|
| btn1   | 98.70%     | ✅     | ...      | ...    | Known issue |
```

**Report Location**: Printed in test failure messages

## Running Tests

### All Tests

```bash
uv run pytest tests/test_ocr_regression.py -v
```

### Specific Disc (by name)

```bash
uv run pytest tests/test_ocr_regression.py -k "Ellen Season 04" -v
```

### Show Detailed Output

```bash
uv run pytest tests/test_ocr_regression.py -v -s
```

### Collect Without Running

```bash
uv run pytest tests/test_ocr_regression.py --collect-only
```

### With Report Directory

```bash
uv run pytest tests/test_ocr_regression.py -v --basetemp=./test_reports
```

## Test Output Example

```
tests/test_ocr_regression.py::test_ocr_regression[Ellen Season 04] PASSED [100%]
tests/test_ocr_regression.py::test_ocr_regression[Ugly Betty S01] PASSED [100%]

======================== 2 passed in 5:23 ========================
```

Each disc runs as a separate parametrized test with its name as the test ID.

## Baseline Approval Workflow

### Initial Baseline Creation

1. **Manual Inspection**: Capture DVD menu screenshots
2. **Extract Text**: Manually transcribe CORRECT text for each button
3. **Create Dataset**: Save to JSON with `created_date` and `approved_by`
4. **Run Test**: Establish initial accuracy metrics
5. **Document Issues**: Add any failing buttons to `known_issues`

### Updating an Existing Baseline

**Only update if**:
1. Manual re-inspection finds an ERROR in baseline
2. Ground truth was incorrect
3. DVD content actually changed

**Never update because**:
- OCR output changed
- Test started failing
- Someone "thinks" baseline is wrong

**Update Process**:
1. Re-inspect original DVD menu
2. Verify ground truth is incorrect
3. Update `expected_results` with correct text
4. Update `metadata.last_updated`
5. Update `metadata.approved_by` with justification
6. Run test to verify

**Example Update**:

```json
{
  "expected_results": [
    {
      "entry_id": "btn3",
      "raw_text": "Corrected spelling from re-inspection"
    }
  ],
  "metadata": {
    "created_date": "2026-01-15",
    "last_updated": "2026-02-01",
    "baseline_version": "v2 - btn3 spelling corrected",
    "approved_by": "Re-inspection found typo in original transcription"
  }
}
```

## Troubleshooting

### "No source paths available"

**Cause**: Neither primary nor backup paths exist

**Solutions**:
- Check path format (Windows: `Q:\\DVD\\`, Unix: `/mnt/dvd/`)
- Verify disc/directory exists
- Set `skip_if_unavailable: false` to fail instead of skip

### "Extraction pipeline failed"

**Cause**: dvdmenu-extract command failed

**Solutions**:
- Check stderr in failure message
- Run extraction manually to debug: `uv run dvdmenu-extract "path" --out "test"`
- Verify valid DVD structure

### Test Passes But Shouldn't

**Cause**: Threshold too low or wrong baseline

**Solutions**:
- Check `min_similarity` value (try 0.90+)
- Review `known_issues` thresholds
- Verify baseline contains ground truth (not OCR output)

### Report Not Found

**Cause**: Test passed without generating report location

**Solutions**:
- Check pytest `--basetemp` directory
- Look in `/tmp/pytest-of-<user>/pytest-<N>/`
- Reports always generated, check test output for path

## Best Practices

### 1. Source Paths
- ✅ Always specify backup for frequently tested discs
- ✅ Use network drive (primary) + local copy (backup)
- ✅ Verify paths on all testing machines

### 2. Baselines
- ✅ Never auto-update from OCR output
- ✅ Always manually verify ground truth
- ✅ Track updates in metadata
- ✅ Document approval process

### 3. Known Issues
- ✅ Document any expected OCR problems
- ✅ Set realistic thresholds per button
- ✅ Include issue description for context
- ❌ Don't add every minor difference - focus on actual bugs

### 4. Thresholds
- ✅ Start with 0.85 for general testing
- ✅ Increase to 0.90+ for high-quality OCR
- ✅ Use per-button thresholds for known issues
- ❌ Don't set threshold to 1.0 unless perfect OCR

### 5. Metadata
- ✅ Always set created_date
- ✅ Track who approved baseline
- ✅ Version baselines when OCR changes
- ✅ Document why baselines updated

## Example: Complete Dataset

See `tests/fixtures/ocr_regression/ellen_season_04.json` for a real-world example with:
- Primary + backup paths
- 15 button baseline
- 4 known issues documented
- Complete metadata tracking
- Custom thresholds per issue

## Migration from Old Format

### Old Format (Single Disc)

```python
def test_ocr_regression_disc(tmp_path):
    dataset = load_data("disc.json")
    run_test(dataset, tmp_path)
```

### New Format (Auto-Discovering)

Just the JSON file - test auto-discovers it!

```json
{
  "disc_name": "Disc Name",
  "source_paths": {"primary": "path"},
  "expected_results": [...]
}
```

**Migration Steps**:
1. Update JSON format (add `source_paths`, etc.)
2. Delete old test functions
3. Run `pytest --collect-only` to verify discovery

## Summary

The generalized OCR regression testing framework provides:

- ✅ **Zero-config test addition**: Drop in JSON, run tests
- ✅ **Fallback support**: Primary + backup paths
- ✅ **Known issues**: Document expected problems
- ✅ **Detailed reports**: JSON + Markdown per run
- ✅ **Baseline management**: Approval tracking and versioning
- ✅ **Auto-discovery**: Tests find datasets automatically

**To add a test**: Create one JSON file.  
**To run tests**: `uv run pytest tests/test_ocr_regression.py -v`

That's it! 🎉
