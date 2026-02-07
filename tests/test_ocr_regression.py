"""OCR accuracy regression tests for DVD menu buttons.

This module provides an auto-discovering, parametrized test framework for validating
OCR accuracy against ground truth baselines. Tests automatically discover and run
against all datasets in tests/fixtures/ocr_regression/.

## Adding a New Test

1. **Create a JSON dataset** in `tests/fixtures/ocr_regression/<disc_name>.json`:
   - Use `dataset_schema.json` for reference
   - Specify primary and optional backup source paths
   - List expected OCR results (ground truth from manual inspection)
   - Document any known issues

2. **That's it!** The test will automatically discover and run your dataset.

## Dataset Format

```json
{
  "disc_name": "Your Disc Name",
  "source_paths": {
    "primary": "Q:\\\\DVD\\\\YourDisc\\\\",
    "backup": "C:\\\\path\\\\to\\\\extracted"
  },
  "test_config": {
    "min_similarity": 0.85
  },
  "expected_results": [
    {"entry_id": "btn1", "raw_text": "Ground truth text"}
  ],
  "known_issues": [
    {"entry_id": "btn1", "issue": "Description", "expected_similarity": 0.90}
  ]
}
```

## Features

- **Auto-discovery**: Automatically finds all `*.json` datasets
- **Parametrized**: Each disc runs as separate pytest test
- **Fallback paths**: Tries primary, then backup if primary unavailable
- **Detailed reporting**: Generates JSON and Markdown reports in test output
- **Known issues tracking**: Documents expected OCR problems per button
- **Whitespace normalization**: Handles spacing/artifact differences

## Reports

Test reports are generated in the test output directory:
- `ocr_test_report.json` - Machine-readable results
- `ocr_test_report.md` - Human-readable summary
"""

from __future__ import annotations

import difflib
import json
import subprocess
from datetime import datetime
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


def _normalize_for_exact(text: str) -> str:
    """Normalize text for exact-match accounting: collapse whitespace and lowercase."""
    return " ".join(text.split()).lower()


def _normalize_for_exact(text: str) -> str:
    """Normalize text for exact-match accounting: collapse whitespace and lowercase."""
    return " ".join(text.split()).lower()


def _get_datasets_dir() -> Path:
    """Get the OCR regression datasets directory."""
    return Path(__file__).resolve().parent / "fixtures" / "ocr_regression"


def _discover_datasets() -> list[Path]:
    """
    Auto-discover all OCR regression test datasets.
    
    Returns:
        List of JSON dataset file paths (excludes schema file)
    """
    datasets_dir = _get_datasets_dir()
    # Find all .json files except the schema
    json_files = [
        f for f in datasets_dir.glob("*.json")
        if f.stem not in ["dataset_schema", "README"]
    ]
    return sorted(json_files)


def _load_dataset(dataset_path: Path) -> dict[str, Any]:
    """
    Load OCR regression test dataset from JSON file.
    
    Args:
        dataset_path: Path to JSON dataset file
        
    Returns:
        Dataset dictionary with all configuration and expected results
    """
    with dataset_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_available_source(dataset: dict[str, Any]) -> Path | None:
    """
    Find the first available source path from dataset.
    
    Tries primary path first, then backup if specified.
    
    Args:
        dataset: Dataset dictionary with source_paths
        
    Returns:
        First available Path, or None if no sources available
    """
    source_paths = dataset.get("source_paths", {})
    
    # Try primary first
    primary = source_paths.get("primary")
    if primary:
        primary_path = Path(primary)
        if primary_path.exists():
            return primary_path
    
    # Try backup if primary unavailable
    backup = source_paths.get("backup")
    if backup:
        backup_path = Path(backup)
        if backup_path.exists():
            return backup_path
    
    return None


