# Project: DVD Menu–Aware Episode Extractor (Python)

## Goal
Build a pipeline tool that extracts episodes/chapters from home-authored DVDs (and later VCD/SVCD), even when content is stored as one large VOB, and names each extracted segment using OCR’d menu text (English + Hebrew). The pipeline must be inspectable, restartable, and testable stage-by-stage.

This is NOT a media “guesser”: episode boundaries must come from disc navigation data when available (DVD PGC/cell/button mappings). FFmpeg may be used for extraction and optional conservative stream repair, but must never decide boundaries.

## Core requirements
1) Split a disc/title into multiple episode files.
2) Map each episode segment to the correct menu item/button.
3) OCR menu button text (ENG + HEB), sanitize it, and name output files accordingly.
4) Produce a manifest JSON that is the single source of truth and enables re-running individual stages.

## Strong emphasis
- Defensive programming: heavy use of asserts, explicit validations, and clear failure modes.
- Test-first: each stage must have unit tests, even if initially it’s a stub with synthetic fixtures.
- Stubs per stage: the initial goal is a fully working “empty” pipeline that runs end-to-end using mock/fake data, then progressively replaces stubs with real implementations.
- Every stage writes artifacts to disk (JSON/logs/images) for debugging and caching.
- Assume that DVD is only one implementation of a more general menu-driven media model.
- Downstream stages must not import DVD-specific modules or reference DVD-only types.

## Format extensibility requirement (DVD, VCD, SVCD, future)

The system MUST be designed to support multiple disc formats with similar-but-not-identical
navigation models (DVD now; VCD/SVCD later).

### Design principles
- The pipeline stages MUST remain conceptually the same across formats:
  ingest → navigation → menu mapping → OCR → segments → extract → manifest
- Format-specific logic MUST be isolated behind explicit interfaces or adapters.
- No stage beyond `ingest` and `nav_parse` may assume DVD-specific structures
  (e.g., PGCs, VTS, IFO files).

### Format capability differences
Different formats may provide different capabilities:
- DVD: explicit menu buttons, PGCs, cell boundaries, SPU overlays
- VCD/SVCD: track-based navigation, entry points, simpler or implicit menus
- Some formats may lack:
  - explicit menu domains
  - button geometry
  - subpicture overlays

The code MUST represent missing capabilities explicitly rather than assuming failure.

### Required abstraction
- Introduce a `DiscFormat` or `NavigationModel` abstraction that exposes:
  - logical menu entries (if any)
  - targets (track / time range / segment)
  - optional selection areas
- Downstream stages MUST operate on this abstract model, not on raw DVD concepts.

### OCR implications
- OCR logic must operate on a generic `MenuEntry` abstraction:
  - entry_id
  - optional selection_rect
  - optional highlight_info
  - associated visual region(s)
- Formats without explicit button rectangles must still produce deterministic
  OCR regions (e.g., fixed layout rules or track labels).

### Non-goal for v0
- Full VCD/SVCD support is NOT required in v0.
- The goal is architectural readiness: adding a new format should require
  implementing a new `nav_parse` adapter and test fixtures, not rewriting stages.



## Tech constraints / assumptions (v0)
- Python 3.11+
- CLI entrypoint (Typer or argparse)
- pytest for tests
- No external web calls
- Disc input is a folder path (e.g., VIDEO_TS). We will not implement ISO mounting in v0.
- OCR engine targeted: Tesseract (invoked via pytesseract), with languages "eng+heb" (must be optional and gracefully handled if missing).

## Pipeline architecture (MUST IMPLEMENT)
Pipeline stages should be explicit and individually runnable:

Stage A: ingest
- Input: path to disc folder
- Output: out/ingest.json (disc type guess, paths, basic sanity checks)

Stage B: nav_parse (stub first)
- Input: ingest.json
- Output: out/nav.json (titles/vts/pgc/cell structure + menu domains)
- v0 stub: return synthetic structure from fixtures.

Stage C: menu_map (stub first)
- Input: nav.json
- Output: out/menu_map.json (menu_id -> list of buttons with rect + target PGC/cell)
- v0 stub: return synthetic menu/button mapping from fixtures.

Stage D: menu_images (stub first)
- Input: menu_map.json
- Output: out/menu_images/{button_id}.png + out/menu_images.json (paths + metadata)
- v0 stub: copy fixture PNGs.

Stage E: ocr (stub first, real OCR optional)
- Input: menu_images.json
- Output: out/ocr.json (button_id -> raw_text + cleaned_label + confidence)
- v0 stub: read fixture text files; real OCR behind a flag.

Stage F: segments
- Input: nav.json + menu_map.json
- Output: out/segments.json (button_id -> start/end timestamps OR cell list)
- v0: compute from fixtures; real later.

