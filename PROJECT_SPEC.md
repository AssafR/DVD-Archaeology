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

  - On DVDs, only VTS_xx_1.VOB and higher contain program video; VIDEO_TS.VOB and VTS_xx_0.VOB are menu-only and must never be treated as episode content.

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



## Tech constraints / assumptions
- Python 3.12+
- `pyparsedvd` for robust DVD IFO parsing.
- `ffmpeg` and `ffprobe` for media extraction and timing.
- `pytesseract` (optional) for OCR.
- `pydantic` for schema validation.
- Cross-platform support (Windows/Linux/macOS).
- No external DB; all state in JSON files.

## Pipeline architecture (MUST IMPLEMENT)
Pipeline stages should be explicit and individually runnable:

Stage A: ingest
- Input: path to disc folder
- Output: `ingest.json`, `video_ts_report.json`, `disc_report.json`
- Purpose: Disc type detection, path discovery, and basic sanity checks.

Stage B: nav_parse
- Input: `ingest.json`
- Output: `nav.json`, `nav_summary.json`, `svcd_nav.json`, `vcd_nav.json`, `raw/vcd-info.stdout.txt`, `raw/vcd-info.stderr.txt` (if using vcd-info)
- Purpose: Parse navigation structure (titles, VTS, PGC, cells) and menu domains.

Stage C: menu_map
- Input: `nav.json`
- Output: `menu_map.json`
- Purpose: Map menu IDs to buttons with their coordinates and targets.

Stage D: menu_validation
- Input: `nav.json`, `menu_map.json`
- Output: `menu_validation.json`
- Purpose: Validate the consistency of the menu mapping against the navigation data.

Stage E: timing
- Input: `nav.json`, `ingest.json`, `menu_map.json`
- Output: `timing.json`, `timing_meta.json`
- Purpose: Determine precise start/end timestamps for segments.

Stage F: segments
- Input: `menu_map.json`, `timing.json`
- Output: `segments.json`
- Purpose: Define the final segments to be extracted based on menu buttons and timing.

Stage G: extract
- Input: `segments.json`, `ingest.json`, `menu_map.json`, `nav.json`
- Output: `episodes/*.mkv`, `extract.json`, `logs/*.log`
- Purpose: Extract and remux video segments using FFmpeg.

Stage H: verify_extract
- Input: `segments.json`, `extract.json`
- Output: `verify.json`
- Purpose: Verify the integrity and correctness of the extracted files.

Stage I: menu_images
- Input: `menu_map.json`
- Output: `menu_images.json`, `menu_images/{button_id}.png`
- Purpose: Extract button images from menu domains. When `--use-real-ffmpeg` is enabled, crop from VOB menu frames; optional `Reference/` overrides are used only when `--use-reference-images` is set. Otherwise, use fixtures/placeholders for tests.

Stage J: ocr
- Input: `menu_images.json`
- Output: `ocr.json`
- Purpose: Perform OCR on menu images to extract button labels. Real OCR is the default; use `--use-stub-ocr` for stub mode (which can read reference text files).

Stage K: finalize
- Input: all previous outputs
- Output: `manifest.json`
- Purpose: Merge all artifacts into a single stable manifest. Includes inputs, detected disc info, button labels, segment boundaries, output filenames, and stage statuses.

## CLI requirements
Implement a CLI command:
dvdmenu-extract <INPUT_PATH> --out <OUT_DIR> [--ocr-lang eng+heb] [--use-stub-ocr] [--use-real-ffmpeg] [--repair off|safe] [--stage <stage_name>] [--until <stage_name>] [--from <stage_name>] [--force]

- Default runs full pipeline.
- --stage runs only one stage (and asserts required upstream artifacts exist).
- --until runs all stages from ingest through the given stage.
- --from runs the given stage and all downstream stages.
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

## Repo layout (please create if doesn't exist):
src/dvdmenu_extract/
  __init__.py
  cli.py
  pipeline.py
  stages/
    extract.py
    ingest.py
    nav_parse.py
    menu_map.py
    menu_images.py
    menu_validation.py
    nav_parse.py
    ocr.py
    segments.py
    timing.py
    verify_extract.py
    extract.py
    finalize.py
  models/
    ingest.py
    nav.py
    menu.py
    ocr.py
    segments.py
    nav_summary.py
    segments.py
    svcd_nav.py
    vcd_nav.py
    verify.py
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
- All stages (A-K) are implemented and functional.
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


### DVD content vs menu verification (IFO-based, authoritative)

DVD VOB filenames alone are insufficient to distinguish program content from menus.
The authoritative distinction is defined by DVD navigation data in IFO files.

Each DVD contains Program Chains (PGCs) of different types:
- VMGM PGCs (Video Manager Menu PGCs), defined in VIDEO_TS.IFO, reference disc-level menu video.
- VTSM PGCs (Video Title Set Menu PGCs), defined in VTS_xx_0.IFO, reference title/chapter menu video.
- VTSTT PGCs (Video Title Set Title PGCs), defined in VTS_xx_0.IFO, reference actual program content.

Each PGC consists of cells that map to specific VOB IDs, cell IDs, and sector/time ranges.
Any video referenced by a VTSTT PGC must be treated as program content.
Any video referenced exclusively by VMGM or VTSM PGCs must be treated as menu material.

Implementation rules:
- Parse IFO navigation structures to classify PGCs by type.
- Only VTSTT PGCs may generate extractable titles/episodes.
- Menu PGCs must never generate content outputs, even if they reference playable VOB segments.
- Filename-based heuristics (e.g. ignoring *_0.VOB) are acceptable only as a fallback when IFO parsing is unavailable.

