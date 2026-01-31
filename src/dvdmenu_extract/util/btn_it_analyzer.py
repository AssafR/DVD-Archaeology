"""BTN_IT (Button Information Table) analyzer for multi-page menu detection.

Parses NAV pack BTN_IT data to understand menu structure, navigation graph,
and page configurations. Enables intelligent button-to-page assignment for
state-based multi-page menus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dvdmenu_extract.util.libdvdread_compat import parse_nav_pack_buttons


@dataclass
class ButtonInfo:
    """Single button information from BTN_IT."""
    index: int  # 1-based button index (1-36)
    active: bool  # Whether this button is in the active range
    rect: tuple[int, int, int, int] | None  # (x1, y1, x2, y2) if present
    nav_up: int | None  # Button index to navigate to on UP
    nav_down: int | None  # Button index to navigate to on DOWN
    nav_left: int | None  # Button index to navigate to on LEFT
    nav_right: int | None  # Button index to navigate to on RIGHT
    vm_cmd_up: int  # VM command for UP (2-byte value)
    vm_cmd_down: int  # VM command for DOWN
    vm_cmd_left: int  # VM command for LEFT
    vm_cmd_right: int  # VM command for RIGHT


@dataclass
class ButtonConfiguration:
    """A unique button configuration representing a menu page."""
    config_id: int  # Unique ID for this configuration
    nav_pack_indices: list[int]  # NAV pack indices with this config
    active_button_range: tuple[int, int]  # (start, end) 1-based inclusive
    active_button_count: int
    buttons: dict[int, ButtonInfo]  # button_index -> ButtonInfo
    
    def signature(self) -> tuple:
        """Create a signature for comparing configurations."""
        # Use button count, active range, and navigation links as signature
        nav_sig = tuple(
            (idx, btn.nav_up, btn.nav_down, btn.nav_left, btn.nav_right)
            for idx, btn in sorted(self.buttons.items())
        )
        return (self.active_button_count, self.active_button_range, nav_sig)


@dataclass
class MenuPageAnalysis:
    """Complete analysis of menu page structure from BTN_IT data."""
    vob_path: Path
    total_nav_packs: int
    nav_packs_with_buttons: int
    configurations: list[ButtonConfiguration]
    page_count: int  # Number of unique configurations (pages)
    navigation_graph: dict[int, dict[str, int]]  # button_idx -> {direction: target_idx}
    
    def get_config_for_button(self, button_index: int) -> ButtonConfiguration | None:
        """Find which configuration contains a given button index."""
        for config in self.configurations:
            if button_index in config.buttons and config.buttons[button_index].active:
                return config
        return None
    
    def get_page_for_button(self, button_index: int) -> int | None:
        """Get page number (0-based) for a given button index."""
        config = self.get_config_for_button(button_index)
        if config is None:
            return None
        try:
            return self.configurations.index(config)
        except ValueError:
            return None
    
    def get_buttons_on_page(self, page_num: int) -> list[int]:
        """Get list of active button indices on a given page (0-based)."""
        if page_num < 0 or page_num >= len(self.configurations):
            return []
        config = self.configurations[page_num]
        return sorted([idx for idx, btn in config.buttons.items() if btn.active])


def find_nav_packs(vob_path: Path) -> list[tuple[int, bytes]]:
    """
    Find all NAV packs in a VOB file.
    
    Returns:
        List of (offset, nav_pack_data) tuples
    """
    nav_packs = []
    
    with open(vob_path, "rb") as f:
        data = f.read()
    
    offset = 0
    pack_idx = 0
    while True:
        # NAV packs start with packet marker 0x000001bf
        marker = data.find(b"\x00\x00\x01\xbf", offset)
        if marker < 0:
            break
        
        # NAV packs are typically 2048 bytes, but we only need first ~1024 for PCI
        if marker + 1024 <= len(data):
            nav_pack = data[marker : marker + 1024]
            nav_packs.append((pack_idx, nav_pack))
            pack_idx += 1
        
        offset = marker + 1
    
    return nav_packs


def parse_button_info_from_nav_pack(nav_pack: bytes, nav_pack_idx: int) -> ButtonConfiguration | None:
    """
    Parse complete button information from a single NAV pack.
    
    Args:
        nav_pack: NAV pack data (at least 1024 bytes)
        nav_pack_idx: Index of this NAV pack in the VOB
    
    Returns:
        ButtonConfiguration if buttons found, None otherwise
    """
    logger = logging.getLogger(__name__)
    
    nav_buttons = parse_nav_pack_buttons(nav_pack)
    if nav_buttons is None or nav_buttons.btn_ns == 0:
        return None
    
    # Determine active button range
    start_idx = nav_buttons.btn_sn if nav_buttons.btn_sn > 0 else 1
    end_idx = min(start_idx + nav_buttons.btn_ns - 1, 36)
    active_indices = set(range(start_idx, end_idx + 1))
    
    # Parse all button slots (we parse all 36 to get navigation targets)
    buttons: dict[int, ButtonInfo] = {}
    
    for i, (rect, links) in enumerate(zip(nav_buttons.rects, nav_buttons.links)):
        btn_idx = i + 1
        
        # Parse navigation links
        nav_up = links.get("up")
        nav_down = links.get("down")
        nav_left = links.get("left")
        nav_right = links.get("right")
        
        # Check if this button has any data (rect, links, or is active)
        has_data = (
            rect is not None or
            nav_up or nav_down or nav_left or nav_right or
            btn_idx in active_indices
        )
        
        if not has_data:
            continue
        
        # Get VM commands from raw entry
        # We need to re-parse the entry to get VM commands
        marker = nav_pack.find(b"\x00\x00\x01\xbf")
        if marker >= 0:
            pci_start = marker + 4 + 2 + 1
            btn_it_start = pci_start + 0x0bb
            entry_start = btn_it_start + (i * 18)
            
            if entry_start + 18 <= len(nav_pack):
                entry = nav_pack[entry_start : entry_start + 18]
                vm_cmd_up = (entry[10] << 8) | entry[11]
                vm_cmd_down = (entry[12] << 8) | entry[13]
                vm_cmd_left = (entry[14] << 8) | entry[15]
                vm_cmd_right = (entry[16] << 8) | entry[17]
            else:
                vm_cmd_up = vm_cmd_down = vm_cmd_left = vm_cmd_right = 0
        else:
            vm_cmd_up = vm_cmd_down = vm_cmd_left = vm_cmd_right = 0
        
        # Log ALL active buttons (with or without rectangles) for debugging
        if btn_idx in active_indices:
            if rect is not None:
                logger.info(f"    BTN_IT Button {btn_idx}: rect={rect}")
            else:
                logger.info(f"    BTN_IT Button {btn_idx}: NO RECTANGLE (rect=None)")
        
        buttons[btn_idx] = ButtonInfo(
            index=btn_idx,
            active=btn_idx in active_indices,
            rect=rect,
            nav_up=nav_up if nav_up and nav_up > 0 else None,
            nav_down=nav_down if nav_down and nav_down > 0 else None,
            nav_left=nav_left if nav_left and nav_left > 0 else None,
            nav_right=nav_right if nav_right and nav_right > 0 else None,
            vm_cmd_up=vm_cmd_up,
            vm_cmd_down=vm_cmd_down,
            vm_cmd_left=vm_cmd_left,
            vm_cmd_right=vm_cmd_right,
        )
    
    if not buttons:
        return None
    
    config = ButtonConfiguration(
        config_id=0,  # Will be assigned later
        nav_pack_indices=[nav_pack_idx],
        active_button_range=(start_idx, end_idx),
        active_button_count=nav_buttons.btn_ns,
        buttons=buttons,
    )
    
    return config


def analyze_btn_it_structure(vob_path: Path) -> MenuPageAnalysis | None:
    """
    Analyze BTN_IT data from all NAV packs to understand menu structure.
    
    This function:
    1. Finds all NAV packs in the menu VOB
    2. Parses button configurations from each NAV pack
    3. Identifies unique configurations (menu pages)
    4. Builds a complete navigation graph
    
    Args:
        vob_path: Path to menu VOB file (VIDEO_TS.VOB, VTS_XX_0.VOB, etc.)
    
    Returns:
        MenuPageAnalysis with page structure and navigation graph,
        or None if no button data found
    """
    logger = logging.getLogger(__name__)
    
    if not vob_path.is_file():
        logger.warning(f"BTN_IT analysis: VOB not found: {vob_path}")
        return None
    
    # Find all NAV packs
    nav_packs = find_nav_packs(vob_path)
    logger.info(f"BTN_IT analysis: found {len(nav_packs)} NAV packs in {vob_path.name}")
    
    if not nav_packs:
        return None
    
    # Parse button configurations from each NAV pack
    all_configs: list[ButtonConfiguration] = []
    
    for pack_idx, nav_pack in nav_packs:
        config = parse_button_info_from_nav_pack(nav_pack, pack_idx)
        if config:
            all_configs.append(config)
    
    logger.info(f"BTN_IT analysis: {len(all_configs)} NAV packs with button data")
    
    if not all_configs:
        return None
    
    # Deduplicate configurations by signature
    unique_configs: list[ButtonConfiguration] = []
    seen_signatures = set()
    
    for config in all_configs:
        sig = config.signature()
        if sig not in seen_signatures:
            config.config_id = len(unique_configs)
            unique_configs.append(config)
            seen_signatures.add(sig)
        else:
            # Merge NAV pack indices for duplicate configs
            for existing in unique_configs:
                if existing.signature() == sig:
                    existing.nav_pack_indices.extend(config.nav_pack_indices)
                    break
    
    logger.info(f"BTN_IT analysis: {len(unique_configs)} unique button configurations (pages)")
    
    # Build navigation graph (all buttons, not just active ones)
    navigation_graph: dict[int, dict[str, int]] = {}
    
    for config in unique_configs:
        for btn_idx, btn_info in config.buttons.items():
            if btn_idx not in navigation_graph:
                navigation_graph[btn_idx] = {}
            
            if btn_info.nav_up:
                navigation_graph[btn_idx]["up"] = btn_info.nav_up
            if btn_info.nav_down:
                navigation_graph[btn_idx]["down"] = btn_info.nav_down
            if btn_info.nav_left:
                navigation_graph[btn_idx]["left"] = btn_info.nav_left
            if btn_info.nav_right:
                navigation_graph[btn_idx]["right"] = btn_info.nav_right
    
    logger.info(f"BTN_IT analysis: navigation graph has {len(navigation_graph)} button nodes")
    
    # Log configuration details
    for config in unique_configs:
        active_btns = [idx for idx, btn in config.buttons.items() if btn.active]
        logger.info(
            f"  Page {config.config_id}: {config.active_button_count} active buttons "
            f"(indices {config.active_button_range[0]}-{config.active_button_range[1]}), "
            f"found in NAV packs: {config.nav_pack_indices[:3]}{'...' if len(config.nav_pack_indices) > 3 else ''}"
        )
        logger.debug(f"    Active button indices: {active_btns}")
    
    analysis = MenuPageAnalysis(
        vob_path=vob_path,
        total_nav_packs=len(nav_packs),
        nav_packs_with_buttons=len(all_configs),
        configurations=unique_configs,
        page_count=len(unique_configs),
        navigation_graph=navigation_graph,
    )
    
    return analysis


def assign_buttons_to_pages(
    expected_button_count: int,
    detected_button_indices: list[int],
    page_analysis: MenuPageAnalysis | None,
) -> dict[int, int]:
    """
    Assign button indices to page numbers using BTN_IT analysis and heuristics.
    
    Strategy:
    1. Buttons detected visually are assigned to their most likely page
    2. Undetected buttons are assigned based on BTN_IT configuration differences
    3. If button appears in multiple pages, prefer the page where it's unique or most prominent
    
    Args:
        expected_button_count: Total number of buttons expected (e.g., 3)
        detected_button_indices: List of button indices successfully detected (0-based, e.g., [0, 1])
        page_analysis: BTN_IT analysis result, or None if unavailable
    
    Returns:
        Dict mapping button_index (0-based) -> page_number (0-based)
        Example: {0: 0, 1: 0, 2: 1} means btn1 and btn2 on page 0, btn3 on page 1
    """
    logger = logging.getLogger(__name__)
    
    button_to_page: dict[int, int] = {}
    
    # If no BTN_IT analysis, assign all to page 0
    if page_analysis is None or page_analysis.page_count == 0:
        logger.info("BTN_IT assignment: no page analysis, assigning all buttons to page 0")
        for btn_idx in range(expected_button_count):
            button_to_page[btn_idx] = 0
        return button_to_page
    
    logger.info(f"BTN_IT assignment: {page_analysis.page_count} pages detected")
    logger.info(f"  Expected buttons: {expected_button_count}, Detected: {len(detected_button_indices)}")
    
    # Map our button indices (0-based) to BTN_IT button indices (1-based)
    # Assumption: btn0 -> button 1, btn1 -> button 2, etc. (sequential mapping)
    
    # First, analyze which BTN_IT button indices appear on which pages
    btn_it_pages: dict[int, list[int]] = {}  # btn_it_index -> [page_nums]
    
    for page_num, config in enumerate(page_analysis.configurations):
        for btn_it_idx, btn_info in config.buttons.items():
            if btn_info.active:
                if btn_it_idx not in btn_it_pages:
                    btn_it_pages[btn_it_idx] = []
                btn_it_pages[btn_it_idx].append(page_num)
    
    # Strategy: Assign detected buttons to first page, undetected to later pages
    # This handles the common case where page 1 shows some buttons, page 2 shows others
    
    for btn_idx in range(expected_button_count):
        btn_it_index = btn_idx + 1
        
        # Check which pages this BTN_IT button appears on
        if btn_it_index in btn_it_pages:
            pages = btn_it_pages[btn_it_index]
            
            if btn_idx in detected_button_indices:
                # Detected button: assign to first page (most likely visible)
                page_num = pages[0]
                button_to_page[btn_idx] = page_num
                logger.info(
                    f"  btn{btn_idx+1} (BTN_IT index {btn_it_index}) -> page {page_num} "
                    f"[DETECTED, appears on pages: {pages}]"
                )
            else:
                # Undetected button: if it appears on multiple pages, prefer later pages
                # (likely not visible on page 1, so must be on page 2)
                if len(pages) > 1:
                    # Appears on multiple pages - prefer the LAST page
                    page_num = pages[-1]
                    button_to_page[btn_idx] = page_num
                    logger.info(
                        f"  btn{btn_idx+1} (BTN_IT index {btn_it_index}) -> page {page_num} "
                        f"[FALLBACK, appears on pages {pages}, choosing last]"
                    )
                else:
                    # Only on one page
                    page_num = pages[0]
                    button_to_page[btn_idx] = page_num
                    logger.info(
                        f"  btn{btn_idx+1} (BTN_IT index {btn_it_index}) -> page {page_num} "
                        f"[FALLBACK, only on this page]"
                    )
        else:
            # Button not found in BTN_IT, distribute heuristically
            buttons_per_page = expected_button_count // page_analysis.page_count
            if buttons_per_page == 0:
                buttons_per_page = 1
            
            page_num = min(btn_idx // buttons_per_page, page_analysis.page_count - 1)
            button_to_page[btn_idx] = page_num
            logger.info(
                f"  btn{btn_idx+1} (BTN_IT index {btn_it_index}) -> page {page_num} "
                f"[HEURISTIC: not in BTN_IT]"
            )
    
    return button_to_page
