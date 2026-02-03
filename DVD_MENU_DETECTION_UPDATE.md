# DVD Menu Detection - Per-Page Frame Differencing Update

## Problem Identified (2026-01-31)

**Critical Issue:** Frame differencing was comparing frames from **different menu pages**, causing false positives from background differences rather than true highlight changes.

### Evidence:
- Raw regions detected included wide areas (220×55px, 283×43px) that were background elements differing between pages
- Only ~2-4 highlight-sized regions found despite 3 buttons expected
- User correctly identified: "image comparison done by mistake between background of menu1 and menu2"

## Solution Implemented

### Page Separation Algorithm

```python
def group_frames_by_page(frames):
    """Separate frames by menu page using temporal clustering."""
    # Compare consecutive frames
    # Large diff (>4) = page boundary
    # Small diff (<4) = same page
```

**For DVD_Sample_01:**
- **Threshold:** mean_diff > 4.0
- **Result:** 2 pages detected correctly
  - Page 0: frames 0-12 (13 frames)
  - Page 1: frames 13-25 (13 frames)
  - Page boundary at frame 12→13 (diff=5.45)

### Frame Difference Analysis:
```
Frame 0->1: diff=0.00   (same page, identical)
Frame 1->2: diff=0.00   (same page, identical)
...
Frame 12->13: diff=5.45  (>>> PAGE BOUNDARY)
Frame 13->14: diff=0.00  (same page, identical)
...
```

## Results

### Per-Page Frame Differencing:
- **Page 0:** 0 raw changed regions (frames identical)
- **Page 1:** 0 raw changed regions (frames identical)

**Conclusion:** Frames within each page are STATIC (no highlight movement). The VOB stores menu pages as static images, not animated navigation sequences.

## Implications

1. **False Positives Eliminated:** ✅ Page separation prevents comparing different menu backgrounds
2. **Highlight Detection Fails:** ❌ No movement within pages means frame differencing finds nothing
3. **Need Hybrid Approach:** Must use static detection PER-PAGE instead of across all frames

## Recommendations

### Short-Term (Current DVD):
Use static dark-region detection on:
- Representative frame from Page 0
- Representative frame from Page 1
Combine results to get all buttons.

### SPU-to-Frame Alignment (2026-02-03)
Some menus report correct SPU overlay coordinates, but the rendered frame is
vertically offset (e.g., Friends S09-10 page 2). To avoid hardcoded offsets,
`menu_images` now computes a per-page **y-shift** by:
1. Running lightweight OCR on the menu frame to get text line bounding boxes.
2. Matching SPU rects to OCR lines by horizontal overlap.
3. Taking the median vertical delta as the page-wide correction.

This happens *inside* `menu_images` during multi-page SPU mapping and is
independent of the pipeline OCR stage. If OCR yields too few lines or the
offset is implausible, it falls back to the raw SPU rects.

### Button Height Regularizer (2026-02-03)
Most menu pages render buttons with a consistent row height. `menu_images` now
optionally normalizes rect heights to the **page median** using IQR-based
outlier detection (no fixed pixel thresholds):
1. Compute heights for all rects on a page.
2. Use IQR bounds to detect outliers (multi-line or atypical buttons).
3. Resize only inlier rects to the median height, leaving outliers untouched.

This provides light regularization and anomaly detection without hardcoding
dimensions. If the page has too few rects or no consistent height, the step
is skipped.

### Size Outlier Filter (2026-02-03)
When SPU clustering yields more rects than expected, `menu_images` now applies
an IQR-based size filter to **remove small low-width/low-height outliers**.
This is intended to drop navigation arrows/widgets before width-ranking:
1. Compute width/height distributions across rects.
2. Mark rects that are low outliers in **both** width and height.
3. Remove those rects, then rank by width if still above expected count.

No fixed pixel thresholds are used; the filter is relative to the page’s
rect size distribution.

### Low-Height Outlier Filter (2026-02-03)
If there are still more rects than expected, `menu_images` also drops **low
height outliers** (IQR-based) *only when* doing so still leaves at least the
expected count. This targets short navigation widgets (e.g., arrows, play-all)
without risking removal of valid buttons on sparse pages.

### Long-Term (General Algorithm):
1. **Always separate pages first** (temporal clustering with adaptive threshold)
2. **Try frame differencing per-page** (may work for DVDs with animated menus)
3. **Fallback to static detection per-page** if no movement detected
4. **Validate using BTN_IT data** to ensure correct button count

## Validation Constraints (DVD_Sample_01)

These are VALIDATION hints for debugging, not hardcoded limits:
- **Highlight region:** x≈146-266, height≈84px (thumbnail only, not full button)
- **Buttons:** 3 total across 2 pages
- **Expected dimensions:** ~120×84px thumbnails

## Code Location

File: `src/dvdmenu_extract/stages/menu_images.py`
- Lines ~545-625: Page separation + per-page frame differencing
- Fallback to static detection when frame diff finds nothing

---

*Last Updated: 2026-01-31*
*Status: Page separation works; need per-page static detection*