This approach matches DVD specification semantics and avoids misclassifying menu video as content.


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

### SVCD navigation model (high-level)
- "Episodes" are typically represented as:
  - Tracks: MPEG2/AVSEQnn.MPG
  - Entry points into tracks: ENTRIES.SVD (mm:ss:ff addresses)
  - PBC lists and selection logic: PSD.SVD + LOT.SVD (selection lists/play lists/end lists)
- Unlike DVD, SVCD may NOT provide button rectangles/highlight masks.
  Therefore, our core pipeline must operate on an abstract NavigationModel and MenuEntry model.

### SVCD implementation plan
1. **Primary**: Native directory parsing of `EXT`, `SEGMENT`, and `VCD` folders to build the navigation tree.
2. **Secondary (Optional)**: Use `vcd-info` (from `vcdimager`) to extract detailed entry point and track metadata if available.
3. **Extraction**: Use `ffmpeg` to extract tracks from `.MPG` files in the `MPEG2` or `SEGMENT` directories.

### SVCD implementation plan (v1: pragmatic; v2: native)
v1 (fast, reliable): Use external GNU VCDImager tools via subprocess:
- Prefer `vcd-info` to parse SVCD PBC/entries/tracks and output a machine-readable summary
  (we will parse its output into our NavigationModel).
- Optionally use `vcdxrip` for extraction support (if helpful), but FFmpeg remains the extractor.

v2 (native): Replace subprocess parsing with direct parsing of SVCD binaries:
- ENTRIES.SVD: entry points parsing.

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

### DVD menu button extraction limitations

There is no maintained Python library capable of parsing DVD menus down to the level of highlighted buttons.
DVD menu buttons are not stored as explicit geometric metadata; they are rendered at playback time by combining
navigation data (IFO), subpicture bitmap streams (SPU), and player state.

While C/C++ libraries such as libdvdread and libdvdnav expose menu navigation logic and button indices,
they do not provide rendered button geometry or highlight masks in a form suitable for direct extraction.
Full button rendering is implemented only inside DVD players.

Therefore, the system must not attempt to read DVD button geometry directly.
Menu understanding is performed indirectly by:
- parsing IFO navigation structures to identify menu PGCs
- extracting representative menu frames
- applying OCR and visual analysis to infer labels and associations

This approach reflects the actual structure of DVD technology and avoids reimplementing a DVD player.




## Optional format support: VCD 2.0 (White Book) — ARCHITECTURE READY

We must support VCD directory layouts (MPEG-1) in addition to DVD and SVCD.

### Detect VCD input
Treat input as VCD if it contains:
- /VCD/INFO.VCD and /VCD/ENTRIES.VCD (core metadata)
- /MPEGAV/AVSEQ*.DAT (main tracks, MPEG-1 PS in .DAT container)
Optionally:
- /VCD/PSD.VCD and /VCD/LOT.VCD (PBC navigation)
- /SEGMENT/ITEM*.DAT (segment play items for menu stills/pages/intros)
- /EXT/PSD_X.VCD, /EXT/LOT_X.VCD, /EXT/SCANDATA.DAT (extensions/indexing)
- /CDI/* (CD-i compatibility; ignore for extraction)

### VCD navigation model (differences vs SVCD)
- Main tracks are AVSEQnn.DAT under /MPEGAV (not /MPEG2/*.MPG).
- Segments are ITEMnnnn.DAT under /SEGMENT.
- VCD may use PBC via PSD/LOT/ENTRIES, but generally lacks DVD-like button rectangles/highlights.

### VCD implementation strategy
1. **Primary**: Native directory parsing of `VCD` and `SEGMENT` folders.
2. **Secondary (Optional)**: Use `vcd-info` for detailed metadata.
3. **Extraction**: Use `ffmpeg` to extract tracks from `.DAT` files in the `MPEGAV` directory.

### Required abstraction behavior
- Use the same format-neutral MenuEntry/Target abstraction used for SVCD:
  - TrackTarget(track_no) or TimeRangeTarget(track_no, start/end) or SegmentItemTarget(item_no)
  - selection_rect is typically None for VCD
- Downstream stages must not assume DVD-only concepts.

### Media handling requirement
- Treat .DAT files as MPEG program streams; do not rely on filename extension.
- Extraction uses FFmpeg; probes must succeed based on content, not extension.
- OCR visuals:
  - Prefer frames from SEGMENT/ITEM*.DAT for menu pages/stills when present.
  - Fallback to representative frames from AVSEQ*.DAT near entry points if needed.

### Tooling backend
- Extend the VCDImager CLI backend to support BOTH VCD and SVCD:
  - vcd-info is the primary structure probe (format, tracks, entries, PBC presence).
  - Optionally vcdxrip XML for more structured parse later.
- The backend must output a normalized, versioned JSON artifact consumed by the pipeline.


On Windows, vcd-info cannot reliably analyze extracted VCD/SVCD directory trees because it operates at the disc/device abstraction level rather than the filesystem level.
Therefore, the system treats vcd-info as an optional disc-image backend, not a required dependency.

When only a directory tree is available, the default path is a lightweight native parser that reads VCD/SVCD control files directly and produces the same NavigationModel.

Optionally, the system may construct a temporary disc image descriptor (e.g. CUE/BIN or ISO) from the directory and invoke vcd-info against that image as a best-effort enhancement; failure of this step must never block or invalidate the directory-native parsing path.

This behavior reflects limitations of external tooling rather than properties of the underlying VCD/SVCD data.

# Implementation tips:
Do not create temporary artifacts in the log directory.

The project configuration is handled by uv. Do not use pip for install, only "uv add", and to run anything, use "uv run".


