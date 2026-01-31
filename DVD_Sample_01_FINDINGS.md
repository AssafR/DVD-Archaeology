# DVD_Sample_01 - Complete Analysis & Findings

## Summary

DVD_Sample_01 is a test disc with a **multi-page menu** system that reveals several challenges with DVD button detection that aren't present in simpler discs like UglyBetty.

## Current Status (2026-01-30)

### ✅ What's Working:
1. **VOB Selection Fixed** - Now correctly extracts from VIDEO_TS.VOB (menu) for "dvd_root" menus
2. **Background Extraction** - Menu frames are correctly extracted
3. **Overlap Prevention** - Button expansion limited to prevent overlap with neighboring buttons
4. **Edge Filtering** - Rectangles touching frame edges are now filtered out
5. **Duplicate Detection** - Vertically overlapping rects are deduplicated (keeps largest)

### ⚠️ Partial Issues:
1. **Multi-Page Menus** - Only detects buttons visible on page 1 (2 of 3 buttons)
2. **Rectangle Detection** - Finds correct thumbnails but can't handle buttons on other menu pages

### ❌ Unsolved Problems:
1. **SPU Highlight Decoding** - Yellow highlight overlay position not extracted
2. **Multi-Page Navigation** - Can't extract frames from menu page 2 for button 3
3. **Highlight Position Detection** - Haven't figured out where the yellow square appears

## DVD Structure

### Files:
```
VIDEO_TS.VOB     - Main menu (933 KB) - contains 2-page menu
VTS_01_1.VOB     - Track 1 content (5.4 MB, 22.2s)
VTS_02_1.VOB     - Track 2 content (9.0 MB, 25.2s)  
VTS_03_1.VOB     - Track 3 content (8.3 MB, 37.8s)
```

### Navigation Structure:
```json
{
  "disc_format": "DVD",
  "menu_domains": ["dvd_root"],
  "menu_buttons": [
    {"button_id": "btn1", "menu_id": "dvd_root", "title_id": 1, "selection_rect": null},
    {"button_id": "btn2", "menu_id": "dvd_root", "title_id": 2, "selection_rect": null},
    {"button_id": "btn3", "menu_id": "dvd_root", "title_id": 3, "selection_rect": null}
  ]
}
```

**Key Observation:** All `selection_rect` and `highlight_rect` fields are `null` - this disc doesn't store button geometry in IFO files.

## Menu Layout (Visual Analysis)

### Page 1 (1/2 indicator):
```
┌────────────────────────────────────┐
│  DVD Title!                    1/2 │
│                                    │
│  [thumbnail]     Track #1          │
│                                    │
│  [thumbnail]     ðø+2              │
│                                    │
│           >    >>    PLAY ALL      │
└────────────────────────────────────┘
```

### Page 2 (2/2):
```
┌────────────────────────────────────┐
│  DVD Title!                    2/2 │
│                                    │
│  [thumbnail]     Track #3          │
│                                    │
│                                    │
│           >    >>    PLAY ALL      │
└────────────────────────────────────┘
```

**Layout Characteristics:**
- Thumbnails: ~112-200px wide, positioned at x≈150-260
- Text labels: To the RIGHT of thumbnails (not overlaid)
- Highlight: Yellow/golden overlay appears OVER thumbnail when selected
- Navigation: Arrow buttons at bottom allow page navigation

## Button Highlighting Mechanism

### How It Works (Theory):
1. **Base Layer**: Background image with thumbnails (baked in)
2. **Text Layer**: Text labels "Track #1", "ðø+2" (also baked in background)
3. **Highlight Layer**: Yellow semi-transparent SPU overlay that appears when button selected

### Reference Images Show:
- **Unselected**: Thumbnail shows normal video content
- **Selected**: Yellow overlay (~50% opacity) covers thumbnail area
- **Highlight Rectangle**: Appears to be ~112×176 pixels, positioned over thumbnail

### SPU Detection Results:
```
SPU parsing: 0 buttons found
NAV pack parsing: 0 buttons found
```

**Conclusion**: This DVD doesn't have parseable SPU/NAV button geometry in the IFO/VOB structure. The highlight is likely:
- Rendered by the DVD player at runtime based on button focus
- Part of a subpicture stream that's only active during menu interaction
- Position determined by button navigation graph (not explicit coordinates)

