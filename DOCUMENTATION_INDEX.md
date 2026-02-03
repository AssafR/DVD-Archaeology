# Documentation Index

**Last Updated:** 2026-02-01  
**Status:** ✅ Production Ready with Comprehensive Documentation

## Overview

This index catalogs all project documentation, including implementation guides, research notes, testing procedures, and design decisions. The documentation covers the complete DVD extraction pipeline from SPU button detection to OCR text extraction.

## Documentation Structure

### 📚 Core Features Documentation

#### OCR Text Extraction (Updated 2026-02-01)

##### OCR Improvements Guide ⭐ NEW
**File:** `OCR_IMPROVEMENTS.md`  
**Purpose:** OCR preprocessing enhancements and testing methodology  
**Contents:**
- Problem statement and improvements implemented
- Vertical padding increase (2x)
- Character blacklist ("|" artifact removal)
- Test methodology and results (3 configurations evaluated)
- Trade-off analysis (why 3x magnification was rejected)
- Current accuracy metrics (67% perfect, 33% minor issues)
- Remaining challenges and future work

**Audience:** Developers working on OCR accuracy, maintainers

##### OCR Regression Testing Framework ⭐ UPDATED 2026-02-01
**File:** `OCR_REGRESSION_FRAMEWORK_GUIDE.md`  
**Purpose:** Complete guide to generalized, auto-discovering OCR regression testing  
**Contents:**
- Auto-discovery system (just drop in JSON files!)
- Primary + backup source paths
- Baseline management and approval workflow
- Known issues tracking per button
- Detailed JSON + Markdown reporting
- Best practices and troubleshooting

**Audience:** Testers, developers, QA engineers

##### Legacy Documentation
**File:** `OCR_REGRESSION_TESTING.md`  
**Purpose:** Original OCR regression testing documentation  
**Status:** Superseded by OCR_REGRESSION_FRAMEWORK_GUIDE.md  
**Note:** Still contains useful historical context and test results

### 📚 Primary Documentation

#### 1. Developer Guide ⭐ START HERE ⭐
**File:** `docs/SPU_BUTTON_EXTRACTION_GUIDE.md`  
**Purpose:** Comprehensive guide for developers working with SPU extraction  
**Contents:**
- Quick start for users and developers
- Complete algorithm walkthrough (7 steps)
- API reference with examples
- Testing and debugging procedures
- Troubleshooting guide
- Performance metrics

**Audience:** Developers, maintainers, contributors

#### 2. Project Specification
**File:** `PROJECT_SPEC.md` (Stage G section)  
**Purpose:** Formal specification of menu_images stage  
**Contents:**
- Button rectangle detection algorithm (SPU + fallback)
- SPU packet structure and format
- Technical implementation details
- Integration with pipeline stages

**Audience:** Architects, technical leads, specification reviewers

#### 3. Implementation Summary
**File:** `SPU_EXTRACTION_IMPLEMENTATION.md`  
**Purpose:** High-level implementation overview and results  
**Contents:**
- Problem solved
- Implementation details summary
- Test results (100% similarity achieved)
- Technical architecture diagram
- Benefits and performance

**Audience:** Project managers, stakeholders, new team members

#### 4. Research Documentation
**File:** `DVD_MENU_HIGHLIGHT_DETECTION_RESEARCH.md`  
**Purpose:** Research process and solution validation  
**Contents:**
- Problem statement
- Approaches tested (static detection, frame diff, hybrid)
- Solution: SPU overlay extraction
- Validation results
- Questions answered

**Audience:** Researchers, algorithm designers, QA team

### 💻 Code Documentation

#### 5. SPU Library Module
**File:** `src/dvdmenu_extract/util/libdvdread_spu.py`  
**Purpose:** Reusable SPU parsing and decoding library  
**Documentation:**
- 60+ line module docstring with examples
- Complete API reference
- SPU packet format specification
- RLE encoding details
- Algorithm overview
- Usage examples

**Functions documented:**
- `parse_spu_control()` - Parse control sequence
- `decode_spu_bitmap()` - Decode RLE bitmap
- `bitmap_connected_components()` - Find regions
- `find_spu_button_rects()` - High-level API
- `iter_spu_packets()` - MPEG-PS iterator
- Helper functions with detailed comments

#### 6. Menu Images Stage
**File:** `src/dvdmenu_extract/stages/menu_images.py`  
**Purpose:** Integration of SPU extraction into pipeline  
**Documentation:**
- `_extract_spu_button_rects()` - 70+ line docstring
  - Complete algorithm description
  - Multi-page handling explanation
  - Validation information
  - Example usage
- `reassemble_spu_packets()` - 50+ line docstring
  - Reassembly algorithm details
  - Critical fix explanation
  - Example with packet sizes
- Inline comments throughout processing loop
  - Step-by-step annotations
  - Rationale for each decision
  - Size threshold explanations
- SPU-to-frame alignment notes
  - OCR-based per-page y-shift (no hardcoded resolution)
  - Fallback behavior when OCR is insufficient
- Button height regularizer
  - IQR-based outlier detection (no fixed pixel thresholds)
  - Resize inlier rects to median height
- Size outlier filter
  - IQR-based removal of low width/height outliers
  - Runs before width-ranking when too many rects
- Low-height outlier filter
  - IQR-based drop of short rects when safe
  - Preserves expected count before ranking

### 🧪 Test Documentation

#### 7. Regression Test Suite
**File:** `tests/test_dvd_sample_01_regression.py`  
**Purpose:** Automated validation of SPU extraction  
**Documentation:**
- Module docstring explaining test purpose
- `test_dvd_sample_01_button_extraction()` - Detailed docstring
  - Test steps outlined
  - Similarity threshold explained
  - Expected results documented