Stage G: extract
- Input: segments.json + ocr.json
- Output: episodes/*.mkv + out/extract.json + logs/*.log
- v0 stub: create empty placeholder files named correctly.
- Later: real FFmpeg extraction/remux with optional --repair.

Stage H: finalize
- Input: all previous outputs
- Output: out/manifest.json (single merged manifest; stable schema)
- Must include: inputs, detected disc info, each button label, segment boundaries, output filename, and stage statuses.

## CLI requirements
Implement a CLI command:
dvdmenu-extract <INPUT_PATH> --out <OUT_DIR> [--ocr-lang eng+heb] [--use-real-ocr] [--use-real-ffmpeg] [--repair off|safe] [--stage <stage_name>] [--force]

- Default runs full pipeline.
- --stage runs only one stage (and asserts required upstream artifacts exist).
- Must have clear error messages and non-zero exit codes.
- Must never silently succeed if a required artifact is missing or malformed.

## Defensive programming requirements
- Use dataclasses / pydantic-style validation (choose one) for reading/writing JSON artifacts.
- Every stage must validate its inputs and outputs with explicit assertions:
  - file exists
  - schema matches expected
  - ids are unique
  - timestamps are non-negative and increasing
  - output paths stay inside OUT_DIR
- Add invariants: e.g., every button in menu_map must have an OCR record and a segment record by finalize stage.

## Testing requirements (MANDATORY)
Use pytest. Create tests for:
- Artifact schemas roundtrip (write -> read -> equals)
- Each stage “stub run” produces expected outputs from fixtures
- Pipeline end-to-end in stub mode creates manifest.json and episode placeholders
- Failure tests:
  - missing upstream artifact raises a clear exception
  - invalid schema causes failure
  - duplicate button IDs rejected
  - negative timestamps rejected
- Add snapshot-like tests for manifest schema stability.

Fixtures:
- tests/fixtures/disc_minimal/ (fake VIDEO_TS)
- tests/fixtures/menu_buttons/ (PNG images)
- tests/fixtures/expected/*.json

## Repo layout (please create)
src/dvdmenu_extract/
  __init__.py
  cli.py
  pipeline.py
  stages/
    ingest.py
    nav_parse.py
    menu_map.py
    menu_images.py
    ocr.py
    segments.py
    extract.py
    finalize.py
  models/
    ingest.py
    nav.py
    menu.py
    ocr.py
    segments.py
    manifest.py
  util/
    io.py
    paths.py
    assertx.py
tests/
  test_pipeline_stub_e2e.py
  test_stage_ingest.py
  test_stage_nav_parse.py
  ...
  fixtures/...

## Implementation notes
- Start by implementing the full stub pipeline with deterministic fixtures so it runs in <2 seconds in CI.
- Keep real integrations (libdvdnav bindings, SPU extraction, FFmpeg extraction, real OCR) behind feature flags, with stubs as the default.
- Log every stage start/end and write stage metadata (duration, inputs, outputs).
- Use type hints everywhere; enable mypy later (optional).
- Ensure Windows-friendly paths (no assumptions about /mnt or symlinks).

## Deliverable for this iteration
A working CLI that runs the full pipeline in stub mode and produces:
- out/manifest.json
- out/menu_images/*.png (from fixtures)
- episodes/*.mkv placeholder files named from OCR labels
- a passing pytest suite that covers each stage and the end-to-end stub pipeline.



“Please scaffold the project exactly as described, including repo layout, stub pipeline stages, and pytest tests.”


Do not use pip for install or python for running, only "uv add" and "uv run".


Assertion requirement:
- For every menu button, exactly one of the following must be true:
  - SPU OCR produced non-empty text
  - Background OCR was attempted


## Menu text extraction: dual-path requirement (MANDATORY)

DVD menus use two common authoring patterns, both of which MUST be supported:

### Pattern A: Text in SPU overlay
- Menu text is rendered as part of the DVD sub-picture (SPU).
- Highlighting changes text color/state.
- OCR should be performed directly on the SPU bitmap within the button region.

### Pattern B: Text baked into background
- Menu text is part of the background video/image.
- SPU overlays contain only highlight masks or button geometry (no glyphs).
- In this case, OCR must be constrained to the button’s logical selection area as defined by DVD navigation data. Highlight masks are visual-only and must not be used to limit OCR regions.

In practical terms:
button.selection_rect   ← primary crop
button.highlight_mask   ← ignore for OCR, useful for diagnostics
menu.background_frame   ← pixel source (if SPU has no text)




### Design rules
- Button geometry (rectangles / masks) from DVD navigation data is the authoritative source
  for where OCR is allowed.
- OCR must NEVER guess text outside the button region.
- Episode structure (boundaries, mapping) must be independent of OCR success or failure.
- OCR is used only for naming/labeling, not segmentation.

### Implementation requirements
- The OCR stage MUST implement a two-step strategy:
  1. Attempt OCR on SPU overlay content inside the button region.
  2. If SPU content is empty or non-textual, fallback to OCR on background content cropped
     to the same region.
- The OCR output MUST record which path was used (`"source": "spu"` or `"source": "background"`).
- Failure to extract text MUST NOT fail the pipeline; a deterministic fallback label must be used.

This dual-path behavior must be represented explicitly in data models, tests, and manifests.

Before implementing real logic, confirm that the stub pipeline runs end-to-end and all tests pass.

From now on, do not remove asserts or tests unless explicitly instructed. Prefer failing fast over silent recovery.


## Optional format support: SVCD (VCD 2.0 family) — ARCHITECTURE READY

We must support future SVCD discs whose structure differs from DVD.
SVCD uses ISO9660 directories and a VCD/SVCD Playback Control (PBC) model,
not DVD IFO/PGC/button-rectangle navigation.

### How to detect SVCD input
Treat input as SVCD if it contains:
- /SVCD/INFO.SVD and /SVCD/ENTRIES.SVD (required SVCD information area files)
- /MPEG2/AVSEQ*.MPG (main tracks)
Optionally:
- /SVCD/PSD.SVD and /SVCD/LOT.SVD (PBC control)
- /SEGMENT/ITEM*.MPG (segment play items, often used for menus/stills)
- /SVCD/SEARCH.DAT and/or /EXT/SCANDATA.DAT (seek/index info)

### SVCD navigation model (high-level)
- "Episodes" are typically represented as:
  - Tracks: MPEG2/AVSEQnn.MPG
  - Entry points into tracks: ENTRIES.SVD (mm:ss:ff addresses)
  - PBC lists and selection logic: PSD.SVD + LOT.SVD (selection lists/play lists/end lists)
- Unlike DVD, SVCD may NOT provide button rectangles/highlight masks.
  Therefore, our core pipeline must operate on an abstract NavigationModel and MenuEntry model.

### Required abstraction changes (MUST)
Create a format-neutral NavigationModel:
- DiscFormat: DVD | SVCD | UNKNOWN
- MenuEntry:
  - entry_id (stable string)
  - target: TrackTarget(track_no) OR TimeRangeTarget(track_no, start, end) OR SegmentItemTarget(item_no)
  - selection_rect: Optional[Rect]  (DVD often has; SVCD often None)
  - visuals: list[VisualRegion] (may reference a segment still/item or a captured frame)
- Downstream stages (OCR, segments, extract, manifest) MUST only use MenuEntry/Target abstractions,
  never DVD-specific PGC/VTS terms.

### SVCD implementation plan (v1: pragmatic; v2: native)
v1 (fast, reliable): Use external GNU VCDImager tools via subprocess:
- Prefer `vcd-info` to parse SVCD PBC/entries/tracks and output a machine-readable summary
  (we will parse its output into our NavigationModel).
- Optionally use `vcdxrip` for extraction support (if helpful), but FFmpeg remains the extractor.

v2 (native): Replace subprocess parsing with direct parsing of SVCD binaries:
- ENTRIES.SVD: entry points pe

### SVCD support on Windows (implementation strategy)

There is no required pip-first Python library that reliably decodes SVCD PBC/menu structures.
Therefore SVCD support MUST be implemented behind an adapter interface with two backends:

Backend 1 (v1, default on Windows): `VcdImagerCliBackend`
- Use subprocess to call VCDImager/libvcdinfo tools (e.g. vcd-info) to extract:
  - tracks (MPEG2/AVSEQnn.MPG)
  - entry points (ENTRIES.SVD-derived)
  - PBC graph (selection/play/end lists) when present
- Parse tool output into the format-neutral NavigationModel.

Backend 2 (v2, optional): `LibVcdInfoBackend`
- Wrap a native libvcdinfo build via ctypes/cffi (Windows DLL) to avoid subprocess.
- Must match Backend 1’s output schema exactly.

Non-goal: perfect OCR-based visual menu reconstruction for SVCD in v1.
Goal: deterministic extraction using tracks + entry points; OCR is optional naming.

SVCD stages must not reference DVD concepts (PGC/VTS/IFO/SPU). They must only emit MenuEntry/Target abstractions.

vcd-info is used to build NavigationModel (tracks, entry points, PBC presence).

Visual assets are derived by:

Prefer frames from SEGMENT/ITEM*.MPG (menu stills/pages).

Fallback to sampled frames from AVSEQ*.MPG near entry points.

No assumptions about highlight rectangles; OCR regions may be full-frame or deterministic crops (configurable), because SVCD typically lacks DVD-style button geometry.


### SVCD tooling wrapper requirement (MUST)

Implement a stable Python wrapper around VCDImager tooling:
- Primary tool: vcd-info (for probing disc format, tracks, entries, search/scandata)
- Optional structured source: vcdxrip generating an XML descriptor for more reliable parsing.

The wrapper MUST:
1) Provide a Python-native API (classes/functions) that returns validated dataclasses.
2) Persist raw stdout/stderr logs to out/raw/ for debugging.
3) Emit a normalized, versioned JSON artifact out/svcd_nav.json that the rest of the pipeline consumes.
4) Be defensive: timeouts, non-zero exit handling, tool-not-found handling, strict schema validation.
5) Never leak raw CLI output to downstream pipeline stages.

Design:
- `dvdmenu_extract.backends.svcd_vcdimager.VcdImagerCliBackend`
- `dvdmenu_extract.util.process.run_process(...)`
- Dataclasses in `dvdmenu_extract.models.svcd_nav`
- Unit tests with fixtures that simulate stdout/stderr and validate parsing + error handling.

