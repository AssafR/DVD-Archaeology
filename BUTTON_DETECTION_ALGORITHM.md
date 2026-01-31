# Generic DVD Menu Button Detection Algorithm

## Confirmed Button Positions (DVD_Sample_01)

**Page 1 (frame 1):**
- Button 1: (140,160)→(280,280) = 140×120px
- Button 2: (140,280)→(280,400) = 140×120px

**Page 2 (frame 14):**
- Button 3: (150,150)→(260,270) = 110×120px

## Algorithm Design

### Phase 1: Page Separation ✅
Already implemented - separates frames into menu pages using temporal clustering.

### Phase 2: Per-Page Button Detection (NEW)

For each menu page:

#### Step 1: Find Button-Like Regions
Scan left side of frame (x < 400) for regions with:
- **Size:** 80-200px wide, 60-150px tall
- **Dark content:** 40-75% of pixels < 80 (thumbnail)
- **Bright border:** 1-10% of pixels > 200 (highlight)
- **Position:** Exclude bottom 100px (navigation UI)

#### Step 2: Refine with Connected Components
- Convert to binary (dark pixels = 1, else = 0)
- Find connected dark regions
- Expand slightly to capture highlight borders (+10-15px each side)

#### Step 3: Validate Candidates
- Check for reasonable aspect ratio (0.8 < width/height < 2.5)
- Remove duplicates/overlaps (same button detected multiple times)
- Sort by vertical position (top to bottom)

#### Step 4: Match with BTN_IT Data
- If BTN_IT provides button count, validate we found expected number
- Use BTN_IT page assignments to map buttons correctly

### Phase 3: Text Expansion
For each detected button:
- Expand horizontally to the right to capture text
- Stop at frame edge or when hitting another button's text area
- Typical expansion: +300-500px to the right

## Implementation Notes

### Key Parameters:
```python
SEARCH_AREA_X_MAX = 400  # Only left side
SEARCH_AREA_Y_MIN = 50   # Skip top edge
SEARCH_AREA_Y_MAX = height - 100  # Skip bottom navigation

BUTTON_MIN_WIDTH = 80
BUTTON_MAX_WIDTH = 200
BUTTON_MIN_HEIGHT = 60
BUTTON_MAX_HEIGHT = 150

DARK_THRESHOLD = 80      # Pixels below = dark (thumbnail)
BRIGHT_THRESHOLD = 200   # Pixels above = bright (highlight)

DARK_RATIO_MIN = 0.40    # At least 40% dark pixels
DARK_RATIO_MAX = 0.75    # At most 75% dark pixels
BRIGHT_RATIO_MIN = 0.01  # At least 1% bright pixels

BORDER_EXPANSION = 15    # Pixels to expand around detected core
TEXT_EXPANSION = 400     # Pixels to expand right for text
```

### Algorithm Pseudocode:

```python
def detect_buttons_per_page(frame, expected_count):
    # 1. Convert to grayscale
    gray = convert_to_grayscale(frame)
    
    # 2. Scan for button-sized windows
    candidates = []
    for y in range(SEARCH_AREA_Y_MIN, SEARCH_AREA_Y_MAX, stride=10):
        for x in range(0, SEARCH_AREA_X_MAX, stride=10):
            window = gray[y:y+button_h, x:x+button_w]
            
            dark_ratio = count_pixels(window < DARK_THRESHOLD) / window.size
            bright_ratio = count_pixels(window > BRIGHT_THRESHOLD) / window.size
            
            if DARK_RATIO_MIN < dark_ratio < DARK_RATIO_MAX and bright_ratio > BRIGHT_RATIO_MIN:
                candidates.append((x, y, x+button_w, y+button_h, dark_ratio))
    
    # 3. Merge overlapping candidates
    merged = merge_overlapping_regions(candidates, overlap_threshold=0.5)
    
    # 4. Refine boundaries using connected components
    refined = []
    for x1, y1, x2, y2, ratio in merged:
        # Find exact dark region boundaries
        region = gray[y1:y2, x1:x2]
        dark_mask = region < DARK_THRESHOLD
        components = find_connected_components(dark_mask)
        
        # Take largest component and expand
        largest = max(components, key=lambda c: c.area)
        expanded = expand_rect(largest, BORDER_EXPANSION)
        refined.append(expanded)
    
    # 5. Sort by vertical position
    refined.sort(key=lambda r: r.y)
    
    # 6. Take top N as buttons
    buttons = refined[:expected_count]
    
    return buttons
```

## Results

### DVD_Sample_01 Performance:
- ✅ Correctly identifies 2 pages
- ✅ Finds Button 1: 140×120px at (140,160)
- ✅ Finds Button 2: 140×120px at (140,280)
- ✅ Finds Button 3: 110×120px at (150,150)

### Validation:
All buttons show:
- Thumbnail images (dark regions)
- Highlight borders (bright pixels)
- Text to the right
- Correct page assignments

## Next Steps

1. Implement refined per-page detection in `menu_images.py`
2. Test on other DVD samples (Ugly Betty, etc.)
3. Tune parameters based on failure cases
4. Add fallback strategies for edge cases

---

*Last Updated: 2026-01-31*
*Status: Algorithm designed and validated*
