# Documentation

This directory contains detailed technical documentation for the DVD Menu-Aware Episode Extractor.

## Developer Guides

### [SPU Button Extraction Guide](SPU_BUTTON_EXTRACTION_GUIDE.md)
**Comprehensive guide to DVD button extraction using SPU overlays**

Topics covered:
- Quick start for users and developers
- Complete algorithm walkthrough
- API reference for all functions
- Testing and debugging procedures
- Troubleshooting common issues
- Performance characteristics

**Essential reading for anyone working with DVD menu button detection.**

## Project Documentation

### Root Directory Files

These files are located in the project root:

- **[PROJECT_SPEC.md](../PROJECT_SPEC.md)** - Complete project specification
  - Pipeline architecture
  - Stage-by-stage documentation
  - Format extensibility requirements
  - SPU extraction implementation details

- **[SPU_EXTRACTION_IMPLEMENTATION.md](../SPU_EXTRACTION_IMPLEMENTATION.md)** - Implementation summary
  - Problem solved and solution overview
  - Technical architecture
  - Test results and validation
  - Benefits and performance metrics

- **[DVD_MENU_HIGHLIGHT_DETECTION_RESEARCH.md](../DVD_MENU_HIGHLIGHT_DETECTION_RESEARCH.md)** - Research documentation
  - Problem statement and test case
  - Research findings
  - Detection approaches tested
  - Final solution and validation

## Code Documentation

### Heavily Documented Modules

- **`src/dvdmenu_extract/stages/menu_images.py`**
  - `_extract_spu_button_rects()` - Comprehensive docstring with algorithm details
  - `reassemble_spu_packets()` - Detailed packet reassembly documentation
  - Inline comments explaining each processing step

- **`src/dvdmenu_extract/util/libdvdread_spu.py`**
  - Module-level documentation with examples
  - Complete API reference
  - SPU packet format specifications
  - RLE encoding details

### Test Documentation

- **`tests/fixtures/DVD_Sample_01/README.md`** - Test fixtures documentation
  - Reference image information
  - Menu structure details
  - Test execution instructions

- **`tests/test_dvd_sample_01_regression.py`** - Regression test suite
  - Docstrings for each test function
  - Image comparison methodology
  - Expected results

## Quick Reference

### For New Developers

1. Start with [SPU Button Extraction Guide](SPU_BUTTON_EXTRACTION_GUIDE.md) (this guide)
2. Read [PROJECT_SPEC.md](../PROJECT_SPEC.md) Stage G for integration context
3. Review code in `src/dvdmenu_extract/stages/menu_images.py`
4. Run tests: `uv run pytest tests/test_dvd_sample_01_regression.py -v`

### For Users

1. Read the [README.md](../README.md) in the project root
2. Follow the quick start guide
3. Run the pipeline: `uv run dvdmenu-extract <input> --out <output> --use-real-ffmpeg`

### For Researchers

1. [DVD_MENU_HIGHLIGHT_DETECTION_RESEARCH.md](../DVD_MENU_HIGHLIGHT_DETECTION_RESEARCH.md) - Complete research process
2. [SPU_EXTRACTION_IMPLEMENTATION.md](../SPU_EXTRACTION_IMPLEMENTATION.md) - Implementation details
3. Test validation: `tests/test_dvd_sample_01_regression.py`

## Documentation Standards

All documentation in this project follows these standards:

- **Comprehensive:** Explains not just what, but why and how
- **Practical:** Includes working examples and code snippets
- **Discoverable:** Cross-referenced with related documentation
- **Maintainable:** Updated alongside code changes
- **Validated:** References actual test results and measurements

## Contributing

When adding new features:

1. Update relevant documentation files
2. Add docstrings to all public functions
3. Include inline comments for complex logic
4. Add examples to developer guides
5. Update this README if adding new docs

---

**Last Updated:** 2026-01-31  
**Maintainer:** DVD-Archaeology Project  
**Status:** ✅ Production Ready
