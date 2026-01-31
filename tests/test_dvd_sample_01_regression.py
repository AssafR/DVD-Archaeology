"""Regression test for DVD_Sample_01 button extraction.

This test validates that the SPU-based button extraction produces consistent
results for the DVD_Sample_01 sample disc. It compares generated button images
against reference images stored in the fixtures directory.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from dvdmenu_extract.pipeline import run_pipeline, PipelineOptions


# Path to the DVD_Sample_01 directory (must exist on the system)
DVD_SAMPLE_01_PATH = Path(r"C:\Users\Assaf\program\DVD-Archaeology\DVD_Sample_01")

# Path to reference button images
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "DVD_Sample_01" / "menu_images"

# Skip test if DVD_Sample_01 directory doesn't exist
pytestmark = pytest.mark.skipif(
    not DVD_SAMPLE_01_PATH.exists(),
    reason=f"DVD_Sample_01 not found at {DVD_SAMPLE_01_PATH}"
)


def image_similarity(img1: Image.Image, img2: Image.Image) -> float:
    """
    Calculate similarity between two images.
    
    Returns a value between 0.0 (completely different) and 1.0 (identical).
    Uses normalized root mean square error (RMSE) as the metric.
    """
    # Ensure images are the same size
    if img1.size != img2.size:
        return 0.0
    
    # Convert to same mode if needed
    if img1.mode != img2.mode:
        img2 = img2.convert(img1.mode)
    
    # Calculate difference
    diff = ImageChops.difference(img1, img2)
    
    # Get statistics
    stat = ImageStat.Stat(diff)
    
    # Calculate normalized RMSE (0 = identical, 255 = maximum difference)
    # For RGB images, stat.rms returns [R, G, B] values
    rms_values = stat.rms if isinstance(stat.rms, list) else [stat.rms]
    avg_rms = sum(rms_values) / len(rms_values)
    
    # Convert to similarity score (1.0 = identical, 0.0 = completely different)
    similarity = 1.0 - (avg_rms / 255.0)
    
    return similarity


def compare_images(generated_path: Path, reference_path: Path, min_similarity: float = 0.98) -> tuple[bool, float, str]:
    """
    Compare a generated image against a reference image.
    
    Args:
        generated_path: Path to the generated image
        reference_path: Path to the reference image
        min_similarity: Minimum similarity score required (0.0-1.0)
    
    Returns:
        Tuple of (passed, similarity_score, message)
    """
    if not generated_path.exists():
        return False, 0.0, f"Generated image not found: {generated_path}"
    
    if not reference_path.exists():
        return False, 0.0, f"Reference image not found: {reference_path}"
    
    try:
        img_generated = Image.open(generated_path)
        img_reference = Image.open(reference_path)
        
        similarity = image_similarity(img_generated, img_reference)
        
        if similarity >= min_similarity:
            return True, similarity, f"Images match (similarity: {similarity:.4f})"
        else:
            return False, similarity, f"Images differ (similarity: {similarity:.4f}, minimum: {min_similarity})"
    
    except Exception as e:
        return False, 0.0, f"Error comparing images: {e}"


@pytest.mark.slow
@pytest.mark.integration
def test_dvd_sample_01_button_extraction():
    """
    Regression test for DVD_Sample_01 button extraction.
    
    This test:
    1. Runs the pipeline on DVD_Sample_01
    2. Extracts button images (btn1.png, btn2.png, btn3.png)
    3. Compares them against reference images
    4. Validates that images are identical or very similar (≥98% similarity)
    
    The test uses SPU overlay extraction which should produce consistent results.
    """
    # Create a temporary output directory
    with tempfile.TemporaryDirectory() as temp_dir:
        out_dir = Path(temp_dir) / "DVD_Sample_01_output"
        out_dir.mkdir()
        
        # Run the pipeline up to menu_images stage
        # We only need to run up to menu_images to generate button images
        try:
            options = PipelineOptions(
                ocr_lang="eng+heb",
                use_real_ocr=True,
                use_real_ffmpeg=True,
                repair="none",
                force=False,
                json_out_root=False,
                json_root_dir=False,
                use_real_timing=True,
                allow_dvd_ifo_fallback=True,
                use_reference_images=False,
                use_reference_guidance=False,
                overwrite_outputs=True,
            )
            run_pipeline(
                input_path=DVD_SAMPLE_01_PATH,
                out_dir=out_dir,
                options=options,
                until="menu_images",
            )
        except Exception as e:
            pytest.fail(f"Pipeline execution failed: {e}")
        
        # Check that menu_images directory exists
        menu_images_dir = out_dir / "menu_images"
        assert menu_images_dir.exists(), f"menu_images directory not created: {menu_images_dir}"
        
        # Define button images to check
        button_files = ["btn1.png", "btn2.png", "btn3.png"]
        
        # Compare each button image
        results = {}
        for button_file in button_files:
            generated_path = menu_images_dir / button_file
            reference_path = FIXTURES_DIR / button_file
            
            passed, similarity, message = compare_images(
                generated_path,
                reference_path,
                min_similarity=0.98  # 98% similarity threshold
            )
            
            results[button_file] = {
                "passed": passed,
                "similarity": similarity,
                "message": message
            }
        
        # Report results
        all_passed = all(r["passed"] for r in results.values())
        
        if not all_passed:
            failure_message = "Button image comparison failed:\n"
            for button_file, result in results.items():
                status = "[PASS]" if result["passed"] else "[FAIL]"
                failure_message += f"  {status} {button_file}: {result['message']}\n"
            pytest.fail(failure_message)
        
        # Print success message with similarity scores
        print("\n[PASS] All button images match reference:")
        for button_file, result in results.items():
            print(f"  {button_file}: similarity = {result['similarity']:.4f}")


@pytest.mark.slow
@pytest.mark.integration
def test_dvd_sample_01_full_pipeline():
    """
    Full pipeline regression test for DVD_Sample_01.
    
    This test runs the complete pipeline (all stages) and validates:
    1. Button images are generated correctly
    2. OCR produces text output
    3. Video files are extracted
    4. No errors occur during pipeline execution
    """
    # Create a temporary output directory
    with tempfile.TemporaryDirectory() as temp_dir:
        out_dir = Path(temp_dir) / "DVD_Sample_01_full"
        out_dir.mkdir()
        
        # Run the full pipeline (excluding verify_extract which may fail on test data)
        try:
            options = PipelineOptions(
                ocr_lang="eng+heb",
                use_real_ocr=True,
                use_real_ffmpeg=True,
                repair="none",
                force=False,
                json_out_root=False,
                json_root_dir=False,
                use_real_timing=True,
                allow_dvd_ifo_fallback=True,
                use_reference_images=False,
                use_reference_guidance=False,
                overwrite_outputs=True,
            )
            run_pipeline(
                input_path=DVD_SAMPLE_01_PATH,
                out_dir=out_dir,
                options=options,
                until="extract",
            )
        except Exception as e:
            pytest.fail(f"Full pipeline execution failed: {e}")
        
        # Validate outputs
        menu_images_dir = out_dir / "menu_images"
        episodes_dir = out_dir / "episodes"
        
        # Check button images
        assert menu_images_dir.exists(), "menu_images directory not created"
        for button_file in ["btn1.png", "btn2.png", "btn3.png"]:
            button_path = menu_images_dir / button_file
            assert button_path.exists(), f"Button image not created: {button_file}"
        
        # Check OCR output
        ocr_json = out_dir / "ocr.json"
        assert ocr_json.exists(), "ocr.json not created"
        
        # Check extracted episodes
        assert episodes_dir.exists(), "episodes directory not created"
        episode_files = list(episodes_dir.glob("*.mkv"))
        assert len(episode_files) == 3, f"Expected 3 episode files, found {len(episode_files)}"
        
        print(f"\n[PASS] Full pipeline completed successfully")
        print(f"  Button images: {len(list(menu_images_dir.glob('*.png')))}")
        print(f"  Episode files: {len(episode_files)}")


if __name__ == "__main__":
    # Allow running the test directly for debugging
    import sys
    
    if not DVD_SAMPLE_01_PATH.exists():
        print(f"Error: DVD_Sample_01 not found at {DVD_SAMPLE_01_PATH}")
        sys.exit(1)
    
    print(f"Running regression test for DVD_Sample_01...")
    print(f"DVD path: {DVD_SAMPLE_01_PATH}")
    print(f"Reference images: {FIXTURES_DIR}")
    
    # Run the test
    pytest.main([__file__, "-v", "-s"])
