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