- `image_similarity()` - Algorithm documentation
- `compare_images()` - Function documentation

#### 8. Test Fixtures README
**File:** `tests/fixtures/DVD_Sample_01/README.md`  
**Purpose:** Document reference images and test data  
**Contents:**
- Reference image details (sizes, sources)
- Menu structure information
- Button rectangle specifications
- Extraction method documentation
- Test execution commands

### 🔧 Tools Documentation

#### 9. Debug Tool
**File:** `tools/debug_spu_packets.py`  
**Purpose:** Debug utility for SPU analysis  
**Documentation:**
- Module docstring
- Function comments
- Output format explanation
- Usage examples in SPU guide

### 📂 Documentation Index

#### 10. Documentation Directory README
**File:** `docs/README.md`  
**Purpose:** Navigation hub for all documentation  
**Contents:**
- Quick links to all documentation files
- Categorized by audience (developers, users, researchers)
- Documentation standards
- Contribution guidelines

## Documentation Coverage

### ✅ Algorithm Documentation
- [x] High-level overview (SPU Implementation Summary)
- [x] Detailed step-by-step walkthrough (Developer Guide)
- [x] Formal specification (PROJECT_SPEC.md)
- [x] Research rationale (Research Documentation)

### ✅ Code Documentation
- [x] Module docstrings (libdvdread_spu.py, menu_images.py)
- [x] Function docstrings (all public functions)
- [x] Inline comments (complex logic sections)
- [x] Type annotations (all functions)

### ✅ API Documentation
- [x] Function signatures
- [x] Parameter descriptions
- [x] Return value specifications
- [x] Usage examples
- [x] Error conditions

### ✅ Testing Documentation
- [x] Test purpose and methodology
- [x] Expected results
- [x] Test data documentation
- [x] Execution instructions

### ✅ User Documentation
- [x] Quick start guide
- [x] Troubleshooting guide
- [x] Performance characteristics
- [x] Reference images

## Quick Access by Role

### I'm a **Developer** adding features
1. Read `docs/SPU_BUTTON_EXTRACTION_GUIDE.md`
2. Review `src/dvdmenu_extract/util/libdvdread_spu.py`
3. Study `src/dvdmenu_extract/stages/menu_images.py`
4. Run `tests/test_dvd_sample_01_regression.py`

### I'm a **Researcher** analyzing the algorithm
1. Read `DVD_MENU_HIGHLIGHT_DETECTION_RESEARCH.md`
2. Review `SPU_EXTRACTION_IMPLEMENTATION.md`
3. Study algorithm in `docs/SPU_BUTTON_EXTRACTION_GUIDE.md`
4. Examine test results in `tests/test_dvd_sample_01_regression.py`

### I'm a **User** extracting buttons
1. Read `docs/SPU_BUTTON_EXTRACTION_GUIDE.md` Quick Start
2. Run pipeline: `uv run dvdmenu-extract <input> --out <output>`
3. If issues: Read Troubleshooting section

### I'm a **Maintainer** fixing bugs
1. Check `docs/SPU_BUTTON_EXTRACTION_GUIDE.md` Troubleshooting
2. Use `tools/debug_spu_packets.py` for diagnostics
3. Review inline comments in `menu_images.py`
4. Validate with `tests/test_dvd_sample_01_regression.py`

### I'm a **Project Manager** reviewing progress
1. Read `SPU_EXTRACTION_IMPLEMENTATION.md`
2. Review test results (100% similarity achieved)
3. Check `PROJECT_SPEC.md` for compliance

## Documentation Metrics

**Total Documentation:**
- **9** primary documentation files
- **1** code module with comprehensive docstrings
- **1** integration module with detailed comments
- **1** test suite with full documentation
- **1** debug tool

**Lines of Documentation:**
- Algorithm guides: ~500 lines
- Code docstrings: ~200 lines
- Inline comments: ~100 lines
- Test documentation: ~50 lines
- **Total: ~850 lines**

**Coverage:**
- Algorithm: ✅ 100% documented
- Public API: ✅ 100% documented
- Complex logic: ✅ 100% commented
- Tests: ✅ 100% documented

## Validation

**Documentation Quality Checks:**
- [x] All public functions have docstrings
- [x] All complex algorithms explained
- [x] Examples provided for key functions
- [x] Test cases fully documented
- [x] Cross-references between docs
- [x] Troubleshooting guide included
- [x] Performance metrics documented
- [x] Code and docs synchronized

**Test Coverage:**
- [x] Regression test passes (100% similarity)
- [x] Reference images stored
- [x] Test methodology documented
- [x] Expected results specified

## Maintenance

**When to Update:**
- Adding new features → Update relevant guides + code docs
- Fixing bugs → Update troubleshooting section
- Changing algorithm → Update all algorithm docs
- Adding tests → Update test documentation

**Documentation Review:**
- Check before each release
- Validate examples still work
- Update metrics and results
- Verify cross-references

## References

### Internal
- `README.md` - Project overview
- `CHANGELOG.md` - Version history (if exists)
- `CONTRIBUTING.md` - Contribution guidelines (if exists)

### External
- [FFmpeg dvdsubdec.c](https://ffmpeg.org/doxygen/trunk/dvdsubdec_8c_source.html)
- [Inside DVD-Video: Subpicture Streams](https://en.wikibooks.org/wiki/Inside_DVD-Video/Subpicture_Streams)
- [MPEG-2 Systems](https://www.iso.org/standard/22180.html)

---

**Status:** ✅ Complete and Validated  
**Last Review:** 2026-01-31  
**Next Review:** Upon next major feature addition  
**Maintainer:** DVD-Archaeology Project
