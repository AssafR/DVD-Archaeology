# FFmpeg VOB Extraction and Repair Parameters

## Summary of Changes

The DVD extraction pipeline has been enhanced with improved error resilience and complete stream preservation for damaged or problematic DVD files.

✅ **Successfully tested** on Ugly Betty Season 1B DVD (7 episodes, ~3.5 GB total extracted)

## Key Improvements

### 1. Complete Stream Preservation

**Before:**
```
-map 0:v:0    # First video stream only
-map 0:a?     # All audio streams (optional)
```

**After:**
```
-map 0:v      # All video streams
-map 0:a      # All audio streams
-map 0:s?     # All subtitle streams (optional)
```

**Benefit:** Preserves all DVD content including multiple audio tracks and subtitle streams. 

**Note:** We specifically map video/audio/subtitles rather than `-map 0` because DVDs contain dvd_nav_packet data streams that are not supported by Matroska format. This selective mapping ensures compatibility while preserving all playable content.

---

## 2. Repair Modes

The `--repair` parameter now supports three modes:

### `--repair off` (Default)
Basic extraction with minimal error handling. Use for clean, undamaged discs.

**Parameters:**
- `-fflags +genpts` - Generate presentation timestamps
- `-err_detect ignore_err` - Ignore detection errors
- `-probesize 100M` - Analyze more data for format detection
- `-analyzeduration 100M` - Spend more time analyzing input
- `-ignore_unknown` / `-copy_unknown` - Handle unknown streams
- `-avoid_negative_ts make_zero` - Fix timestamp issues
- `-start_at_zero` - Normalize timestamps
- `-max_interleave_delta 0` - Tight stream synchronization

### `--repair safe` (Recommended for Damaged Discs)
Moderate error resilience without performance impact. **Recommended for most damaged DVDs.**

**Additional parameters:**
- `-max_muxing_queue_size 9999` - Increased buffer for out-of-sync streams
- `-max_error_rate 1.0` - Allow processing to continue despite errors (up to 100% error rate)

**Use when:**
- DVD has scratches or minor physical damage
- Playback skips or stutters
- Some sectors are unreadable
- FFmpeg reports AC texture errors, MV errors, or similar issues

### `--repair aggressive` (For Severely Damaged Discs)
Maximum error resilience with potential performance impact. Use as a last resort.

**Additional parameters:**
- `-fflags +genpts+discardcorrupt` - Also discard corrupted packets
- `-max_muxing_queue_size 9999`
- `-max_error_rate 1.0`

**Warning:** The `+discardcorrupt` flag can cause FFmpeg to hang or run very slowly on some inputs. Use only when `--repair safe` fails.

**Use when:**
- Disc is severely scratched or damaged
- `--repair safe` produces unwatchable output
- Willing to accept potential slowness or hangs

---

## 3. Error Handling Details

### `-err_detect ignore_err`
Tells FFmpeg to continue processing even when it encounters errors in the input stream. Without this, FFmpeg would stop at the first error.

### `-max_error_rate 1.0`
Sets the threshold for acceptable errors. Default is ~0.667 (66.7%). Setting to 1.0 means FFmpeg will continue even if 100% of frames have errors, allowing maximum data recovery.

### `-max_muxing_queue_size 9999`
Increases the internal buffer size for stream multiplexing. DVD files often have streams that become temporarily out of sync (especially when damaged). A larger buffer prevents FFmpeg from failing when streams drift.

### `-fflags +discardcorrupt`
Actively discards packets that are detected as corrupted rather than trying to process them. This can:
- **Pro:** Produce cleaner output by removing garbage data
- **Con:** Can cause FFmpeg to hang or run slowly while scanning for corruption
- **Con:** May discard more data than necessary

---

## 4. Implementation Details

### Helper Functions

Two new helper functions centralize parameter management:

```python
_build_ffmpeg_input_flags(repair: str) -> list[str]
```
Builds input-related flags based on repair mode.

```python
_build_ffmpeg_output_flags() -> list[str]
```
Builds output-related flags (stream mapping, codec, timing).

### Applied To All Extraction Methods

The improved parameters are applied to all four extraction paths:
1. **Sector-based extraction** - Direct sector range extraction from VOB files
2. **Single-slice extraction** - Extract one segment from a single source file
3. **Multi-slice extraction** - Extract multiple segments and join them
4. **Concat extraction** - Concatenate multiple pre-extracted slices

---

## Usage Examples

### Clean Disc (No Repair Needed)
```bash
python main.py /path/to/VIDEO_TS --out ./output --use-real-ffmpeg
```

### Damaged Disc (Moderate Damage)
```bash
python main.py /path/to/VIDEO_TS --out ./output --use-real-ffmpeg --repair safe
```

### Severely Damaged Disc (Last Resort)
```bash
python main.py /path/to/VIDEO_TS --out ./output --use-real-ffmpeg --repair aggressive
```

---

## Expected Output Quality

### With `--repair off`
- Clean discs: Perfect extraction
- Damaged discs: May fail with errors

### With `--repair safe`
- Clean discs: Perfect extraction (no negative impact)
- Moderately damaged discs: Usually successful, may have minor glitches
- Severely damaged discs: May still fail

### With `--repair aggressive`
- Any disc: Maximum recovery attempt
- Trade-off: Slower processing, possible hangs
- Output may have visible artifacts or dropouts in damaged areas

---

## Technical References

### FFmpeg Documentation
- [FFmpeg Error Resilience](https://ffmpeg.org/doxygen/trunk/error__resilience_8c.html)
- [max_error_rate parameter](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2013-October/069544.html)

### DVD-Specific Considerations
- VOB files are MPEG-2 Program Streams
- Can contain multiple video angles, audio tracks (AC3, DTS, PCM), and subtitle streams (VobSub)
- DVD navigation data (PCI/DSI packets) is preserved with `-copy_unknown`
- Sector-based extraction bypasses corrupted filesystem metadata

---

## Troubleshooting

### FFmpeg hangs with `--repair aggressive`
**Solution:** Use `--repair safe` instead. The `+discardcorrupt` flag is scanning every packet.

### Output has audio/video desync
**Solution:** The disc damage may be too severe. Try:
1. Use `--repair aggressive` if not already
2. Check the disc for physical damage
3. Use `ddrescue` or `dvdbackup` to create a disc image first

### Extraction fails even with `--repair aggressive`
**Solution:** The disc may be too damaged for FFmpeg. Try:
1. Create a disc image with `ddrescue` (attempts multiple reads)
2. Use commercial DVD recovery software
3. Clean the disc and retry

### Missing subtitles in output
**Solution:** This should now be fixed with `-map 0`. If subtitles are still missing:
- Verify the DVD actually contains subtitle streams
- Check FFmpeg output logs for subtitle stream detection
- Some DVDs have menu-based subtitles only (not in video streams)

---

## Performance Impact

| Mode | Speed | Quality | Reliability |
|------|-------|---------|-------------|
| `off` | ⚡⚡⚡ Fastest | ⭐⭐⭐ Best | ❌ Fails on damage |
| `safe` | ⚡⚡ Fast | ⭐⭐ Good | ✅ Handles most damage |
| `aggressive` | ⚡ Slow | ⭐ Acceptable | ✅✅ Maximum recovery |

**Recommendation:** Start with `--repair safe` for any disc that's not pristine. Only use `aggressive` if `safe` fails.
