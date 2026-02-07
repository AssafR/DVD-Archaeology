# NAV Parse PGC Validation

**Status:** ✅ Adopted  
**Audience:** Maintainers, nav_parse developers, QA  
**Scope:** DVD menu button extraction (nav_parse, VTSM/VMGM PGC tables)

## Why

Some discs ship with empty or garbage VTSM PGC tables (e.g., menus defined only in VMGM). When we fall back to NAV-pack scanning, a bogus `nb_pgc` or out-of-bounds PGC offsets can trigger repeated scans with zero rectangles, effectively hanging the stage. We now validate the PGC table structure before scanning, so malformed data is skipped deterministically.

## Validation Rules (deterministic, no heuristics)

1) **Table bounds:** `pgc_table_start + 8 + nb_pgc * 8` must fit inside the IFO.  
2) **Entry offsets:** Each PGC start offset must be:
   - Non-zero
   - ≥ `pgc_table_start`
   - < file size
   - Monotonic (increasing) to avoid overlapping/rewinding entries  
3) **Minimum header:** Each PGC must fit at least the common 0x00EC header.  
4) **Button table presence:** At least one PGC must expose a non-empty, in-bounds button table (using the standard offsets 0x00E6/0x00EA/0x00E4).  
5) **Fallback behavior:** If validation fails, the VTSM navpack/SPU scan path is skipped early; downstream VMGM/title fallbacks remain unchanged. A 30s cumulative time budget remains as a safety net during scanning.

## Implementation Notes

- Implemented in `_validate_pgc_table()` and `_pgc_button_table_sane()` in `src/dvdmenu_extract/util/dvd_ifo.py`.
- Both VTSM NAV-pack scanning and VTSM SPU scanning invoke this validation before iterating PGCs.
- Logging:
  - `warning` for table/PGC rejection or missing sane button tables.
  - `debug` for per-PGC structural issues (out-of-bounds, non-monotonic, truncated headers).
- The previous `nb_pgc` heuristic cap was removed; only structural validity decides whether we scan.

## Expected Outcomes

- Prevents infinite or long-running navpack scans on discs with malformed/unused VTSM tables.
- Leaves valid discs untouched; no behavior change when structures are sane.
- Provides actionable logs for QA without requiring reproduction under a debugger.

## How to Verify

1) Run `uv run dvdmenu-extract <disc> --stage nav_parse --log-level info`.  
2) For malformed VTSM tables, expect early skip logs and continued fallback to VMGM/title paths.  
3) For valid tables, expect normal navpack/SPU scans; no new warnings emitted.

