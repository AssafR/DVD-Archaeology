"""
SPU Text Clustering - Group character-level SPU regions into button text lines.

Many DVDs store button text as individual character glyphs in SPU overlays,
not as full button highlight rectangles. This module clusters these tiny
character regions into complete button text bounding boxes.

Algorithm:
1. Sort all character boxes by vertical position (top edge)
2. Group into horizontal text lines (characters with similar Y coordinates)
3. Within each line, merge horizontally adjacent characters
4. Return button-level bounding boxes suitable for OCR

Tested with:
- Friends S09-10: 627 character regions → ~19 button text lines
- Ellen Season 04: 514 character regions → ~15 button text lines
"""

from typing import List, Optional, Tuple


def detect_column_gutter(
    char_rects: List[Tuple[int, int, int, int]],
    frame_w: int,
    min_depth: float = 0.6,
    min_gutter_width: int = 20,
    edge_margin: float = 0.15,
) -> Optional[int]:
    """Detect a vertical column gutter from ALL character components on a page.

    Builds a global horizontal projection (sum of character heights at each X)
    across every character rect, then finds the deepest valley.  Because the
    projection accumulates evidence from ALL rows, a true column gutter (present
    in every row) produces a much stronger valley than any within-text gap that
    varies from row to row.

    Args:
        char_rects: All character-level bounding boxes on the page.
        frame_w:    Width of the frame / bitmap in pixels.
        min_depth:  Minimum relative valley depth (0-1) to accept a gutter.
        min_gutter_width: Minimum width of the zero/low-density region (px).
        edge_margin: Fraction of frame width to exclude at left/right edges
                     so we don't pick a valley at the very edge of text.

    Returns:
        The X coordinate of the gutter centre, or ``None`` when no convincing
        two-column gutter is found.
    """
    if not char_rects or frame_w <= 0:
        return None

    # --- horizontal projection: accumulate character height at each X --------
    x_proj = [0] * frame_w
    for x1, y1, x2, y2 in char_rects:
        cx1 = max(0, min(frame_w - 1, x1))
        cx2 = max(cx1, min(frame_w - 1, x2))
        h = max(1, y2 - y1 + 1)
        for x in range(cx1, cx2 + 1):
            x_proj[x] += h

    # --- smooth to reduce per-character spikes --------------------------------
    window = 11
    half_w = window // 2
    smoothed: List[float] = []
    for x in range(frame_w):
        lo = max(0, x - half_w)
        hi = min(frame_w, x + half_w + 1)
        smoothed.append(sum(x_proj[lo:hi]) / max(1, hi - lo))

    # --- search for the deepest valley inside [left_margin, right_margin] -----
    left_margin = int(frame_w * edge_margin)
    right_margin = int(frame_w * (1.0 - edge_margin))
    if right_margin - left_margin < min_gutter_width + 2:
        return None

    search = smoothed[left_margin:right_margin + 1]
    valley_offset = min(range(len(search)), key=lambda i: search[i])
    valley_x = left_margin + valley_offset
    valley_val = search[valley_offset]

    # peaks on each side
    left_slice = search[:valley_offset]
    right_slice = search[valley_offset + 1:]
    left_peak = max(left_slice) if left_slice else 0.0
    right_peak = max(right_slice) if right_slice else 0.0
    peak = max(left_peak, right_peak)

    if peak <= 0:
        return None

    depth = (peak - valley_val) / peak

    # --- measure gutter width (consecutive low-density samples) ---------------
    tol = valley_val + peak * 0.05  # allow up to 5 % of peak
    gutter = 1
    lx = valley_x - 1
    while lx >= 0 and smoothed[lx] <= tol:
        gutter += 1
        lx -= 1
    rx = valley_x + 1
    while rx < frame_w and smoothed[rx] <= tol:
        gutter += 1
        rx += 1

    # --- both halves must have substantial AND balanced density ----------------
    left_density = sum(smoothed[left_margin:valley_x])
    right_density = sum(smoothed[valley_x + 1:right_margin + 1])
    min_side_density = peak * 3  # at least a few characters worth

    # Balance: the smaller side must be at least 25 % of the larger.
    # This rejects false gutters between a narrow prefix (e.g. "65. 4-3")
    # and a wide text body, while accepting true two-column layouts where
    # both columns carry comparable amounts of text.
    if left_density > 0 and right_density > 0:
        balance = min(left_density, right_density) / max(left_density, right_density)
    else:
        balance = 0.0
    min_balance = 0.25

    if depth < min_depth:
        return None
    if gutter < min_gutter_width:
        return None
    if left_density < min_side_density or right_density < min_side_density:
        return None
    if balance < min_balance:
        return None

    return valley_x


