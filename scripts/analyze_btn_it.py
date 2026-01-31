#!/usr/bin/env python3
"""Analyze BTN_IT (button information table) data from DVD NAV packs.

This script scans VOB files for NAV packs and extracts complete button
information including navigation links and VM commands.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dvdmenu_extract.util.libdvdread_compat import read_u16


def find_nav_packs(vob_path: Path) -> list[bytes]:
    """Find all NAV packs in a VOB file."""
    nav_packs = []
    with open(vob_path, "rb") as f:
        data = f.read()
    
    # Search for NAV pack marker (0x000001bf)
    offset = 0
    while True:
        marker = data.find(b"\x00\x00\x01\xbf", offset)
        if marker < 0:
            break
        
        # NAV packs are 2048 bytes
        if marker + 2048 <= len(data):
            nav_packs.append(data[marker:marker + 2048])
        offset = marker + 1
    
    return nav_packs


def parse_btn_it_entry(entry: bytes) -> dict:
    """Parse a single BTN_IT entry (18 bytes)."""
    if len(entry) < 18:
        return {}
    
    # Bytes 0-5: Button rectangle
    b0, b1, b2, b3, b4, b5 = entry[0:6]
    x1 = ((b0 & 0x3F) << 4) | (b1 >> 4)
    x2 = ((b1 & 0x03) << 8) | b2
    y1 = ((b3 & 0x3F) << 4) | (b4 >> 4)
    y2 = ((b4 & 0x03) << 8) | b5
    
    # Bytes 6-9: Navigation links (button indices 1-36)
    up = entry[6] & 0x3F
    down = entry[7] & 0x3F
    left = entry[8] & 0x3F
    right = entry[9] & 0x3F
    
    # Bytes 10-17: VM commands for each navigation direction
    # Each command is 2 bytes (8 bytes total for up/down/left/right)
    cmd_up = (entry[10] << 8) | entry[11]
    cmd_down = (entry[12] << 8) | entry[13]
    cmd_left = (entry[14] << 8) | entry[15]
    cmd_right = (entry[16] << 8) | entry[17]
    
    return {
        "rect": (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None,
        "nav_links": {
            "up": up if up > 0 else None,
            "down": down if down > 0 else None,
            "left": left if left > 0 else None,
            "right": right if right > 0 else None,
        },
        "vm_commands": {
            "up": f"0x{cmd_up:04X}" if cmd_up != 0 else None,
            "down": f"0x{cmd_down:04X}" if cmd_down != 0 else None,
            "left": f"0x{cmd_left:04X}" if cmd_left != 0 else None,
            "right": f"0x{cmd_right:04X}" if cmd_right != 0 else None,
        },
    }


def analyze_nav_pack(nav_pack: bytes) -> dict | None:
    """Analyze BTN_IT table in a NAV pack."""
    # Find PCI packet within NAV pack
    marker = nav_pack.find(b"\x00\x00\x01\xbf")
    if marker < 0:
        return None
    
    pci_start = marker + 4 + 2 + 1
    if pci_start + 0x0bb + (36 * 18) > len(nav_pack):
        return None
    
    # Parse button metadata
    hli_ss = read_u16(nav_pack, pci_start + 0x60)  # Highlight status
    btn_md = read_u16(nav_pack, pci_start + 0x6E)  # Button mode
    btn_sn = nav_pack[pci_start + 0x70]  # Start button number
    btn_ns = nav_pack[pci_start + 0x71]  # Number of buttons
    
    if btn_ns == 0:
        return None
    
    # Parse BTN_IT table (36 entries × 18 bytes each)
    btn_it_start = pci_start + 0x0bb
    buttons = []
    
    for i in range(36):
        entry = nav_pack[btn_it_start + (i * 18) : btn_it_start + ((i + 1) * 18)]
        btn_data = parse_btn_it_entry(entry)
        # Include button if it has rect, nav links, OR VM commands
        has_data = (
            btn_data.get("rect") or 
            any(btn_data.get("nav_links", {}).values()) or
            any(btn_data.get("vm_commands", {}).values())
        )
        if has_data:
            btn_data["index"] = i + 1
            buttons.append(btn_data)
    
    return {
        "hli_ss": f"0x{hli_ss:04X}",
        "btn_md": f"0x{btn_md:04X}",
        "btn_sn": btn_sn,
        "btn_ns": btn_ns,
        "buttons": buttons,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: analyze_btn_it.py <VIDEO_TS_DIR>")
        sys.exit(1)
    
    video_ts = Path(sys.argv[1])
    if not video_ts.is_dir():
        print(f"Error: {video_ts} is not a directory")
        sys.exit(1)
    
    # Check all VOB files
    vob_files = sorted(video_ts.glob("*.VOB"))
    
    for vob_path in vob_files:
        print(f"\n{'='*70}")
        print(f"Analyzing: {vob_path.name}")
        print(f"{'='*70}\n")
        
        nav_packs = find_nav_packs(vob_path)
        print(f"Found {len(nav_packs)} NAV packs")
        
        button_tables = []
        for i, nav_pack in enumerate(nav_packs):
            result = analyze_nav_pack(nav_pack)
            if result and result["buttons"]:
                button_tables.append((i, result))
        
        if not button_tables:
            print("No button tables found in this VOB\n")
            continue
        
        print(f"Found {len(button_tables)} NAV packs with button data\n")
        
        # Show details of all unique button configurations
        seen_configs = set()
        for nav_idx, data in button_tables:  # Show all
            config_key = (data["btn_ns"], tuple(
                (b["index"], b["rect"], tuple(b["nav_links"].items()))
                for b in data["buttons"]
            ))
            if config_key in seen_configs:
                continue
            seen_configs.add(config_key)
            
            print(f"NAV Pack #{nav_idx}:")
            print(f"  HLI_SS: {data['hli_ss']} (highlight status)")
            print(f"  BTN_MD: {data['btn_md']} (button mode)")
            print(f"  Start Button: {data['btn_sn']}, Count: {data['btn_ns']}")
            print(f"  Total Button Entries: {len(data['buttons'])}\n")
            
            # Group buttons by whether they have rects
            with_rects = [b for b in data["buttons"] if b["rect"]]
            without_rects = [b for b in data["buttons"] if not b["rect"]]
            
            if with_rects:
                print(f"  Buttons with Rectangles ({len(with_rects)}):")
                for btn in with_rects:
                    x1, y1, x2, y2 = btn["rect"]
                    print(f"    Button {btn['index']}: ({x1}, {y1}, {x2}, {y2}) [{x2-x1}x{y2-y1}]")
                    print(f"      Nav: {btn['nav_links']}")
                    vm_cmds = {k: v for k, v in btn["vm_commands"].items() if v}
                    if vm_cmds:
                        print(f"      VM: {vm_cmds}")
                print()
            
            if without_rects:
                print(f"  Buttons without Rectangles ({len(without_rects)}):")
                for btn in without_rects:
                    print(f"    Button {btn['index']}:")
                    print(f"      Nav: {btn['nav_links']}")
                    vm_cmds = {k: v for k, v in btn["vm_commands"].items() if v}
                    if vm_cmds:
                        print(f"      VM: {vm_cmds}")
                print()


if __name__ == "__main__":
    main()
