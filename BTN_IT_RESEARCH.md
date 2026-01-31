# BTN_IT Command Parser Research - DVD_Sample_01

**Date**: 2026-01-31  
**Goal**: Understand button navigation structure to enable multi-page menu detection

## Executive Summary

DVD_Sample_01 contains **TWO distinct button configurations** in its VIDEO_TS.VOB, confirming the 2-page menu structure:

- **NAV Pack #0**: Page 1 configuration (6 active buttons, indices 1-6)
- **NAV Pack #2**: Page 2 configuration (5 active buttons, indices 1-5)

### Key Discovery

❌ **No button rectangles defined in BTN_IT**  
✅ **Navigation links present** (up/down/left/right button indices)  
✅ **VM commands present** (2-byte DVD VM instructions for each direction)

This means:
- Button **positions** come from SPU stream (not BTN_IT)
- Button **navigation** is defined in BTN_IT
- Button **actions** (what happens on press) are in VM commands

## Detailed Analysis

### NAV Pack #0 - Page 1/2

```
HLI_SS: 0x0001 (highlight status)
BTN_MD: 0x1000 (button mode)
Active Buttons: 6 (indices 1-6)
Total Non-Empty Slots: 3 (only 3 have data)
```

**Button 1** (Track #1 thumbnail):
```
Rect: (none) - Position comes from SPU
Nav:  right->27
VM:   up=0x31EE, down=0x1D01, left=0xFF02, right=0x0401
```
- Pressing RIGHT navigates to button 27 (likely ">>" forward button)
- VM commands define what happens on each direction

**Button 2** (Track #2 thumbnail):
```
Rect: (none)
Nav:  left->6
VM:   down=0x0020, left=0x0205, right=0x0305
```
- Pressing LEFT navigates to button 6 (likely navigation button)

**Button 3** (appears in page 1 config but may not be visible):
```
Rect: (none)
Nav:  left->7, right->33
VM:   up=0x428C, down=0x1D01, left=0xFF02, right=0x0604
```
- Navigates to buttons 7 and 33

### NAV Pack #2 - Page 2/2

```
HLI_SS: 0x0001
BTN_MD: 0x1000
Active Buttons: 5 (indices 1-5)
Total Non-Empty Slots: 2
```

**Button 1**:
```
Rect: (none)
Nav:  left->12, right->14
VM:   up=0x111C, down=0x1D01, left=0xFF02, right=0x0402
```
- Different navigation structure than Page 1's Button 1

**Button 2**:
```
Rect: (none)
Nav:  left->13, right->33
VM:   up=0x428C, down=0x1D01, left=0xFF02, right=0x0501
```

## Button Index Mapping

### Observed Indices

**Active Content Buttons**:
- Indices 1-3 (Page 1): Track #1, Track #2, Track #3 (?)
- Indices 1-2 (Page 2): Different configuration

**Navigation Button References**:
- Button 6, 7 (referenced from Page 1)
- Button 12, 13, 14 (referenced from Page 2)
- Button 27, 33 (referenced from both pages)

**Hypothesis**:
- Buttons 1-3: Content buttons (our btn1, btn2, btn3)
- Buttons 4-6: Navigation buttons on Page 1 (>>, PLAY ALL, etc.)
- Buttons 12-14: Navigation buttons on Page 2 (<<, PLAY ALL, etc.)
- Button 27, 33: Special navigation (forward/back between pages?)

## VM Command Analysis

### Command Patterns Observed

**Right Navigation (Forward)**:
```
Button 1: right=0x0401
Button 2: right=0x0305
Button 3: right=0x0604
```

**Left Navigation (Back)**:
```
Button 1: left=0xFF02  (special: 0xFF prefix)
Button 2: left=0x0205
Button 3: left=0xFF02  (special: 0xFF prefix)
```

**Up Navigation**:
```
Button 1: up=0x31EE
Button 3: up=0x428C
Button 1 (Page 2): up=0x111C
```

**Down Navigation**:
```
Button 1: down=0x1D01  (common pattern!)
Button 2: down=0x0020
Button 3: down=0x1D01  (common pattern!)
```

### Common Command: 0x1D01

Appears in **down** direction for buttons 1 and 3. Likely a standard "navigate down" command.

### Special Command: 0xFF02

Appears in **left** direction for buttons 1 and 3. The 0xFF prefix might indicate:
- Invalid/disabled navigation
- Special system command
- Return to menu root

## DVD VM Command Structure

DVD VM commands are **2 bytes** (16 bits):

```
High Byte (8 bits): Opcode
Low Byte (8 bits): Operand/Parameters
```

Common VM Opcodes (from DVD spec):
```
0x00: NOP (no operation)
0x01-0x06: Link commands (Jump to cell, PGC, etc.)
0x1D: Link to menu (LinkPGCN)
0x31: Set system parameter
0x42: Set general parameter
0xFF: Special/reserved
```

### Interpreting DVD_Sample_01 Commands

**0x1D01**: `Link PGCN 01`
- Jump to Program Chain 1
- Common menu navigation command

**0x0401**: `Link Cell 01` (?)
- Might jump to a specific cell/chapter

**0xFF02**: `Special command 02`
- Likely "return to root menu" or "disabled"

**0x428C**: `SetGPRM(12)` (?)
- Set General Parameter Register 12
- Might toggle menu state

## Limitations for Multi-Page Detection

### Problem: Buttons Have No Rectangles

The BTN_IT table **does not contain button rectangles** for DVD_Sample_01. This means:

❌ **Cannot detect button positions** from BTN_IT alone  
❌ **Cannot map visual thumbnails** to button indices directly  
✅ **CAN identify different page configurations** (different active button counts/links)  
✅ **CAN trace navigation graph** (which buttons lead where)

### What We CAN Do

1. **Detect menu state transitions** by comparing BTN_IT configurations
2. **Build navigation graph** showing button->button relationships
3. **Identify potential pages** by clustering configurations
4. **Simulate button presses** to enumerate reachable states

### What We CANNOT Do

1. **Extract button rectangles** - must come from SPU stream
2. **Map btn1/btn2/btn3 to BTN_IT indices** - no visual correlation without SPU
3. **Determine button visibility** - NAV pack doesn't say which buttons are visible

## Next Steps for Implementation

### Approach 1: Navigation Graph Analysis (Feasible)

**Goal**: Build a state machine of menu pages from BTN_IT data

**Steps**:
1. Parse all NAV packs in menu VOB
2. Extract unique button configurations (active indices, nav links)
3. Build directed graph: `button_idx -> {up: X, down: Y, left: Z, right: W}`
4. Identify "pages" as clusters of buttons with similar navigation patterns
5. Map our detected visual buttons (btn1, btn2, btn3) to pages based on:
   - Order (btn1 likely = button index 1)
   - Count (3 buttons total matches 3 content buttons in BTN_IT)

**Challenges**:
- No guarantee btn1 = button 1 (could be button 2 or 3)
- No way to know which buttons are visible without SPU

### Approach 2: VM Command Interpreter (Complex)

**Goal**: Execute DVD VM commands to simulate menu state

**Steps**:
1. Implement DVD VM instruction parser
2. Track system registers (SPRM) and general registers (GPRM)
3. Simulate button press sequences
4. Track menu state changes (PGC transitions)
5. Capture SPU overlay states at each menu state

**Challenges**:
- Full DVD VM has ~60 opcodes
- Requires implementing DVD player logic
- Need to decode SPU stream at each state
- Very complex implementation (~1000+ lines of code)

### Approach 3: Hybrid Heuristic (Practical)

**Goal**: Use BTN_IT data + visual detection + heuristics

**Steps**:
1. Parse BTN_IT to count pages (2 configs = 2 pages confirmed)
2. Visual detection finds buttons on page 1 (btn1, btn2)
3. **Assume** button 3 is on page 2 (btn_ns decreases from 6→5)
4. Use BTN_IT navigation links to understand relationships
5. Extract page-specific frames if possible (not applicable to DVD_Sample_01)

**For DVD_Sample_01 specifically**:
- Page 1: 6 active buttons (indices 1-6)
  - Buttons 1, 2, 3 = content (our btn1, btn2, btn3?)
  - Buttons 4, 5, 6 = navigation (>>, PLAY ALL)
- Page 2: 5 active buttons (indices 1-5)
  - Buttons 1, 2 = content (actually btn3?)
  - Buttons 3, 4, 5 = navigation (<<, PLAY ALL)

**Limitation**: This is speculation without SPU data to confirm visibility.

## Recommendation

**Implement Approach 3 (Hybrid Heuristic)** with these steps:

1. ✅ **Parse BTN_IT for all NAV packs** (done - see `analyze_btn_it_full.py`)
2. **Count unique configurations** to determine # of pages
3. **Visual detection** to find buttons on primary frame
4. **Heuristic mapping**:
   - If BTN_IT shows N pages and we detect M buttons:
     - Distribute buttons across pages (M/N per page)
     - Mark undetected buttons as "page X" based on BTN_IT
5. **Document limitations** clearly

This provides:
- ✅ Better than current fallback (knows which page button is on)
- ✅ Works for discs with temporal pages AND state-based pages
- ✅ Reasonable implementation complexity
- ⚠️ Still imperfect for DVD_Sample_01 (no SPU extraction)

## Code Location

**Analysis Scripts**:
- `scripts/analyze_btn_it.py` - Basic BTN_IT parsing
- `scripts/analyze_btn_it_full.py` - Comprehensive 36-slot analysis

**Existing Parsers**:
- `src/dvdmenu_extract/util/libdvdread_compat.py` - BTN_IT parsing
  - `parse_nav_pack_buttons()` - Extracts buttons from NAV pack
  - `decode_btn_it_rect()` - Decodes button rectangles (unused here)

**Integration Point**:
- `src/dvdmenu_extract/stages/menu_images.py`
  - Currently: Multi-page temporal detection
  - TODO: Add BTN_IT-based page detection

## References

- libdvdread BTN_IT structure: https://github.com/mirror/libdvdread/blob/master/src/dvdread/ifo_types.h
- DVD VM specification: DVD-Video spec Part 3, Chapter 4
- NAV pack structure: DVD-Video spec Part 3, Annex D