def cluster_character_rects_into_buttons(
    char_rects: List[Tuple[int, int, int, int]],
    line_height_tolerance: int = 10,
    char_spacing_max: int = 20,
    min_button_width: int = 250,  # Episode buttons are wide; nav buttons are narrow
    min_button_height: int = 10,
    max_button_height: int = 40,  # Reject buttons taller than this (likely multi-button capture)
    min_aspect_ratio: float = 10.0,  # Minimum width:height ratio (episode buttons are very wide)
    min_char_count: int = 20,  # Minimum number of character components (filters short nav text)
    padding_left: int = 10,
    padding_top: int = 10,
    padding_right: int = 80,
    padding_bottom: int = 10,
    merge_same_line: bool = True,
    trim_right_small_group: bool = False,
    trim_right_gap_threshold: int = 120,
    trim_right_max_width: int = 160,
    trim_left_small_group: bool = False,
    trim_left_gap_threshold: int = 120,
    trim_left_max_width: int = 160,
    trim_left_max_x: int = 220,
) -> List[Tuple[int, int, int, int]]:
    """
    Cluster character-level bounding boxes into button text lines.
    
    Takes hundreds of tiny character regions from SPU overlay and groups them
    into button-sized bounding boxes suitable for OCR.
    
    Args:
        char_rects: List of (x1, y1, x2, y2) character bounding boxes
        line_height_tolerance: Max Y difference to consider characters on same line (pixels)
        char_spacing_max: Max horizontal gap to merge characters (used if merge_same_line=False)
        min_button_width: Minimum width to consider a valid button (pixels)
        min_button_height: Minimum height to consider a valid button (pixels)
        max_button_height: Maximum height to consider a valid button (pixels) - filters multi-button captures
        min_aspect_ratio: Minimum width:height ratio (filters square/tall nav elements)
        min_char_count: Minimum number of character components in button (filters short nav text)
        padding_left: Extra padding to add to left edge (pixels)
        padding_top: Extra padding to add to top edge (pixels)
        padding_right: Extra padding to add to right edge (pixels)
        padding_bottom: Extra padding to add to bottom edge (pixels)
        merge_same_line: If True, merge ALL characters on same Y line into one button (recommended)
    
    Returns:
        List of (x1, y1, x2, y2) button bounding boxes
    
    Example:
        Input: 320 tiny character boxes (10x17 each)
        Output: 10 button text lines (200x20 each)
    """
    if not char_rects:
        return []
    
    # Step 1: Group characters by vertical position (text lines)
    # Sort by top edge (y1) to process top-to-bottom
    sorted_rects = sorted(char_rects, key=lambda r: (r[1], r[0]))  # Sort by y1, then x1
    
    text_lines: List[List[Tuple[int, int, int, int]]] = []
    current_line: List[Tuple[int, int, int, int]] = [sorted_rects[0]]
    current_y = sorted_rects[0][1]  # y1 of first rect
    
    for rect in sorted_rects[1:]:
        x1, y1, x2, y2 = rect
        
        # Check if this character is on the same text line
        # (within line_height_tolerance of current line's Y position)
        if abs(y1 - current_y) <= line_height_tolerance:
            # Same line
            current_line.append(rect)
        else:
            # New line - save current line and start new one
            if current_line:
                text_lines.append(current_line)
            current_line = [rect]
            current_y = y1
    
    # Add last line
    if current_line:
        text_lines.append(current_line)
    
    # Step 2: Within each text line, merge horizontally adjacent characters
    button_rects: List[Tuple[int, int, int, int]] = []
    
    for line_chars in text_lines:
        # Sort characters in this line by X position (left to right)
        line_chars_sorted = sorted(line_chars, key=lambda r: r[0])
        
        if merge_same_line:
            # SIMPLE APPROACH: Merge ALL characters on this line into ONE button
            # This handles text with wide gaps like "220 10.02... Fine  (PART 1)"
            # where there's a large visual gap but it's still one button text
            
            # Check character count FIRST (filters short nav text like "'")
            char_count = len(line_chars_sorted)
            if char_count < min_char_count:
                continue  # Skip buttons with too few characters
            
            # Find bounding box of entire line (WITHOUT padding first)
            x1_raw = min(r[0] for r in line_chars_sorted)
            y1_raw = min(r[1] for r in line_chars_sorted)
            x2_raw = max(r[2] for r in line_chars_sorted)
            y2_raw = max(r[3] for r in line_chars_sorted)

            # Optional: trim a small, far-right text group (e.g., a side button)
            if trim_right_small_group or trim_left_small_group:
                def _split_groups(gap_threshold: int) -> List[List[Tuple[int, int, int, int]]]:
                    groups: List[List[Tuple[int, int, int, int]]] = []
                    current_group = [line_chars_sorted[0]]
                    for rect in line_chars_sorted[1:]:
                        gap = rect[0] - current_group[-1][2]
                        if gap > gap_threshold:
                            groups.append(current_group)
                            current_group = [rect]
                        else:
                            current_group.append(rect)
                    if current_group:
                        groups.append(current_group)
                    return groups

                left_groups = _split_groups(trim_left_gap_threshold)
                right_groups = _split_groups(trim_right_gap_threshold)

                if len(left_groups) >= 2 or len(right_groups) >= 2:
                    left_group = left_groups[0]
                    right_group = right_groups[-1]
                    left_x1 = min(r[0] for r in left_group)
                    left_x2 = max(r[2] for r in left_group)
                    left_width = left_x2 - left_x1
                    right_x1 = min(r[0] for r in right_group)
                    right_x2 = max(r[2] for r in right_group)
                    right_width = right_x2 - right_x1
                    trimmed_left = False
                    if (
                        trim_left_small_group
                        and len(left_groups) >= 2
                        and left_width <= trim_left_max_width
                        and left_x2 <= trim_left_max_x
                        and right_width >= 220
                    ):
                        x1_raw = right_x1
                        y1_raw = min(r[1] for r in right_group)
                        x2_raw = right_x2
                        y2_raw = max(r[3] for r in right_group)
                        trimmed_left = True
                    if (
                        trim_right_small_group
                        and len(right_groups) >= 2
                        and right_width <= trim_right_max_width
                        and not trimmed_left
                    ):
                        x1_raw = min(r[0] for r in left_group)
                        y1_raw = min(r[1] for r in left_group)
                        x2_raw = left_x2
                        y2_raw = max(r[3] for r in left_group)
            
            # Check size constraints BEFORE padding (filters nav buttons correctly)
            raw_width = x2_raw - x1_raw
            raw_height = y2_raw - y1_raw
            aspect_ratio = raw_width / raw_height if raw_height > 0 else 0
            
            # Filter: too small, too tall, wrong aspect ratio
            if (raw_width >= min_button_width and 
                raw_height >= min_button_height and
                raw_height <= max_button_height and
                aspect_ratio >= min_aspect_ratio):
                # Add padding AFTER size check passes
                x1 = max(0, x1_raw - padding_left)
                y1 = max(0, y1_raw - padding_top)
                x2 = x2_raw + padding_right
                y2 = y2_raw + padding_bottom
                
                button_rects.append((x1, y1, x2, y2))
        
        else:
            # COMPLEX APPROACH: Split line into buttons by horizontal gaps
            # Use when buttons can appear side-by-side on same Y coordinate
            button_groups: List[List[Tuple[int, int, int, int]]] = []
            current_group = [line_chars_sorted[0]]
            
            for i in range(1, len(line_chars_sorted)):
                prev_rect = line_chars_sorted[i-1]
                curr_rect = line_chars_sorted[i]
                
                # Check horizontal gap between characters
                gap = curr_rect[0] - prev_rect[2]  # x1_curr - x2_prev
                
                if gap <= char_spacing_max:
                    # Close enough - same button
                    current_group.append(curr_rect)
                else:
                    # Too far - new button
                    if current_group:
                        button_groups.append(current_group)
                    current_group = [curr_rect]
            
            # Add last group
            if current_group:
                button_groups.append(current_group)
            
            # Compute bounding box for each button group
            for group in button_groups:
                if not group:
                    continue
                
                # Find raw bounds WITHOUT padding first
                x1_raw = min(r[0] for r in group)
                y1_raw = min(r[1] for r in group)
                x2_raw = max(r[2] for r in group)
                y2_raw = max(r[3] for r in group)
                
                # Check size constraints BEFORE padding
                raw_width = x2_raw - x1_raw
                raw_height = y2_raw - y1_raw
                aspect_ratio = raw_width / raw_height if raw_height > 0 else 0
                
                # Filter: too small, too tall, wrong aspect ratio
                if (raw_width >= min_button_width and 
                    raw_height >= min_button_height and
                    raw_height <= max_button_height and
                    aspect_ratio >= min_aspect_ratio):
                    # Add padding AFTER size check passes
                    x1 = max(0, x1_raw - padding_left)
                    y1 = max(0, y1_raw - padding_top)
                    x2 = x2_raw + padding_right
                    y2 = y2_raw + padding_bottom
                    
                    button_rects.append((x1, y1, x2, y2))
    
    return button_rects


