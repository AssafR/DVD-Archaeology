OCR Menu Detection Notes
========================

Scope
-----
- Captures what we tried for SPU/video-based button rect detection (esp. DrWho/Ellen cases).
- Records failure modes and why each attempt didn’t hold up, to inform a fresh design.

Baseline Pipeline (relevant parts)
----------------------------------
- SPU overlay extraction: connected components -> text clustering -> per-page rects.
- Row grouping: Y-projection bands; per-band x_min/x_max span; optional splits.
- Mapping: visual order (header, left top-down, right top-down) used as fallback when SPU rects exist; BTN_IT only when no rects.
- OCR: prefer SPU crops; primary-frame OCR as fallback.

Attempts & Outcomes
-------------------
1) Fixed mid-frame split for non-header rows
   - Rationale: stable two-column split; avoid noisy valley.
   - Failure: DrWho row spanning most of the frame got split into two buttons (btn3/btn4 duplicate “102…”). Gap not clean; mid-split was arbitrary.

2) Gap-based merge (min_gap <= 12 or overlap > 0)
   - Rationale: merge when components touch/overlap.
   - Outcome: SPU stayed at 14, but DrWho row still split—gap was larger than 12 even though visually one row.

3) Wide-row merge with modest gutter (span >= 55%, gap < 40/60/90/150)
   - Rationale: treat wide rows with small gutter as single.
   - Outcome: With moderate gaps (40–90) split persisted; with 150 sometimes SPU stayed 14, sometimes split persisted. Increasing too far risks merging true two-column rows.

4) Force-single for wide upper-half rows
   - Rationale: keep header-like/wide rows single.
   - Failure: Dropped SPU button count (12) → heuristic frame fallback → bad OCR. Too aggressive; removed needed splits.

5) Two-component + high vertical-overlap merge
   - Rationale: merge only when exactly two comps nearly aligned vertically.
   - Outcome: SPU stable at 14 but DrWho still split; gap remained above threshold.

6) Heuristic frame-based fallback (horizontal projection bands)
   - Rationale: when SPU insufficient, find text bands in frames.
   - Failure: for DrWho this produced fewer/misaligned rects; OCR degraded (gibberish). Good only as last resort.

Key Observations
----------------
- SPU masks can span most of the frame with a non-empty gutter; fixed center splits are brittle.
- True SPU buttons should not overlap; gutter size can be large yet still belong to one visual row.
- Forcing single based on span/position can reduce button count and trigger heuristic fallback.
- Mapping by visual order works when rect set is correct; BTN_IT ordering causes misalignment for two-column layouts.
- Primary-frame OCR helps avoid SPU mask artifacts but cannot fix wrong rect splits.

Open Problems / Requirements
----------------------------
- Need a robust split/merge decision per band based on actual gutter size, not fixed mid-line.
- Preserve SPU button count (avoid falling back) while merging over-split bands.
- Generalize to two-column menus (clear gutters) vs. single wide rows (header or wide band).
- Keep mapping visual-order first; BTN_IT only when rects missing.

Candidate Directions
--------------------
- Gap-threshold split: compute min horizontal gap in a band; if gap < T (absolute or % of frame) -> merge; else split. Choose T to allow wide single rows but keep clear two-column gutters.
- Valley-based split with smoothing: project foreground pixels horizontally within the band; split at strongest valley only if valley depth is significant vs. peaks.
- SPU-guided center/width checks: require both halves to exceed min width/height after split; otherwise keep single.
- Stability guard: if split reduces SPU button count below expected, revert to merged band for that page.

Recent Findings & Failures
----------------------------
- Added column-aware row splitting and reordered rects by visual bands, but the new ordering no longer matched `btn1..btnN`, so every column-layout regression (Ellen S4, Entourage Emmy 2005, Friends S09-10) failed with shifted OCR results even though the crops were correct.
- Attempted to permute the detection order back to navigation order by reusing the original list, but the nav mapping still didn’t align and the same misalignment persisted.
- The root issue is that `menu_images` now tracks rects purely by visual layout, yet downstream stages still expect the BTN_IT/nav order. Unless we map each rect back to its canonical button index (or permute the list back before storing `fallback_rects`), the pipeline will keep assigning the wrong crop to each `btnN`.
- Previous state: Claudius 9-13 passes (visual ordering happened to match), but Ellen/Entourage/Friends still fail. The new heuristics must include an explicit permutation step that aligns visual rects with BTN_IT indices before producing menu images.