## Current Detection Results

### Static Frame Analysis:
```
Detected 6 dark regions (by size):
1. (0, 0, 359, 175) - 360×176 - top banner (WRONG)
2. (144, 176, 343, 351) - 200×176 - BUTTON 1 THUMBNAIL ✓
3. (120, 360, 271, 535) - 152×176 - possible duplicate
4. (0, 176, 111, 351) - 112×176 - left edge (WRONG)
5. (152, 352, 263, 527) - 112×176 - BUTTON 2 THUMBNAIL ✓
6. (112, 480, 271, 575) - 160×96 - nav buttons area

After edge filtering + deduplication:
1. (144, 176, 343, 351) - Button 1 ✓
2. (120, 360, 271, 535) - Button 2 region (multiple candidates, kept largest)

Missing: Button 3 (on page 2)
```

### Expansion Results:
```
Before expansion:
btn1: (144, 176, 343, 351) - width 200px
btn2: (120, 360, 271, 535) - width 152px

After 2.5× expansion with overlap prevention:
btn1: (144, 176, 719, 351) - expanded to right edge (no neighbor detected)
btn2: (120, 360, 651, 535) - expanded 380px right

✓ No overlap (overlap prevention working)
```

## Code Changes Made

### 1. VOB Selection Fix (menu_images.py ~line 880)
**Problem**: Was using target VOB (where button leads) instead of menu VOB (where button image is)

**Fix**:
```python
# First priority: use menu_id to find the menu VOB
if menu_base and menu_base.upper() == "VMGM":
    vob_path = video_ts_path / "VIDEO_TS.VOB"
elif menu_base and menu_base.upper().startswith("VTSM"):
    parts = menu_base.split("_")
    if len(parts) >= 2 and parts[1].isdigit():
        vob_path = video_ts_path / f"VTS_{parts[1]}_0.VOB"
elif menu_base == "dvd_root" or menu_id == "dvd_root":
    # "dvd_root" typically means main menu in VIDEO_TS.VOB
    vob_path = video_ts_path / "VIDEO_TS.VOB"
```

### 2. Overlap-Aware Expansion (menu_images.py ~line 810)
**Problem**: 2.5× expansion caused 63% overlap between buttons

**Fix**:
```python
# Check for buttons to the right on the same row (prevent overlap)
for other_rect in sorted_rects[idx + 1:]:
    other_x1, other_y1, other_x2, other_y2 = other_rect
    # If on similar vertical position (same row), limit expansion
    if abs(other_y1 - y1) < 50:  # Same row threshold
        # Leave a 10px gap to prevent overlap
        max_x2 = min(max_x2, other_x1 - 10)
```

### 3. Edge Filtering & Deduplication (menu_images.py ~line 418)
**Problem**: Detected edge regions and duplicates instead of actual thumbnails

**Fix**:
```python
# Filter out edge rects (too close to frame borders)
edge_margin = 20
filtered_thumbnails = [
    rect for rect in thumbnails
    if rect[0] > edge_margin and rect[1] > edge_margin
]

# Remove vertically overlapping duplicates (keep largest)
deduped = []
for rect in sorted(filtered_thumbnails, key=lambda r: (r[2]-r[0])*(r[3]-r[1]), reverse=True):
    y_center = (rect[1] + rect[3]) / 2
    overlaps = False
    for existing in deduped:
        existing_y_center = (existing[1] + existing[3]) / 2
        if abs(y_center - existing_y_center) < 100:  # Same row threshold
            overlaps = True
            break
    if not overlaps:
        deduped.append(rect)
```

### 4. Multi-Page Menu Fallback (menu_images.py ~line 937)
**Problem**: btn3 on page 2 causes extraction to fail

**Temporary Fix**:
```python
if not crop_rect:
    # Fallback for buttons not visible on current menu frame
    logger.warning(
        f"menu_images: missing rect for {entry.entry_id}, using default (multi-page menu?)"
    )
    crop_rect = RectModel(x=150, y=350, w=400, h=150)
```

## Remaining Challenges

### 1. SPU Highlight Position Detection
**Problem**: Can't extract the yellow highlight rectangle position