def _run_extraction_pipeline(source_path: Path, output_path: Path) -> tuple[int, str]:
    """
    Run the actual dvdmenu-extract CLI pipeline up to OCR stage.
    
    For OCR regression testing, we only need stages through OCR:
    - ingest, nav_parse, menu_map, menu_images, ocr
    
    We skip the slow 'extract' stage (video frame extraction) since it's
    not relevant for OCR testing and takes 80%+ of the runtime.
    
    Args:
        source_path: Path to DVD or extracted directory
        output_path: Output directory for extraction
        
    Returns:
        Tuple of (exit_code, stderr_output)
    """
    result = subprocess.run(
        [
            "uv",
            "run",
            "dvdmenu-extract",
            str(source_path),
            "--out",
            str(output_path),
            "--until",
            "ocr",  # Stop before 'extract' stage (the slow one)
            "--use-real-ffmpeg",
            "--overwrite-outputs",
            "--force",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    return result.returncode, result.stderr


def _generate_test_report(
    dataset: dict[str, Any],
    results: list[dict[str, Any]],
    output_dir: Path,
    suite_root: Path | None = None,
) -> None:
    """
    Generate detailed test report in JSON and Markdown formats.
    
    Args:
        dataset: Original dataset with expected results
        results: List of comparison results for each button
        output_dir: Directory to write reports to
    """
    disc_name = dataset["disc_name"]
    timestamp = datetime.now().isoformat()
    
    # Calculate summary statistics
    total_buttons = len(results)
    perfect_matches = sum(1 for r in results if r["similarity"] >= 0.99)
    passing = sum(1 for r in results if r["passed"])
    failing = total_buttons - passing
    avg_similarity = sum(r["similarity"] for r in results) / total_buttons if results else 0
    exact_matches = sum(1 for r in results if r.get("exact_match"))
    mismatches = total_buttons - exact_matches
    
    # JSON Report
    json_report = {
        "disc_name": disc_name,
        "timestamp": timestamp,
        "summary": {
            "total_buttons": total_buttons,
            "perfect_matches": perfect_matches,
            "passing": passing,
            "failing": failing,
            "pass_rate": passing / total_buttons if total_buttons else 0,
            "average_similarity": avg_similarity,
            "exact_matches": exact_matches,
            "mismatches": mismatches,
        },
        "results": results,
        "dataset": dataset,
    }
    
    json_path = output_dir / f"ocr_report_{disc_name.replace(' ', '_').lower()}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    
    # Markdown Report
    md_lines = [
        f"# OCR Test Report: {disc_name}",
        f"",
        f"**Date**: {timestamp}",
        f"**Total Buttons**: {total_buttons}",
        f"**Pass Rate**: {passing}/{total_buttons} ({passing/total_buttons*100:.1f}%)",
        f"**Average Similarity**: {avg_similarity:.2%}",
        f"**Exact Matches**: {exact_matches}",
        f"**Non-exact (differences)**: {mismatches}",
        f"",
        f"## Summary",
        f"",
        f"- ✅ Perfect matches (≥99%): {perfect_matches}",
        f"- ✅ Passing (≥{dataset.get('test_config', {}).get('min_similarity', 0.85):.0%}): {passing}",
        f"- ❌ Failing: {failing}",
        f"",
        f"## Detailed Results",
        f"",
        f"| Button | Similarity | Status | Expected | Actual | Notes |",
        f"|--------|------------|--------|----------|--------|-------|",
    ]
    
    for result in results:
        status = "✅" if result["passed"] else "❌"
        similarity = f"{result['similarity']:.2%}"
        entry_id = result["entry_id"]
        expected = result["expected"][:50] + "..." if len(result["expected"]) > 50 else result["expected"]
        actual = result["actual"][:50] + "..." if len(result["actual"]) > 50 else result["actual"]
        notes = result.get("notes", "")
        
        md_lines.append(
            f"| {entry_id} | {similarity} | {status} | `{expected}` | `{actual}` | {notes} |"
        )
    
    # Add known issues section if present
    known_issues = dataset.get("known_issues", [])
    if known_issues:
        md_lines.extend([
            f"",
            f"## Known Issues",
            f"",
        ])
        for issue in known_issues:
            md_lines.append(f"- **{issue['entry_id']}**: {issue['issue']}")
    
    md_path = output_dir / f"ocr_report_{disc_name.replace(' ', '_').lower()}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    if suite_root is not None:
        _append_suite_summary(suite_root, json_report)


def _append_suite_summary(suite_root: Path, dataset_report: dict[str, Any]) -> None:
    """
    Append or update a suite-level aggregate report combining all parametrized datasets in this run.

    Writes JSON and Markdown to suite_root (the parent of each dataset's output_dir).
    """
    suite_root.mkdir(parents=True, exist_ok=True)
    json_path = suite_root / "ocr_suite_report.json"
    md_path = suite_root / "ocr_suite_report.md"

    if json_path.is_file():
        aggregate = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        aggregate = {"datasets": []}

    # Replace/update entry by disc_name
    datasets_by_name = {d["disc_name"]: d for d in aggregate.get("datasets", [])}
    datasets_by_name[dataset_report["disc_name"]] = dataset_report
    aggregate["datasets"] = list(datasets_by_name.values())

    # Recompute suite totals
    total_buttons = sum(d["summary"].get("total_buttons", 0) for d in aggregate["datasets"])
    total_passing = sum(d["summary"].get("passing", 0) for d in aggregate["datasets"])
    total_exact = sum(d["summary"].get("exact_matches", 0) for d in aggregate["datasets"])
    avg_sims = [
        d["summary"].get("average_similarity", 0.0)
        for d in aggregate["datasets"]
        if "summary" in d
    ]
    aggregate["summary"] = {
        "dataset_count": len(aggregate["datasets"]),
        "total_buttons": total_buttons,
        "total_passing": total_passing,
        "total_exact_matches": total_exact,
        "average_of_averages": (sum(avg_sims) / len(avg_sims)) if avg_sims else 0.0,
    }

    json_path.write_text(json.dumps(aggregate, indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown summary
    lines = [
        "# OCR Regression Suite Report",
        "",
        f"**Datasets**: {aggregate['summary']['dataset_count']}",
        f"**Total Buttons**: {aggregate['summary']['total_buttons']}",
        f"**Passing Buttons**: {aggregate['summary']['total_passing']}",
        f"**Exact Matches**: {aggregate['summary']['total_exact_matches']}",
        f"**Average of Dataset Averages**: {aggregate['summary']['average_of_averages']:.2%}",
        "",
        "## Datasets",
        "",
        "| Dataset | Buttons | Passing | Exact | Avg Similarity | Pass Rate |",
        "|---------|---------|---------|-------|----------------|-----------|",
    ]
    for d in sorted(aggregate["datasets"], key=lambda x: x["disc_name"]):
        s = d["summary"]
        pass_rate = s["passing"] / s["total_buttons"] if s.get("total_buttons") else 0
        lines.append(
            f"| {d['disc_name']} | {s['total_buttons']} | {s['passing']} | {s.get('exact_matches', 0)} | "
            f"{s['average_similarity']:.2%} | {pass_rate:.2%} |"
        )

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Suite summary updated at {md_path}")


def _run_ocr_regression_test(
    dataset: dict[str, Any],
    tmp_path: Path,
) -> None:
    """
    Run OCR regression test for a specific DVD dataset.
    
    This function:
    1. Finds available source path (primary or backup)
    2. Runs extraction pipeline
    3. Compares OCR results against ground truth
    4. Generates detailed test report
    5. Fails test if similarity below threshold
    
    Args:
        dataset: Complete dataset dictionary from JSON file
        tmp_path: Temporary directory for test outputs (used if no custom output_directory specified)
    """
    disc_name = dataset["disc_name"]
    expected_results = dataset["expected_results"]
    test_config = dataset.get("test_config", {})
    min_similarity = test_config.get("min_similarity", 0.85)
    skip_if_unavailable = test_config.get("skip_if_unavailable", True)
    known_issues_map = {
        issue["entry_id"]: issue
        for issue in dataset.get("known_issues", [])
    }
    
    # Use custom output directory if specified, otherwise use tmp_path
    custom_output_dir = test_config.get("output_directory")
    if custom_output_dir:
        output_path = Path(custom_output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = tmp_path
    
    # Find available source path
    source_path = _find_available_source(dataset)
    if source_path is None:
        if skip_if_unavailable:
            pytest.skip(f"{disc_name}: No source paths available")
        else:
            pytest.fail(f"{disc_name}: No source paths available")
    
    # Run the actual extraction pipeline (don't duplicate logic)
    exit_code, stderr = _run_extraction_pipeline(source_path, output_path)
    if exit_code != 0:
        pytest.fail(
            f"{disc_name}: Extraction pipeline failed with exit code {exit_code}\n"
            f"stderr: {stderr[:500]}"
        )
    
    # Read the OCR results
    ocr_json_path = output_path / "ocr.json"
    if not ocr_json_path.exists():
        pytest.fail(f"{disc_name}: OCR output not found at {ocr_json_path}")
    
    ocr = read_json(ocr_json_path, OcrModel)
    
    # Create lookup by entry_id for easier comparison
    actual_by_id = {result.entry_id: result for result in ocr.results}
    
    # Compare each expected result and collect detailed results
    comparison_results: list[dict[str, Any]] = []
    failures: list[str] = []
    
    for expected in expected_results:
        entry_id = expected["entry_id"]
        expected_text = expected["raw_text"]
        known_issue = known_issues_map.get(entry_id)
        
        # Use known issue threshold if specified, otherwise use global threshold
        button_threshold = (
            known_issue.get("expected_similarity", min_similarity)
            if known_issue
            else min_similarity
        )
        
        # Check if we have this button in OCR results
        if entry_id not in actual_by_id:
            comparison_results.append({
                "entry_id": entry_id,
                "expected": expected_text,
                "actual": "[MISSING]",
                "similarity": 0.0,
                "passed": False,
                "threshold": button_threshold,
                "notes": "Missing from OCR results",
            })
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
        passed = similarity >= button_threshold
        exact_match = _normalize_for_exact(expected_text) == _normalize_for_exact(actual_text)
        
        # Collect result
        notes = known_issue["issue"] if known_issue else ""
        comparison_results.append({
            "entry_id": entry_id,
            "expected": expected_text,
            "actual": actual_text,
            "similarity": similarity,
            "passed": passed,
            "threshold": button_threshold,
            "notes": notes,
            "exact_match": exact_match,
        })
        
        # Track failures
        if not passed:
            failure_detail = (
                f"{entry_id}: OCR mismatch (similarity: {similarity:.2%}, "
                f"threshold: {button_threshold:.2%})\n"
                f"  Expected: '{expected_text}'\n"
                f"  Actual:   '{actual_text}'"
            )
            if notes:
                failure_detail += f"\n  Known Issue: {notes}"
            failures.append(failure_detail)
    
    # Generate detailed reports
    _generate_test_report(
        dataset=dataset,
        results=comparison_results,
        output_dir=output_path,
        suite_root=output_path.parent,
    )
    # Non-intrusive notice for humans running tests interactively.
    report_stem = dataset["disc_name"].replace(" ", "_").lower()
    print(f"OCR report written to {output_path / f'ocr_report_{report_stem}.md'}")
    suite_report_md = output_path.parent / "ocr_suite_report.md"
    if suite_report_md.is_file():
        print(f"Suite summary updated at {suite_report_md}")
    
    # Report all failures at once
    if failures:
        report_path = output_path / f"ocr_report_{disc_name.replace(' ', '_').lower()}.md"
        failure_msg = (
            f"\n{disc_name} OCR regression test failures:\n\n"
            + "\n\n".join(failures)
            + f"\n\nDetailed report: {report_path}"
        )
        pytest.fail(failure_msg)


# ============================================================================
# Auto-discovering Parametrized Tests
# ============================================================================
# Tests automatically discover all datasets in tests/fixtures/ocr_regression/
# No need to manually add test functions - just drop in a new JSON file!
# ============================================================================

def _dataset_ids() -> list[str]:
    """Generate readable test IDs for parametrize."""
    datasets = _discover_datasets()
    ids = []
    for dataset_path in datasets:
        try:
            dataset = _load_dataset(dataset_path)
            ids.append(dataset["disc_name"])
        except Exception:
            ids.append(dataset_path.stem)
    return ids


@pytest.mark.parametrize(
    "dataset_path",
    _discover_datasets(),
    ids=_dataset_ids(),
)
def test_ocr_regression(dataset_path: Path, tmp_path: Path) -> None:
    """
    OCR regression test - auto-discovers and tests all datasets.
    
    This parametrized test automatically runs against every JSON file
    in tests/fixtures/ocr_regression/ (except schema files).
    
    To add a new test:
    1. Create a new JSON file following dataset_schema.json format
    2. That's it! The test will automatically discover and run it.
    
    Args:
        dataset_path: Path to dataset JSON file (parametrized by pytest)
        tmp_path: Temporary directory for test outputs
    """
    dataset = _load_dataset(dataset_path)
    _run_ocr_regression_test(dataset, tmp_path)
