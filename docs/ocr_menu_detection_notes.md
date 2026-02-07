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