def cluster_spu_rects_by_page(
    spu_results: List[Tuple[int, Tuple[int, int, int, int]]],
    **clustering_params,
) -> List[Tuple[int, Tuple[int, int, int, int]]]:
    """
    Cluster character-level SPU rectangles into button text lines, preserving page info.
    
    Takes output from SPU extraction (page_index, rect) and clusters the rectangles
    on each page separately, returning (page_index, clustered_rect) for each button.
    
    Args:
        spu_results: List of (page_index, (x1, y1, x2, y2)) from SPU extraction
        **clustering_params: Optional parameters for cluster_character_rects_into_buttons()
    
    Returns:
        List of (page_index, (x1, y1, x2, y2)) with clustered button rectangles
    
    Example:
        Input: [(0, char_rect1), (0, char_rect2), ..., (1, char_rect320), ...]
        Output: [(0, button1), (0, button2), ..., (1, button10), ...]
    """
    # Group by page
    pages: dict[int, List[Tuple[int, int, int, int]]] = {}
    for page_idx, rect in spu_results:
        if page_idx not in pages:
            pages[page_idx] = []
        pages[page_idx].append(rect)
    
    # Cluster each page separately
    clustered_results: List[Tuple[int, Tuple[int, int, int, int]]] = []
    
    for page_idx in sorted(pages.keys()):
        char_rects = pages[page_idx]
        button_rects = cluster_character_rects_into_buttons(char_rects, **clustering_params)
        
        # Add page index back
        for rect in button_rects:
            clustered_results.append((page_idx, rect))
    
    return clustered_results
