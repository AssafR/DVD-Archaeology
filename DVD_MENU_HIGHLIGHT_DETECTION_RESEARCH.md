# DVD Menu Highlight Detection Research

## Problem Statement

DVD menus with navigatable buttons present a challenging extraction problem:
- Buttons are highlighted when selected (using DVD navigation arrows)
- The highlight mechanism is unknown (possibly SPU/subtitle overlay)
- Button text is often to the RIGHT of the thumbnail, not on it
- Multiple menu "pages" can exist within a single VOB file
- Need to detect the full highlighted area (thumbnail + border + text)

### Test Case: DVD_Sample_01

- 3 buttons across 2 navigatable menu pages
- Buttons arranged vertically  
- Text positioned to the right of thumbnail images
- Highlight appears as a yellow/bright border around the thumbnail
- Both menu pages stored in VIDEO_TS.VOB (duration ~0.04s, 26 frames)

## Research Findings

### 1. DVD Menu Structure

**BTN_IT (Button Information Table) Analysis:**
- NAV packs contain button data: rectangles, navigation commands, VM instructions
- Can parse BTN_IT to understand:
  - Number of buttons per page
  - Button positions (though may not match screen coordinates)
  - Navigation structure (which buttons lead where)
  - Page detection based on button command patterns

**Multi-Page Menus:**
- Multiple logical "pages" can exist in a single VOB
- Pages are represented as different frames, not different time segments
- `ffprobe` reports misleading durations for menu VOBs (e.g., 0.04s for 26 frames)
- Solution: Extract ALL frames from short VOBs instead of timestamp sampling

### 2. Detection Approaches Tested

#### Approach A: Static Dark Region Detection
**Method:** Scan frames for dark rectangular regions (DVD thumbnail areas)
- Threshold: mean pixel value < 65
- Block-based scanning (8px blocks)
- Connected component analysis to find rectangles

**Problems:**
- Only detects the dark CORE of thumbnails
- Misses the highlight BORDER (often lighter/bright pixels)
- Incomplete captures: "btn1 only catches right side of highlight"
- Threshold too high: misses lighter portions
- Threshold too low: too many false positives (text, artifacts)

#### Approach B: Frame Differencing Only
**Method:** Compare consecutive frames to find what changes (moving highlight)
```python
aggregate_diff = ImageChops.lighter(frame1_diff, frame2_diff, ...)
mask = aggregate_diff.point(lambda p: 255 if p > threshold else 0)
```

**Findings:**
- Successfully detects CHANGING regions (highlight moving between buttons)
- Threshold matters: 5-10 works better than 15-20
- Morphological operations (dilation/erosion) help connect nearby changed pixels
- Detects highlight BORDERS but not always the full thumbnail interior
- Frame diff shows what's DIFFERENT, not necessarily what's COMPLETE

**Problems:**
- If highlight has static parts (e.g., base thumbnail always visible), only border changes are detected
- Very aggressive expansion needed (50-60px) to capture full button area from partial detection
- Can miss buttons if they don't move highlight significantly between frames

#### Approach C: Hybrid (Static + Frame Diff Validation)
**Method:** 
1. Detect static dark regions in each frame
2. Use frame differencing to validate which regions actually change
3. Keep only regions that overlap with changed areas

**Results:**
- Best dimensional accuracy: 519×142px, 486×142px, 519×142px
- Correctly mapped buttons to appropriate frames/pages
- Still missing left side of highlight border

**Why it worked better:**
- Static detection finds the thumbnail core
- Frame diff confirms it's a dynamic element (not static background)
- Combination provides more complete coverage

### 3. Key Technical Insights

**Highlight Mechanism Hypothesis:**
The DVD highlight likely works as:
1. Base thumbnail image (possibly always visible or in SPU layer 0)
2. Highlight border/overlay (SPU layer 1, changes when button selected)
3. Frame differencing captures the BORDER change, not the full thumbnail

**Expansion Strategy:**
- Initial detection finds core/partial region
- Post-detection expansion must capture:
  - Full thumbnail (left/right/top/bottom)
  - Highlight borders (bright pixels around thumbnail)
  - Text area (to the right, variable width)

