#!/usr/bin/env python3
"""Comprehensive BTN_IT analysis showing all 36 button slots."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dvdmenu_extract.util.libdvdread_compat import read_u16


def find_nav_packs(vob_path: Path) -> list[bytes]:
    """Find all NAV packs in a VOB file."""
    nav_packs = []
    with open(vob_path, "rb") as f:
        data = f.read()
    
    offset = 0
    while True:
        marker = data.find(b"\x00\x00\x01\xbf", offset)
        if marker < 0:
            break
        if marker + 2048 <= len(data):
            nav_packs.append(data[marker:marker + 2048])
        offset = marker + 1
    
    return nav_packs


def analyze_full_btn_it(nav_pack: bytes) -> dict | None:
    """Analyze complete BTN_IT table showing all 36 slots."""
    marker = nav_pack.find(b"\x00\x00\x01\xbf")
    if marker < 0:
        return None
    
    pci_start = marker + 4 + 2 + 1
    if pci_start + 0x0bb + (36 * 18) > len(nav_pack):
        return None
    
    # Parse button metadata
    hli_ss = read_u16(nav_pack, pci_start + 0x60)
    btn_md = read_u16(nav_pack, pci_start + 0x6E)
    btn_sn = nav_pack[pci_start + 0x70]  # Start button number (1-based)
    btn_ns = nav_pack[pci_start + 0x71]  # Number of buttons
    
    if btn_ns == 0:
        return None
    
    # Active button indices
    start_idx = btn_sn if btn_sn > 0 else 1
    active_indices = set(range(start_idx, min(start_idx + btn_ns, 37)))
    
    # Parse all 36 BTN_IT entries
    btn_it_start = pci_start + 0x0bb
    all_buttons = []
    
    for i in range(36):
        entry_start = btn_it_start + (i * 18)
        entry = nav_pack[entry_start : entry_start + 18]
        
        if len(entry) < 18:
            continue
        
        # Parse rectangle
        b0, b1, b2, b3, b4, b5 = entry[0:6]
        x1 = ((b0 & 0x3F) << 4) | (b1 >> 4)
        x2 = ((b1 & 0x03) << 8) | b2
        y1 = ((b3 & 0x3F) << 4) | (b4 >> 4)
        y2 = ((b4 & 0x03) << 8) | b5
        rect = (x1, y1, x2, y2) if (x2 > x1 and y2 > y1) else None
        
        # Parse navigation links
        up = entry[6] & 0x3F
        down = entry[7] & 0x3F
        left = entry[8] & 0x3F
        right = entry[9] & 0x3F
        
        # Parse VM commands
        cmd_up = (entry[10] << 8) | entry[11]
        cmd_down = (entry[12] << 8) | entry[13]
        cmd_left = (entry[14] << 8) | entry[15]
        cmd_right = (entry[16] << 8) | entry[17]
        
        # Determine if this slot has any data
        has_data = (
            rect or
            up > 0 or down > 0 or left > 0 or right > 0 or
            cmd_up > 0 or cmd_down > 0 or cmd_left > 0 or cmd_right > 0
        )
        
        if has_data:
            btn_idx = i + 1
            all_buttons.append({
                "index": btn_idx,
                "active": btn_idx in active_indices,
                "rect": rect,
                "nav": {"up": up or None, "down": down or None, "left": left or None, "right": right or None},
                "vm": {
                    "up": f"0x{cmd_up:04X}" if cmd_up else None,
                    "down": f"0x{cmd_down:04X}" if cmd_down else None,
                    "left": f"0x{cmd_left:04X}" if cmd_left else None,
                    "right": f"0x{cmd_right:04X}" if cmd_right else None,
                },
            })
    
    return {
        "hli_ss": f"0x{hli_ss:04X}",
        "btn_md": f"0x{btn_md:04X}",
        "btn_sn": btn_sn,
        "btn_ns": btn_ns,
        "active_range": f"{start_idx}-{start_idx + btn_ns - 1}" if btn_ns > 0 else "none",
        "buttons": all_buttons,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: analyze_btn_it_full.py <VOB_FILE>")
        sys.exit(1)
    
    vob_path = Path(sys.argv[1])
    if not vob_path.is_file():
        print(f"Error: {vob_path} not found")
        sys.exit(1)
    
    print(f"Analyzing: {vob_path.name}\n")
    
    nav_packs = find_nav_packs(vob_path)
    print(f"Found {len(nav_packs)} NAV packs\n")
    
    # Analyze unique button configurations
    seen_configs = set()
    for nav_idx, nav_pack in enumerate(nav_packs):
        result = analyze_full_btn_it(nav_pack)
        if not result or not result["buttons"]:
            continue
        
        # Create config signature
        config_sig = (
            result["btn_ns"],
            result["active_range"],
            tuple((b["index"], b["active"], b["rect"] is not None) for b in result["buttons"])
        )
        
        if config_sig in seen_configs:
            continue
        seen_configs.add(config_sig)
        
        print(f"{'='*70}")
        print(f"NAV Pack #{nav_idx} - Button Configuration")
        print(f"{'='*70}")
        print(f"HLI_SS: {result['hli_ss']}, BTN_MD: {result['btn_md']}")
        print(f"Active Buttons: {result['btn_ns']} (indices {result['active_range']})")
        print(f"Total Non-Empty Slots: {len(result['buttons'])}\n")
        
        # Group by active status
        active_btns = [b for b in result["buttons"] if b["active"]]
        inactive_btns = [b for b in result["buttons"] if not b["active"]]
        
        if active_btns:
            print(f"ACTIVE BUTTONS ({len(active_btns)}):")
            print("-" * 70)
            for btn in active_btns:
                print(f"  Button {btn['index']}:")
                if btn["rect"]:
                    x1, y1, x2, y2 = btn["rect"]
                    print(f"    Rect: ({x1:3d}, {y1:3d}, {x2:3d}, {y2:3d}) size: {x2-x1}x{y2-y1}")
                else:
                    print(f"    Rect: (none)")
                nav_str = ", ".join(f"{k}->{v}" for k, v in btn["nav"].items() if v)
                print(f"    Nav:  {nav_str or '(none)'}")
                vm_str = ", ".join(f"{k}={v}" for k, v in btn["vm"].items() if v)
                if vm_str:
                    print(f"    VM:   {vm_str}")
                print()
        
        if inactive_btns:
            print(f"INACTIVE/NAVIGATION BUTTONS ({len(inactive_btns)}):")
            print("-" * 70)
            for btn in inactive_btns:
                print(f"  Button {btn['index']}: ", end="")
                if btn["rect"]:
                    x1, y1, x2, y2 = btn["rect"]
                    print(f"rect=({x1},{y1},{x2},{y2})", end=" ")
                nav_str = ", ".join(f"{k}->{v}" for k, v in btn["nav"].items() if v)
                if nav_str:
                    print(f"nav={nav_str}", end=" ")
                vm_str = ", ".join(f"{k}={v}" for k, v in btn["vm"].items() if v)
                if vm_str:
                    print(f"vm={vm_str}", end=" ")
                print()
            print()


if __name__ == "__main__":
    main()
