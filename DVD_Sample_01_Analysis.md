# DVD_Sample_01 Analysis  

## Status: PARTIALLY FIXED ✅

### What's Working:
1. ✅ VOB selection now correct - extracts from VIDEO_TS.VOB (menu) instead of title VOBs
2. ✅ Background frame shows correct menu
3. ✅ Overlap prevention working - expansion limited to prevent overlaps
4. ✅ btn2 shows correct content with thumbnails and text

### What's Broken:
1. ❌ Rectangle detection finds wrong regions
2. ❌ btn1 shows blue background (wrong crop region)
3. ❌ btn3 likely also wrong (rect too narrow at 56px width)

## Problem Summary

DVD_Sample_01 contains a menu with thumbnail+text buttons. Initial issues with wrong VOB and overlapping rectangles have been fixed, but rectangle detection still finds incorrect regions.

## Menu Structure

Based on reference images:
- **Menu Layout**: Thumbnails on LEFT, text labels on RIGHT
- **Highlight Method**: Yellow/golden SPU overlay appears over thumbnail when selected
- **Navigation**: Two menu screens (1/2 indicator visible), 3 buttons total
- **Buttons**:
  - Button 1: Thumbnail + "Track #1"
  - Button 2: Thumbnail + "ðø+2" (or similar)  
  - Button 3: Thumbnail + text (on screen 2)
- **Bottom**: Navigation controls (>, >>, PLAY ALL)

## Current Detection Issues

### 1. No SPU/IFO Button Geometry
```
selection_rect: null
highlight_rect: null
```
The DVD IFO files don't contain button rectangles. SPU parsing found 0 buttons.

### 2. Fallback Visual Detection Problems

**Static frame detected 6 dark regions:**
```
(0, 176, 111, 351) - 112×176 - likely Thumbnail 1
(144, 176, 343, 351) - 200×176 - TOO WIDE, probably wrong
(0, 352, 55, 527) - 56×176 - too narrow
(152, 352, 263, 527) - 112×176 - likely Thumbnail 2
(120, 360, 271, 535) - 152×176
(112, 480, 271, 575) - 160×96 - might be nav buttons
```

**Selected first 3 for dvd_root menu:**
```
Raw: (0, 176, 111, 351), (144, 176, 343, 351), (0, 352, 55, 527)
```

### 3. Aggressive Expansion Causes Overlaps

**Expansion logic (lines 800-818 of menu_images.py):**
```python
# Heuristic: if rect is roughly square and < 30% of frame width,
# likely a thumbnail; expand right to capture adjacent text.
aspect = w / h if h > 0 else 1.0
if 0.5 <= aspect <= 2.0 and w < 720 * 0.3:
    expansion = int(w * 2.5)
    expanded_rects.append((x1, y1, min(719, x2 + expansion), y2))
```

**Results:**
```
(0, 176, 111, 351) → (0, 176, 391, 351)  [expand by 280px]
(144, 176, 343, 351) → (144, 176, 719, 351)  [expand by 376px]
```

**Overlap: 63%** (max allowed: 20%)

## Root Causes

1. **Wrong rectangles detected**: Detection found `(144, 176, 343, 351)` which is too wide and at wrong position
2. **No overlap prevention**: Expansion doesn't check for neighboring buttons
3. **No constraint on expansion**: Should expand only until next button or reasonable limit

## Proposed Solutions

### Solution 1: Limit Expansion to Available Space
Before expanding, check for overlaps with other detected buttons:
```python
def _expand_with_overlap_check(rects: list, max_width: int) -> list:
    sorted_rects = sorted(rects, key=lambda r: r[0])  # Sort by x position
    expanded = []
    for i, (x1, y1, x2, y2) in enumerate(sorted_rects):
        w = x2 - x1 + 1
        # Calculate desired expansion
        expansion = int(w * 2.5)
        max_x2 = min(max_width - 1, x2 + expansion)
        
        # Check for next button to the right
        if i + 1 < len(sorted_rects):
            next_x1 = sorted_rects[i + 1][0]
            # Leave a 10px gap
            max_x2 = min(max_x2, next_x1 - 10)
        
        expanded.append((x1, y1, max_x2, y2))
    return expanded
```

### Solution 2: Better Rectangle Detection
The current detection selects wrong rects. Should:
- Filter by consistent size (thumbnails should be similar dimensions)
- Sort by vertical position first, then horizontal
- Take exactly `expected` count of most likely candidates