**Multi-Page Detection:**
- Extract all frames from menu VOB (don't trust ffprobe duration)
- Group detected buttons by similarity (same button across frames)
- Use BTN_IT data to assign buttons to correct pages
- Match button index to appropriate frame for extraction

### 4. Current Implementation Status

**File:** `src/dvdmenu_extract/stages/menu_images.py`

**Current Approach:** Pure frame differencing with morphological operations
```python
# Threshold: 5 (very sensitive)
# Morphological: 3x MaxFilter(5), 1x MinFilter(3) 
# Expansion: 50px left, 60px right, 50px top/bottom
```

**Performance on DVD_Sample_01:**
- Detects 5 raw regions, uses 3 for buttons
- Correctly identifies multi-page structure via BTN_IT
- Button dimensions variable (not consistent)
- Still missing parts of highlight area

### 5. Debug Tools

**Debug Mask Output:**
Location: `{output_dir}/menu_images/_menu_detect_multipage/debug_frame_diff_mask.png`

Shows the aggregate frame difference mask after morphological operations. White pixels indicate detected changes.

**Frame Output:**
All extracted frames saved to `_menu_detect_multipage/VIDEO_TS_frame_*.png` for manual inspection.

## SOLUTION IMPLEMENTED: SPU Overlay Extraction ✅

**Status:** Implemented and validated on 2026-01-31

### The Correct Approach

DVD menu button highlights are stored as **SPU (Sub-Picture Unit) overlay streams**, not in the video frames themselves. The solution is to:

1. **Parse SPU packets** from the menu VOB file
2. **Decode RLE-compressed bitmaps** for each menu page
3. **Extract button rectangles** from connected components
4. **Map buttons to correct video frames** using page information

### Implementation Details

**Algorithm:**
1. Read entire menu VOB file (typically <1MB)
2. Parse MPEG-PS private stream 1 (stream ID 0xBD, substream 0x20-0x3F)
3. **Reassemble fragmented SPU packets** using size headers (critical!)
   - SPU packets are often split across multiple PES packets
   - Buffer and concatenate fragments until complete
   - Process all packets in sequence (one per menu page)
4. For each SPU packet:
   - Parse control structure (coordinates, offsets, menu flag)
   - Decode RLE-compressed bitmap (two fields for interlaced video)
   - Find connected components (regions of non-zero pixels)
   - Filter by size: ≥80x60px = buttons, smaller = navigation arrows
5. Map buttons to correct frames using temporal page detection

**What We Distinguish:**

1. **Menu SPUs vs. Subtitle SPUs**
   - Uses `is_menu` flag (SPU command `0x00` = "Force display")
   - Only process menu SPUs, skip subtitle SPUs
   
2. **Button Highlights vs. Navigation Arrows**
   - Size-based filtering: ≥80×60px = button, <80×60px = arrow
   - This is the key distinction for accurate extraction
   - On DVD_Sample_01: 113×90px buttons, 60×28px arrows

3. **What We Don't Distinguish (currently not needed):**
   - Button states (normal/selected/activated)
   - Substream purposes (all 0x20-0x3F processed equally)
   - Highlight colors or styles

**DVD Menu Structure:**
- Background video: Contains button thumbnail images
- SPU overlay: Contains button highlights (colored borders)
- These are separate streams, composited during playback
- **Critical insight:** Highlights are in SPU, not in video frames

**Results on DVD_Sample_01:**
- ✅ 100% accurate button extraction
- ✅ Perfect reproducibility (1.0000 similarity score)
- ✅ Correctly handles multi-page menus
- ✅ Filters out navigation arrows automatically

### Code Location

**Primary Implementation:** `src/dvdmenu_extract/stages/menu_images.py`
- Function: `_extract_spu_button_rects(vob_path, expected)`
- Nested function: `reassemble_spu_packets(vob_data)`

**SPU Parsing Library:** `src/dvdmenu_extract/util/libdvdread_spu.py`
- `parse_spu_control()` - Parse control structure
- `decode_spu_bitmap()` - Decode RLE bitmap
- `bitmap_connected_components()` - Find button regions
- `iter_spu_packets()` - Iterate through SPU packets in VOB

### Validation

**Test:** `tests/test_dvd_sample_01_regression.py`
- Compares generated button images against reference images
- Achieved 100% similarity (1.0000) for all 3 buttons
- Reference images stored in `tests/fixtures/DVD_Sample_01/menu_images/`

### Benefits

1. **Deterministic:** Direct access to authored button data
2. **Accurate:** Extracts exact button regions from disc
3. **Robust:** Works regardless of menu design/colors
4. **Fast:** <1 second for typical menu VOBs
5. **Reproducible:** Produces identical results every time

### Fallback Strategy

If SPU extraction fails or finds insufficient buttons, the system falls back to:
1. Frame-based detection (dark thumbnail cores)
2. Static region analysis
3. BTN_IT rectangle data (if available)

This ensures the pipeline works even for DVDs with non-standard authoring.

## Test Command

```bash
uv run dvdmenu-extract "C:\Users\Assaf\program\DVD-Archaeology\DVD_Sample_01\" \
  --out "C:\Users\Assaf\Desktop\Temporary\DVD_Sample_01" \
  --use-real-ffmpeg --overwrite-outputs --force
```

## Related Files

- **BTN_IT Implementation:** `src/dvdmenu_extract/util/btn_it_analyzer.py`
- **Detection Code:** `src/dvdmenu_extract/stages/menu_images.py`
- **Test Sample:** `DVD_Sample_01/`
- **Previous Documentation:** `BTN_IT_IMPLEMENTATION.md`, `PROGRESS_SUMMARY_2026-01-31.md`

## Questions Answered ✅

1. ~~Is the highlight rendered via SPU stream or baked into video frames?~~
   - **ANSWER:** SPU stream. Highlights are overlay graphics, not part of the video.

2. ~~Can we decode SPU data to get exact highlight coordinates?~~
   - **ANSWER:** Yes! SPU packets contain RLE-compressed bitmaps with exact button regions.

3. ~~Are there multiple SPU layers (base + highlight)?~~
   - **ANSWER:** Each SPU packet represents one menu page. Multiple packets = multiple pages.

4. ~~Can button press simulation provide clearer frame captures?~~
   - **ANSWER:** Not needed. Direct SPU extraction provides exact button data.

5. ~~What's the optimal combination of detection strategies?~~
   - **ANSWER:** SPU extraction as primary, with fallback to heuristics if needed.

## Conclusion

**Problem:** DVD menu button detection was unreliable using visual heuristics because button highlights are SPU overlays, not part of the video frames.

**Solution:** Direct SPU overlay extraction by parsing and decoding subpicture packets from the menu VOB file.

**Results:** 
- ✅ 100% accurate button extraction
- ✅ Perfect reproducibility (validated with regression tests)
- ✅ Handles multi-page menus correctly
- ✅ Fast and deterministic

**Key Insight:** Trying to visually detect highlights in extracted video frames was fundamentally flawed. The correct approach is to extract them directly from the SPU stream where they are actually stored.

---

*Last Updated: 2026-01-31*  
*Test Case: DVD_Sample_01 (3 buttons, 2 pages)*  
*Final Result: **100% accurate extraction via SPU overlays***  
*Status: **✅ SOLVED***