Implemented Solution: Global Gutter Detection + Per-Column Clustering
---------------------------------------------------------------------

### Root Cause

The per-band `_split_rows_into_columns()` approach was fundamentally fragile for
character-level SPU with two-column layouts (e.g. Dr Who Confidential).  Three
interacting flaws caused failures:

1. **Fragile per-band splitting** -- the valley analysis operated on one merged
   row at a time, so a single wide label ("102 The Good The Bad The Ugly") or
   navigation glyphs sharing the same Y coordinates would weaken or obscure the
   gutter signal.
2. **Ordering destroyed** -- `_split_rows_into_columns()` returned column-major
   order, but the subsequent `page_rects.sort(key=(Y, X))` converted it back to
   row-major, misaligning with the expected BTN_IT ordering.
3. **Synthetic companion rects** -- the old row-pairing code could fabricate
   phantom left-companion rectangles when a row had only one button, creating
   extra/duplicate entries.

### Design

Detect the column gutter **once at the page level** from ALL character
components, **before** merging characters into buttons.  Then cluster characters
per-column independently.

    SPU Characters
        -> Global X-projection
        -> Strong gutter?
            Yes -> Partition chars into left / right groups
                    -> Cluster left group  -> left button rects
                    -> Cluster right group -> right button rects
                    -> Order: header, all-left, all-right
            No  -> Single-column clustering (unchanged behaviour)

The global projection accumulates evidence from every row, so only a **true**
column gutter (consistent across many rows) produces a strong valley.
Within-text gaps vary by row and cancel out.

### Key Changes

1. **`detect_column_gutter()`** (`spu_text_clustering.py`) -- builds a smoothed
   horizontal projection from ALL character rects on the page, finds the deepest
   valley in the central region, and returns the gutter X coordinate (or `None`).
   Requires: relative depth >= 60%, gutter width >= 20px, both sides have
   substantial and balanced character density (min 25% balance ratio).

2. **Column-aware clustering** (`menu_images.py`, character-level SPU path) --
   when a gutter is detected, characters in the top ~15% of Y range that span
   both sides of the gutter are treated as header text and clustered separately.
   Remaining characters are partitioned into left/right groups by their centre X
   relative to the gutter, each group is clustered with relaxed thresholds
   (`min_button_width=60`, `min_char_count=4`), and the final order is
   header -> left (top-to-bottom) -> right (top-to-bottom).

3. **Skip legacy column splitting** -- when column-aware clustering is active,
   `_split_rows_into_columns()` is bypassed entirely, along with the row-major
   re-sort that would destroy the ordering.

4. **Simplified multi-page alignment** -- `_detect_menu_rects_multi_page()` now
   trusts the ordering from `_extract_spu_button_rects()` and only performs
   frame-alignment (median y-shift via OCR line boxes) and height regularisation
   (IQR-based outlier-safe normalisation).  The old row-pairing code that
   synthesised phantom companion rects has been removed.

### Regression Safety

| Test                    | SPU Type        | Layout        | Impact                                               |
| ----------------------- | --------------- | ------------- | ---------------------------------------------------- |
| Dr Who Confidential     | Character-level | Two-column    | **Fixed** -- global gutter detects columns correctly  |
| Ellen S04               | Character-level | Single-column | No change -- no gutter found, same clustering path   |
| Friends S09-10          | Character-level | Single-column | No change -- no gutter found                         |
| Entourage Emmy 2005     | Character-level | Unknown       | Safe -- gutter detection is conservative             |
| Claudius 9-13           | Large-component | Single-column | No change -- large-component path unchanged          |

For single-column menus, `detect_column_gutter()` returns `None` because there
is no consistent vertical gap across all rows.  The pipeline falls through to
the existing single-column clustering, producing identical results.