### Solution 3: Use Frame Differencing for Highlights
Instead of static detection, use frame-to-frame differences to find the yellow highlight overlay:
- Sample multiple frames from menu VOB
- Detect regions that change (highlight on/off)
- These changing regions are the actual button areas

### Solution 4: Manual Calibration for Sample Disc
For DVD_Sample_01 specifically, add reference button coordinates that can be used for testing:
```json
{
  "DVD_Sample_01": {
    "buttons": [
      {"id": "btn1", "thumbnail": [0, 176, 111, 351], "full": [0, 176, 400, 351]},
      {"id": "btn2", "thumbnail": [0, 352, 111, 527], "full": [0, 352, 400, 527]},
      {"id": "btn3", "thumbnail": [...], "full": [...]}
    ]
  }
}
```

## Recommended Fix Priority

1. **HIGH**: Implement Solution 1 (overlap prevention) - immediate fix for current failure
2. **MEDIUM**: Implement Solution 2 (better detection) - improve accuracy
3. **LOW**: Solution 3 (frame differencing) - already implemented, may need tuning
4. **LOW**: Solution 4 (manual calibration) - useful for testing only

## Current Detection Problem

The static frame detector finds 6 dark regions:
```
(0, 176, 111, 351) - 112×176 - LEFT EDGE, not a thumbnail ❌
(144, 176, 343, 351) - 200×176 - FIRST THUMBNAIL ✅
(0, 352, 55, 527) - 56×176 - too narrow ❌
(152, 352, 263, 527) - 112×176 - SECOND THUMBNAIL ✅
(120, 360, 271, 535) - 152×176 - possible duplicate
(112, 480, 271, 575) - 160×96 - navigation buttons area
```

**Selected first 3 (WRONG):** `[(0, 176, 111, 351), (144, 176, 343, 351), (0, 352, 55, 527)]`
**Should select:** `[(144, 176, 343, 351), (152, 352, 263, 527), (third button from screen 2)]`

## Fix Needed: Better Rectangle Selection

The detection finds candidate rectangles but selects the wrong ones. Issues:
1. **No filtering of edge regions** - rects at x=0 or near edges should be deprioritized
2. **Size-based selection instead of quality-based** - should prefer rects with:
   - Not touching frame edges (x > 20, y > 20)
   - Consistent sizes (similar width/height to other candidates)
   - Vertically aligned (similar x positions for stacked buttons)

### Proposed Fix

```python
def _filter_thumbnail_candidates(rects: list, frame_width: int, frame_height: int, expected: int) -> list:
    """Filter detected rects to find actual thumbnails."""
    # Remove edge rects (too close to frame borders)
    edge_margin = 20
    filtered = [
        rect for rect in rects
        if rect[0] > edge_margin  # not touching left edge
        and rect[1] > edge_margin  # not touching top edge
        and rect[2] < frame_width - edge_margin  # not touching right edge
        and rect[3] < frame_height - edge_margin  # not touching bottom edge
    ]
    
    # Find most common x position (thumbnails are vertically stacked)
    x_positions = [rect[0] for rect in filtered]
    x_clusters = {}
    for x in x_positions:
        # Group by x with ±30px tolerance
        found_cluster = False
        for cluster_x in x_clusters:
            if abs(x - cluster_x) <= 30:
                x_clusters[cluster_x].append(x)
                found_cluster = True
                break
        if not found_cluster:
            x_clusters[x] = [x]
    
    # Use the largest cluster (most buttons at similar x position)
    best_cluster = max(x_clusters.values(), key=len, default=[])
    best_x = sum(best_cluster) / len(best_cluster) if best_cluster else 0
    
    # Filter to rects near the best x position
    aligned_rects = [
        rect for rect in filtered
        if abs(rect[0] - best_x) <= 30
    ]
    
    # Sort by y position and take top N
    aligned_rects.sort(key=lambda r: r[1])
    return aligned_rects[:expected]
```

## Next Steps

1. ✅ Fixed overlap-aware expansion logic
2. ✅ Fixed VOB selection for "dvd_root" menus
3. 🚧 Implement better rectangle filtering
4. Test with DVD_Sample_01
5. Handle second menu screen (button 3)
6. Document the highlight detection limitation (SPU overlays decoded in detection but not used for button boundaries yet)
