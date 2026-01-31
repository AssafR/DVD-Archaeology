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

## Recommendations for Improvement

### Short Term:
1. **Inspect debug mask** to understand what frame diff actually detects
2. **Adjust morphological parameters** based on mask visualization
3. **Try adaptive expansion** based on detected region characteristics
4. **Combine approaches**: Use frame diff to find general area, static detection to refine boundaries

### Medium Term:
1. **SPU Stream Decoding:** Parse DVD subtitle/SPU streams to directly read highlight overlays
2. **Button Press Simulation:** Implement DVD VM commands to "press" buttons and observe state changes
3. **Adaptive Thresholding:** Use multiple detection strategies and vote/merge results
4. **ML-based Detection:** Train a model to recognize DVD menu button patterns

### Long Term:
1. **Full DVD VM Interpreter:** Execute button navigation commands to map all menu states
2. **SPU Render Engine:** Render highlight overlays directly from SPU data
3. **Multi-Strategy Fusion:** Combine BTN_IT, frame diff, SPU data, and static detection for robust extraction

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

## Open Questions

1. Is the highlight rendered via SPU stream or baked into video frames?
2. Can we decode SPU data to get exact highlight coordinates?
3. Are there multiple SPU layers (base + highlight)?
4. Can button press simulation provide clearer frame captures?
5. What's the optimal combination of detection strategies?

## Conclusion

Detecting DVD menu button highlights is challenging because:
- The mechanism varies by authoring tool
- Highlights may be partial (borders only) or complete (full overlay)
- Frame differencing captures changes but not always complete regions
- Static detection finds cores but misses dynamic elements
- No single approach works universally

The **hybrid approach** (static + frame diff validation) shows the most promise, but needs refinement to capture complete highlight areas. Further investigation into SPU stream structure and button press simulation may provide more reliable detection.

---

*Last Updated: 2026-01-31*  
*Test Case: DVD_Sample_01 (3 buttons, 2 pages)*  
*Current Best Result: 519×142px buttons with partial highlight capture*
