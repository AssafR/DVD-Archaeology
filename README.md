# 🎬 DVD Menu–Aware Episode Extractor

**Home-burned DVDs often hide multiple episodes inside a single VOB file, with the only real structure living in the DVD menu.**  
This project reconstructs that structure by parsing DVD navigation data, mapping menu buttons to their actual video segments, and OCR-reading menu text (English & Hebrew) to produce correctly split and human-named episode files.

Instead of guessing timestamps or relying on broken chapter metadata, this tool treats the DVD menu as the source of truth — the same way a real DVD player does.

**This is especially useful for personal archives, multilingual content, and discs where chapters exist only in the menu, not in the video stream.**

---

## Why this exists

Most DVD ripping tools flatten discs into one or two large video files, silently discarding the navigation logic that defines where episodes actually begin and end.  
For home-authored DVDs, VCDs, and SVCDs, this often means losing episode boundaries and titles entirely.

This project takes the opposite approach: **it reads the DVD the way a player does**, preserving the author’s intent and reconstructing episode structure instead of guessing it.

---

## How it works (high level)

1. **Parse DVD navigation data** to discover menu buttons, program chains (PGCs), and cell boundaries.  
2. **Map each menu button** to the exact video segment it activates.  
3. **Extract menu overlays** and OCR chapter titles in English and Hebrew.  
4. **Split the source video** into episode files named after their corresponding menu entries.  
5. *Optional:* normalize or lightly repair extracted streams before final segmentation.

The result is a deterministic, player-accurate reconstruction of episodes from discs that were never authored for modern media libraries.

---

## Non-goals (by default)

This project focuses on **structure recovery**, not media restoration. By default, it does **not** aim to:

- Perform heuristic or AI-based scene detection  
- Guess episode boundaries when navigation data is missing  
- Replace general-purpose ripping or transcoding tools  

Because the extraction pipeline relies on FFmpeg, **optional stream repair and normalization may be exposed as an opt-in step** for discs with minor corruption or timing issues.

The primary goal remains unchanged: **recovering episode structure from existing DVD navigation data**, not repairing broken media.

---

## Who this is for

- People archiving **home-burned DVDs** or old TV recordings  
- Multilingual collections (including **Hebrew RTL menus**)  
- Media librarians and digital preservation nerds  
- Anyone tired of files named `VTS_01_1_FINAL_FINAL.vob`

---

*FFmpeg may repair the video stream, but episode boundaries always come from the DVD menu — never from heuristics.*