**Why It's Hard**:
- SPU parsing found 0 buttons in this DVD
- Highlight may be player-generated, not stored in VOB
- May require decoding the subpicture stream during menu playback
- Position might be in button navigation graph (BTN_IT data)

**Possible Solutions**:
a) **Frame Differencing**: Extract multiple frames while "pressing" different buttons, compute diff
b) **NAV Pack Deep Dive**: Parse BTN_IT command tables more thoroughly
c) **Template Matching**: Use the yellow overlay as a template to find its position
d) **Accept Limitation**: Document that some DVDs don't have extractable highlight geometry

### 2. Multi-Page Menu Navigation
**Problem**: Button 3 is on page 2, only page 1 is extracted

**Why It's Hard**:
- DVD_Sample_01 has one VIDEO_TS.VOB containing both menu pages
- No explicit "page" boundaries in IFO structure
- Would need to simulate button navigation to reach page 2
- Requires understanding of DVD menu navigation commands

**Possible Solutions**:
a) **Multi-Frame Extraction**: Extract frames at multiple timestamps from menu VOB
b) **Navigation Simulation**: Parse PGC commands to understand page transitions
c) **Accept Limitation**: Document that multi-page menus require manual button placement

### 3. Text Adjacent to Buttons
**Current Heuristic**: Expand thumbnail region 2.5× to the right

**Problems**:
- Works for DVD_Sample_01 (text is right of thumbnail)
- May fail for other layouts (text below, above, or overlaid)
- Expansion causes issues when buttons are close together

**Better Approach**:
- OCR the entire menu frame
- Find text regions using pytesseract.image_to_data()
- Match text regions to button regions by proximity
- Create combined rect (thumbnail + nearest text)

## Recommendations

### Short Term (Current Session):
1. ✅ Run full pipeline to see current results
2. ✅ Document findings in this file
3. ⚠️ Test with the fallback for button 3
4. Document the multi-page menu limitation in spec

### Medium Term (Next Steps):
1. **Improve Text Detection**: Use OCR-guided text region expansion instead of fixed 2.5×
2. **Multi-Frame Extraction**: Sample multiple timestamps from menu VOBs
3. **Frame Differencing**: Implement highlight detection using frame comparison
4. **Better Fallback**: For missing buttons, use coordinates from similar buttons

### Long Term (Future Work):
1. **NAV Pack Deep Dive**: Fully parse BTN_IT command tables for button navigation
2. **PGC Command Parsing**: Understand menu page transitions
3. **SPU Stream Decoding**: Decode subpicture during menu "playback" simulation
4. **Template Matching**: Use reference highlight images to find button positions

## Test Command

```bash
uv run dvdmenu-extract "C:\Users\Assaf\program\DVD-Archaeology\DVD_Sample_01\" \
  --out "C:\Users\Assaf\Desktop\Temporary\DVD_Sample_01" \
  --use-real-ffmpeg --overwrite-outputs --force
```

## Current Output

### Button Images:
- **btn1.png**: ❓ (needs verification)
- **btn2.png**: ✅ Shows correct thumbnail + text
- **btn3.png**: ⚠️ Uses fallback rect (button on page 2)

### Extracted Videos:
- **DVD_Sample_01_0.mkv**: 5.2 MB, 22.2s ✅
- **DVD_Sample_01_1.mkv**: 5.4 MB, 14.4s ⚠️ (expected 25.2s - verification failed)
- **DVD_Sample_01_2.mkv**: 8.1 MB, 37.8s ✅

## Key Insight: Pattern B Menu

According to PROJECT_SPEC.md, this is a **Pattern B** menu:

> ### Pattern B: Text baked into background
> - Menu text is part of the background video/image.
> - SPU overlays contain only highlight masks or button geometry (no glyphs).
> - In this case, OCR must be constrained to the button's logical selection area.

**For DVD_Sample_01:**
- Text labels ("Track #1", "ðø+2") are baked into background ✅
- Thumbnails are baked into background ✅
- SPU highlight is separate layer (yellow overlay) ✅
- But: No button rectangles in IFO, must detect visually ⚠️

This is actually a **hybrid**: Pattern B menu (text in background) but WITHOUT explicit button geometry, requiring visual detection fallback.
