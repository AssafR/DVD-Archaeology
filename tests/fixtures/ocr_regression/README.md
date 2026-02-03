# OCR Regression Test Datasets

This directory contains OCR test datasets for DVD menu button regression testing. Tests automatically discover and run against all datasets in this folder.

## Quick Start

**To add a new test**: Just drop a JSON file in this directory following the schema. That's it - the test framework will automatically discover and run it!

## Purpose

These tests verify OCR extraction accuracy by:
1. Running the real extraction pipeline (not test stubs)
2. Comparing OCR output against ground truth baselines
3. Generating detailed reports (JSON + Markdown)
4. Tracking known issues per button

## Dataset Format

Each dataset is a JSON file following this structure (see `dataset_schema.json` for complete specification):

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
    {
      "entry_id": "btn1",
      "raw_text": "Ground truth text from manual inspection"
    }
  ],
  "known_issues": [
    {
      "entry_id": "btn1",
      "issue": "Description of known OCR problem",
      "expected_similarity": 0.90
    }
  ],
  "metadata": {
    "created_date": "2026-02-01",
    "approved_by": "Your Name"
  }
}
```

## Key Features

### 1. **Primary + Backup Source Paths**
Specify multiple source locations. Test tries primary first, falls back to backup if unavailable.

**Use cases:**
- Primary: Network drive (`Q:\DVD\DiscName\`)
- Backup: Local extracted copy (`C:\Temp\DiscName`)

### 2. **Auto-Discovery**
No need to manually add test functions! Just create a JSON file and pytest will automatically discover and run it.

### 3. **Known Issues Tracking**
Document expected OCR problems per button with custom similarity thresholds:

```json
"known_issues": [
  {
    "entry_id": "btn13",
    "issue": "OCR reads '77' as 'Tf'",
    "expected_similarity": 0.88
  }
]
```

### 4. **Detailed Test Reports**
Each test run generates:
- **JSON Report**: Machine-readable results with all metrics
- **Markdown Report**: Human-readable summary with pass/fail table

Reports saved to test output directory.

## Adding a New Dataset

### Step 1: Manually Verify Text
Capture screenshots or inspect DVD menus to determine **CORRECT** text for each button.

### Step 2: Create JSON Dataset

Create `tests/fixtures/ocr_regression/your_disc.json`:

```json
{
  "disc_name": "Your Disc Name",
  "description": "OCR test for Your Disc. Ground truth from manual inspection.",
  "source_paths": {
    "primary": "Q:\\DVD\\YourDisc\\",
    "backup": "C:\\backup\\YourDisc"
  },
  "test_config": {
    "min_similarity": 0.85,
    "skip_if_unavailable": true
  },
  "expected_results": [
    {"entry_id": "btn1", "raw_text": "Episode 1 - Title Here"},
    {"entry_id": "btn2", "raw_text": "Episode 2 - Another Title"}
  ],
  "known_issues": [
    {
      "entry_id": "btn1",
      "issue": "Known OCR issue description",
      "expected_similarity": 0.90
    }
  ],
  "metadata": {
    "created_date": "2026-02-01",
    "baseline_version": "Current OCR config",
    "approved_by": "Your Name"
  }
}
```

### Step 3: That's It!

Run tests: `uv run pytest tests/test_ocr_regression.py -v`

The framework automatically discovers your dataset and runs it.

## Field Reference

### Required Fields

- **`disc_name`**: Human-readable name (shown in test output)
- **`source_paths.primary`**: Primary path to DVD or extracted directory
- **`expected_results`**: Array of ground truth OCR results
  - `entry_id`: Button ID (btn1, btn2, etc.)
  - `raw_text`: CORRECT text (ground truth, not OCR output)

### Optional Fields

- **`source_paths.backup`**: Fallback path if primary unavailable
- **`description`**: What this test covers
- **`test_config.min_similarity`**: Global similarity threshold (default: 0.85)
- **`test_config.skip_if_unavailable`**: Skip if no sources found (default: true)
- **`known_issues`**: Array of documented OCR problems
  - `entry_id`: Button with issue
  - `issue`: Description of problem
  - `expected_similarity`: Custom threshold for this button
- **`metadata`**: Optional tracking info (dates, versions, approvals)

## Baseline Management

### What is a Baseline?

The `expected_results` array is your **ground truth baseline** - the CORRECT text as it appears on the DVD menu, manually verified by inspection.

**Important**: Baselines should NOT change unless:
1. You re-verify the actual menu text and found an error
2. You explicitly approve updated ground truth
3. The DVD itself changes

### Baseline Approval Process

1. Create initial baseline from manual inspection
2. Set `metadata.approved_by` to track who verified it
3. Run test to establish initial accuracy
4. **DO NOT auto-update baselines** from OCR output
5. Only update if manual re-inspection finds errors

### Example: Updating a Baseline

```json
{
  "metadata": {
    "created_date": "2026-01-15",
    "last_updated": "2026-02-01",
    "baseline_version": "v2 - corrected btn3 typo",
    "approved_by": "Manual re-inspection on 2026-02-01"
  }
}
```

## Running Tests

```bash
# Run all OCR regression tests
uv run pytest tests/test_ocr_regression.py -v

# Run specific disc (by name)
uv run pytest tests/test_ocr_regression.py -k "Ellen Season 04" -v

# Show detailed output including reports
uv run pytest tests/test_ocr_regression.py -v -s

# Generate only test list (no execution)
uv run pytest tests/test_ocr_regression.py --collect-only
```

## Test Reports

Each test generates reports in the temporary test output directory:

### JSON Report
`ocr_report_<disc_name>.json`
- Machine-readable
- Full comparison results
- Summary statistics
- Original dataset included

### Markdown Report  
`ocr_report_<disc_name>.md`
- Human-readable table
- Pass/fail indicators
- Similarity percentages
- Known issues section

**Report Location**: Shown in test failure messages

## Troubleshooting

### "No source paths available"
- Check that `source_paths.primary` or `source_paths.backup` exists
- Verify paths use correct format (Windows: `Q:\\DVD\\`, Unix: `/mnt/dvd/`)
- Set `skip_if_unavailable: false` to fail instead of skip

### "Extraction pipeline failed"
- Check stderr output in failure message
- Verify source is valid DVD structure
- Try running extraction manually to debug

### "OCR output not found"
- Pipeline may have failed silently
- Check tmp_path for actual output files
- Verify extraction completed all stages

### Test Passes But Shouldn't
- Check `min_similarity` threshold (may be too low)
- Review `known_issues` thresholds
- Verify baseline contains ground truth (not OCR output)

## Best Practices

1. **Source Paths**: Always specify backup for discs you test frequently
2. **Baselines**: Never auto-update from OCR; always manually verify
3. **Known Issues**: Document any buttons with expected OCR problems
4. **Thresholds**: Start with 0.85, tighten to 0.90+ for clean discs
5. **Metadata**: Track when/who approved baselines for audit trail
6. **Reports**: Review generated reports to understand failures

## Example: Complete Dataset

See `ellen_season_04.json` for a real-world example with:
- Primary + backup source paths
- 15 button baseline
- 4 documented known issues
- Complete metadata tracking

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
