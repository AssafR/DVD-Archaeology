from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable
import time
import logging

from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.libdvdread_compat import (
    decode_btn_it_rect,
    NavPackButtons,
    parse_c_adt,
    parse_nav_pack_buttons,
    parse_vobu_admap,
    read_u16,
    read_u32,
)
from dvdmenu_extract.util.libdvdread_spu import find_spu_button_rects, iter_spu_packets


@dataclass
class DvdIfoCell:
    cell_id: int
    start_time: float
    end_time: float
    first_sector: int | None = None
    last_sector: int | None = None
    vob_id: int | None = None


@dataclass
class DvdIfoPgc:
    pgc_id: int
    cells: list[DvdIfoCell]


@dataclass
class DvdIfoTitle:
    title_id: int
    pgcs: list[DvdIfoPgc]


def _read_u16(data: bytes, offset: int) -> int:
    return read_u16(data, offset)


def _read_u32(data: bytes, offset: int) -> int:
    return read_u32(data, offset)


def _parse_c_adt(data: bytes, sector_offset: int) -> dict[tuple[int, int], tuple[int, int]]:
    return parse_c_adt(data, sector_offset)


def parse_vts_c_adt(ifo_path: Path) -> dict[tuple[int, int], tuple[int, int]]:
    data = ifo_path.read_bytes()
    return _parse_c_adt(data, 0x00E0)


def parse_vtsm_c_adt(ifo_path: Path) -> dict[tuple[int, int], tuple[int, int]]:
    data = ifo_path.read_bytes()
    return _parse_c_adt(data, 0x00D8)


def parse_vts_vobu_admap(ifo_path: Path, sector_offset: int) -> list[int]:
    data = ifo_path.read_bytes()
    return parse_vobu_admap(data, sector_offset)


def parse_vts_pgci_cell_positions(
    ifo_path: Path,
) -> dict[int, list[tuple[int, int]]]:
    data = ifo_path.read_bytes()
    if len(data) < 0x00D0:
        return {}
    pgci_sector = _read_u32(data, 0x00CC)
    if pgci_sector == 0:
        return {}
    pgci_offset = pgci_sector * 2048
    if pgci_offset + 8 > len(data):
        return {}
    pgc_count = _read_u16(data, pgci_offset)
    entry_offset = pgci_offset + 8
    pgc_positions: dict[int, list[tuple[int, int]]] = {}
    for pgc_index in range(pgc_count):
        entry = entry_offset + (pgc_index * 8)
        if entry + 8 > len(data):
            break
        pgc_rel = _read_u32(data, entry + 4)
        pgc_start = pgci_offset + pgc_rel
        if pgc_start + 0x00EC > len(data):
            continue
        cell_count = data[pgc_start + 0x0003]
        cell_pos_rel = _read_u16(data, pgc_start + 0x00EA)
        if cell_pos_rel == 0:
            continue
        cell_pos_start = pgc_start + cell_pos_rel
        positions: list[tuple[int, int]] = []
        for cell_idx in range(cell_count):
            pos_offset = cell_pos_start + (cell_idx * 4)
            if pos_offset + 4 > len(data):
                break
            vob_id = _read_u16(data, pos_offset)
            cell_idn = data[pos_offset + 3]
            positions.append((vob_id, cell_idn))
        if positions:
            pgc_positions[pgc_index + 1] = positions
    return pgc_positions


def parse_dvd_nav_menu_buttons(video_ts: Path, debug_spu: bool = False) -> list[dict]:
    """Parses menu button geometry from IFO files.

    Uses VMGM/VTSM PGC tables to locate button data (more reliable than PGCI_UT).
    """
    buttons: list[dict] = []

    logger = logging.getLogger(__name__)

    # 1. Try SPU-based button detection from menu VOBs.
    vtsm_targets: list[dict] = []
    for title_id, ifo_path in _iter_vts_ifo_files(video_ts):
        vtsm_targets.extend(
            _parse_pgcit_menu_buttons(
                ifo_path,
                f"VTSM_{title_id:02d}",
                title_id=title_id,
                pgc_table_offset=0x00D4,
            )
        )

    for title_id, ifo_path in _iter_vts_ifo_files(video_ts):
        spu_buttons = _parse_vtsm_spu_buttons(
            video_ts, title_id, ifo_path, debug_spu=debug_spu
        )
        if spu_buttons:
            logger.info(
                "nav_parse: %s VTSM SPU buttons=%d",
                ifo_path.name,
                len(spu_buttons),
            )
            _apply_spu_targets(spu_buttons, vtsm_targets)
            buttons.extend(spu_buttons)
    if buttons:
        return buttons

    # 2. Try NAV pack button tables from menu VOBs.
    for title_id, ifo_path in _iter_vts_ifo_files(video_ts):
        navpack_buttons = _parse_vtsm_navpack_buttons(video_ts, title_id, ifo_path)
        if navpack_buttons:
            logger.info(
                "nav_parse: %s VTSM navpack buttons=%d",
                ifo_path.name,
                len(navpack_buttons),
            )
            buttons.extend(navpack_buttons)
    if buttons:
        return buttons

    # 3. Try NAV pack button tables from title VOBs using PGCI cell positions.
    title_ids = [title_id for title_id, _ in _iter_vts_ifo_files(video_ts)]
    for title_id, ifo_path in _iter_vts_ifo_files(video_ts):
        title_nav_buttons = _parse_vts_title_navpack_buttons(
            video_ts, title_id, ifo_path, title_ids
        )
        if title_nav_buttons:
            logger.info(
                "nav_parse: %s title navpack buttons=%d",
                ifo_path.name,
                len(title_nav_buttons),
            )
            buttons.extend(title_nav_buttons)
            break
    if buttons:
        return buttons

    # 3. VIDEO_TS.IFO (VMGM PGCIT at 0x00C8)
    vmgm_ifo = video_ts / "VIDEO_TS.IFO"
    if vmgm_ifo.is_file():
        vmgm_buttons = _parse_pgcit_menu_buttons(
            vmgm_ifo,
            "VMGM",
            pgc_table_offset=0x00C8,
        )
        logger.info("nav_parse: VMGM buttons=%d", len(vmgm_buttons))
        buttons.extend(vmgm_buttons)

    # 4. VTS_XX_0.IFO (VTSM PGCIT at 0x00D4)
    for title_id, ifo_path in _iter_vts_ifo_files(video_ts):
        vts_buttons = _parse_pgcit_menu_buttons(
            ifo_path,
            f"VTSM_{title_id:02d}",
            title_id=title_id,
            pgc_table_offset=0x00D4,
        )
        logger.info(
            "nav_parse: %s VTSM buttons=%d (PGCIT 0x00D4)",
            ifo_path.name,
            len(vts_buttons),
        )
        buttons.extend(vts_buttons)

    return buttons


def _parse_vtsm_navpack_buttons(
    video_ts: Path,
    title_id: int,
    ifo_path: Path,
) -> list[dict]:
    data = ifo_path.read_bytes()
    if len(data) < 0x00D4:
        return []

    pgc_sector = _read_u32(data, 0x00D4)
    if pgc_sector == 0:
        return []
    pgc_table_start = pgc_sector * 2048
    if pgc_table_start + 8 > len(data):
        return []
    nb_pgc = _read_u16(data, pgc_table_start)
    if nb_pgc == 0:
        return []

    c_adt = parse_vtsm_c_adt(ifo_path)
    vobu_admap = parse_vts_vobu_admap(ifo_path, 0x00DC)
    vob_map = _build_menu_vob_sector_map(video_ts, title_id)
    if not vob_map:
        return []

    buttons: list[dict] = []
    btn_idx = 1
    default_sector_range = None
    if c_adt:
        default_sector_range = next(iter(c_adt.values()))
    vob_end = max(end for _, _, end in vob_map)
    for pgc_idx in range(nb_pgc):
        entry = pgc_table_start + 8 + (pgc_idx * 8)
        if entry + 8 > len(data):
            break
        pgc_rel = _read_u32(data, entry + 4)
        if pgc_rel == 0:
            continue
        pgc_start = pgc_table_start + pgc_rel
        if pgc_start + 0x00EC > len(data):
            continue
        cell_pos_rel = _read_u16(data, pgc_start + 0x00EA)
        sector_range = None
        if cell_pos_rel != 0:
            cell_pos_start = pgc_start + cell_pos_rel
            if cell_pos_start + 4 <= len(data):
                vob_id = _read_u16(data, cell_pos_start)
                cell_idn = data[cell_pos_start + 3]
                sector_range = c_adt.get((vob_id, cell_idn))
        if not sector_range:
            sector_range = default_sector_range
        if not sector_range:
            sector_range = (0, vob_end)
        first_sector, last_sector = sector_range
        rects = _scan_navpacks_for_buttons(
            vob_map=vob_map,
            vobu_admap=vobu_admap,
            first_sector=first_sector,
            last_sector=last_sector,
        )
        if not rects:
            continue
        menu_id = f"VTSM_{title_id:02d}_pgc{pgc_idx + 1:02d}"
        for rect in rects:
            x1, y1, x2, y2 = rect
            buttons.append(
                {
                    "button_id": f"btn{btn_idx}",
                    "menu_id": menu_id,
                    "selection_rect": {
                        "x": x1,
                        "y": y1,
                        "w": x2 - x1 + 1,
                        "h": y2 - y1 + 1,
                    },
                    "highlight_rect": {
                        "x": x1,
                        "y": y1,
                        "w": x2 - x1 + 1,
                        "h": y2 - y1 + 1,
                    },
                    "title_id": title_id,
                    "pgc_id": pgc_idx + 1,
                }
            )
            btn_idx += 1

    return buttons


def _parse_title_navpack_buttons(
    video_ts: Path,
    title_id: int,
    ifo_path: Path,
    title_ids: list[int],
) -> list[dict]:
    data = ifo_path.read_bytes()
    if len(data) < 0x00D4:
        return []

    c_adt = parse_vts_c_adt(ifo_path)
    vobu_admap = parse_vts_vobu_admap(ifo_path, 0x00DC)
    vob_map = _build_vob_sector_map(video_ts, title_id)
    if not vob_map:
        return []

    default_sector_range = None
    if c_adt:
        default_sector_range = next(iter(c_adt.values()))
    vob_end = max(end for _, _, end in vob_map)
    first_sector, last_sector = (
        default_sector_range if default_sector_range else (0, vob_end)
    )

    rects = _scan_navpacks_for_buttons(
        vob_map=vob_map,
        vobu_admap=vobu_admap,
        first_sector=first_sector,
        last_sector=last_sector,
    )
    if not rects:
        return []

    # Use the largest rects to avoid arrow buttons.
    rects = sorted(
        rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), reverse=True
    )
    rects = rects[: len(title_ids)]
    rects = sorted(rects, key=lambda r: (r[1], r[0]))

    buttons: list[dict] = []
    btn_idx = 1
    for rect, target_title in zip(rects, title_ids, strict=False):
        x1, y1, x2, y2 = rect
        buttons.append(
            {
                "button_id": f"btn{btn_idx}",
                "menu_id": "dvd_root",
                "selection_rect": {
                    "x": x1,
                    "y": y1,
                    "w": x2 - x1 + 1,
                    "h": y2 - y1 + 1,
                },
                "highlight_rect": {
                    "x": x1,
                    "y": y1,
                    "w": x2 - x1 + 1,
                    "h": y2 - y1 + 1,
                },
                "title_id": target_title,
                "pgc_id": 1,
            }
        )
        btn_idx += 1
    return buttons


def _parse_vts_title_navpack_buttons(
    video_ts: Path,
    title_id: int,
    ifo_path: Path,
    title_ids: list[int],
) -> list[dict]:
    """
    Parse NAV-pack button rectangles from title VOBs using PGCI cell positions.

    This follows the DVD IFO layout used by libdvdread:
    - VTS_PGCI table provides PGC -> cell (vob_id, cell_id) positions.
    - VTS_C_ADT maps (vob_id, cell_id) to sector ranges.
    We scan those ranges for NAV packs containing BTN_IT tables.
    """
    c_adt = parse_vts_c_adt(ifo_path)
    pgc_positions = parse_vts_pgci_cell_positions(ifo_path)
    vobu_admap = parse_vts_vobu_admap(ifo_path, 0x00DC)
    vob_map = _build_vob_sector_map(video_ts, title_id)
    if not vob_map:
        return []

    ranges: list[tuple[int, int]] = []
    for positions in pgc_positions.values():
        for vob_id, cell_idn in positions:
            sector_range = c_adt.get((vob_id, cell_idn))
            if sector_range:
                ranges.append(sector_range)
    if not ranges:
        vob_end = max(end for _, _, end in vob_map)
        ranges = [(0, vob_end)]

    best_rects: list[tuple[int, int, int, int]] = []
    for first_sector, last_sector in ranges:
        rects = _scan_navpacks_for_buttons(
            vob_map=vob_map,
            vobu_admap=vobu_admap,
            first_sector=first_sector,
            last_sector=last_sector,
        )
        if rects and len(rects) >= len(best_rects):
            best_rects = rects
        if len(best_rects) >= len(title_ids):
            break

    if not best_rects:
        return []

    # Use the largest rects to avoid arrow buttons.
    best_rects = sorted(
        best_rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), reverse=True
    )
    best_rects = best_rects[: len(title_ids)]
    best_rects = sorted(best_rects, key=lambda r: (r[1], r[0]))

    buttons: list[dict] = []
    for idx, (rect, target_title) in enumerate(
        zip(best_rects, title_ids, strict=False), start=1
    ):
        x1, y1, x2, y2 = rect
        buttons.append(
            {
                "button_id": f"btn{idx}",
                "menu_id": "dvd_root",
                "selection_rect": {
                    "x": x1,
                    "y": y1,
                    "w": x2 - x1 + 1,
                    "h": y2 - y1 + 1,
                },
                "highlight_rect": {
                    "x": x1,
                    "y": y1,
                    "w": x2 - x1 + 1,
                    "h": y2 - y1 + 1,
                },
                "title_id": target_title,
                "pgc_id": 1,
            }
        )
    return buttons


def _parse_vtsm_spu_buttons(
    video_ts: Path,
    title_id: int,
    ifo_path: Path,
    debug_spu: bool,
) -> list[dict]:
    data = ifo_path.read_bytes()
    if len(data) < 0x00D4:
        return []

    pgc_sector = _read_u32(data, 0x00D4)
    if pgc_sector == 0:
        return []
    pgc_table_start = pgc_sector * 2048
    if pgc_table_start + 8 > len(data):
        return []
    nb_pgc = _read_u16(data, pgc_table_start)
    if nb_pgc == 0:
        return []

    c_adt = parse_vtsm_c_adt(ifo_path)
    vobu_admap = parse_vts_vobu_admap(ifo_path, 0x00DC)
    vob_map = _build_menu_vob_sector_map(video_ts, title_id)
    if not vob_map:
        return []

    default_sector_range = None
    if c_adt:
        default_sector_range = next(iter(c_adt.values()))

    buttons: list[dict] = []
    btn_idx = 1
    last_rects: list[tuple[int, int, int, int]] | None = None
    def _rect_area(rect: tuple[int, int, int, int]) -> int:
        x1, y1, x2, y2 = rect
        return max(0, x2 - x1 + 1) * max(0, y2 - y1 + 1)

    def _rect_overlap_ratio(
        a: tuple[int, int, int, int], b: tuple[int, int, int, int]
    ) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        if ix2 < ix1 or iy2 < iy1:
            return 0.0
        inter = (ix2 - ix1 + 1) * (iy2 - iy1 + 1)
        denom = min(_rect_area(a), _rect_area(b))
        return (inter / denom) if denom else 0.0

    for pgc_idx in range(nb_pgc):
        entry = pgc_table_start + 8 + (pgc_idx * 8)
        if entry + 8 > len(data):
            break
        pgc_rel = _read_u32(data, entry + 4)
        if pgc_rel == 0:
            continue
        pgc_start = pgc_table_start + pgc_rel
        if pgc_start + 0x00EC > len(data):
            continue
        cell_pos_rel = _read_u16(data, pgc_start + 0x00EA)
        sector_range = None
        if cell_pos_rel != 0:
            cell_pos_start = pgc_start + cell_pos_rel
            if cell_pos_start + 4 <= len(data):
                vob_id = _read_u16(data, cell_pos_start)
                cell_idn = data[cell_pos_start + 3]
                sector_range = c_adt.get((vob_id, cell_idn))
        if not sector_range:
            sector_range = default_sector_range
        if not sector_range:
            continue
        first_sector, last_sector = sector_range
        rects, nav_buttons = _scan_spu_for_buttons(
            vob_map=vob_map,
            vobu_admap=vobu_admap,
            first_sector=first_sector,
            last_sector=last_sector,
        )
        if not rects:
            continue
        if last_rects == rects:
            continue
        last_rects = rects
        ordered_rects = _order_spu_rects(rects)
        menu_id = f"VTSM_{title_id:02d}_pgc{pgc_idx + 1:02d}"
        if debug_spu:
            logger = logging.getLogger(__name__)
            logger.info("nav_parse: SPU rects %s: %s", menu_id, ordered_rects)
        candidates: list[tuple[int, tuple[int, int, int, int]]] = []
        if nav_buttons:
            for idx in nav_buttons.active_indices:
                if 0 < idx <= len(nav_buttons.rects):
                    rect = nav_buttons.rects[idx - 1]
                    if rect is not None:
                        candidates.append((idx, rect))
        used_indices: set[int] = set()

        for idx, rect in enumerate(ordered_rects):
            x1, y1, x2, y2 = rect
            nav_links = None
            nav_index = None
            if candidates:
                # Match by spatial overlap to NAV-pack button indices.
                best = None
                best_score = 0.0
                for nav_idx, nav_rect in candidates:
                    if nav_idx in used_indices:
                        continue
                    score = _rect_overlap_ratio(rect, nav_rect)
                    if score > best_score:
                        best_score = score
                        best = nav_idx
                if best is not None and best_score > 0:
                    used_indices.add(best)
                    nav_links = nav_buttons.links[best - 1] if nav_buttons else None
                    nav_index = nav_links.get("index")
            buttons.append(
                {
                    "button_id": f"btn{btn_idx}",
                    "menu_id": menu_id,
                    "selection_rect": {
                        "x": x1,
                        "y": y1,
                        "w": x2 - x1 + 1,
                        "h": y2 - y1 + 1,
                    },
                    "highlight_rect": {
                        "x": x1,
                        "y": y1,
                        "w": x2 - x1 + 1,
                        "h": y2 - y1 + 1,
                    },
                    "title_id": title_id,
                    "pgc_id": pgc_idx + 1,
                    "nav_links": nav_links,
                    "nav_index": nav_index,
                }
            )
            btn_idx += 1

    return buttons


def _order_spu_rects(
    rects: list[tuple[int, int, int, int]]
) -> list[tuple[int, int, int, int]]:
    if not rects:
        return []
    rects = rects[:]
    centers = [((r[0] + r[2]) / 2, (r[1] + r[3]) / 2) for r in rects]
    x_values = [c[0] for c in centers]
    min_x = min(x_values)
    max_x = max(x_values)
    spread = max_x - min_x
    if spread < 40:
        rects.sort(key=lambda r: (r[1], r[0]))
        return rects
    median_x = sorted(x_values)[len(x_values) // 2]
    left = [r for r in rects if ((r[0] + r[2]) / 2) <= median_x]
    right = [r for r in rects if ((r[0] + r[2]) / 2) > median_x]
    left.sort(key=lambda r: r[1])
    right.sort(key=lambda r: r[1])
    return left + right


def _apply_spu_targets(spu_buttons: list[dict], ifo_buttons: list[dict]) -> None:
    if not spu_buttons or not ifo_buttons:
        return
    ifo_by_menu: dict[str, list[dict]] = {}
    for btn in ifo_buttons:
        menu_id = btn.get("menu_id") or "unknown_menu"
        ifo_by_menu.setdefault(menu_id, []).append(btn)
    for menu_id, entries in ifo_by_menu.items():
        entries.sort(
            key=lambda b: int(str(b.get("button_id", "btn0")).replace("btn", ""))
        )

    spu_by_menu: dict[str, list[dict]] = {}
    for btn in spu_buttons:
        menu_id = btn.get("menu_id") or "unknown_menu"
        spu_by_menu.setdefault(menu_id, []).append(btn)

    for menu_id, rects in spu_by_menu.items():
        rects.sort(
            key=lambda b: (
                int((b.get("selection_rect") or {}).get("y", 0)),
                int((b.get("selection_rect") or {}).get("x", 0)),
            )
        )
        targets = ifo_by_menu.get(menu_id)
        if not targets:
            # Fall back to any VTSM targets with same title_id
            title_id = rects[0].get("title_id")
            targets = [
                btn
                for btn in ifo_buttons
                if btn.get("title_id") == title_id
            ]
            targets.sort(
                key=lambda b: int(
                    str(b.get("button_id", "btn0")).replace("btn", "")
                )
            )
        if not targets:
            continue
        for btn, target in zip(rects, targets, strict=False):
            if target.get("pgc_id") is not None:
                btn["pgc_id"] = target.get("pgc_id")
            if target.get("title_id") is not None:
                btn["title_id"] = target.get("title_id")


def _build_vob_sector_map(
    video_ts: Path, title_id: int
) -> list[tuple[Path, int, int]]:
    sector_size = 2048
    mappings: list[tuple[Path, int, int]] = []
    current_sector = 0
    for path in sorted(video_ts.glob(f"VTS_{title_id:02d}_*.VOB")):
        sector_count = path.stat().st_size // sector_size
        if sector_count == 0:
            continue
        start = current_sector
        end = current_sector + sector_count - 1
        mappings.append((path, start, end))
        current_sector += sector_count
    return mappings


def _build_menu_vob_sector_map(
    video_ts: Path, title_id: int
) -> list[tuple[Path, int, int]]:
    """Prefer the menu VOB (VTS_XX_0.VOB) to avoid scanning program VOBs."""
    sector_size = 2048
    mappings: list[tuple[Path, int, int]] = []
    current_sector = 0
    menu_vobs = sorted(video_ts.glob(f"VTS_{title_id:02d}_0.VOB"))
    for path in menu_vobs:
        sector_count = path.stat().st_size // sector_size
        if sector_count == 0:
            continue
        start = current_sector
        end = current_sector + sector_count - 1
        mappings.append((path, start, end))
        current_sector += sector_count
    if mappings:
        return mappings
    return _build_vob_sector_map(video_ts, title_id)


def _read_vob_sector_at(
    vob_map: list[tuple[Path, int, int]], sector: int
) -> bytes | None:
    for path, start, end in vob_map:
        if start <= sector <= end:
            offset = (sector - start) * 2048
            try:
                with path.open("rb") as handle:
                    handle.seek(offset)
                    data = handle.read(2048)
            except OSError:
                return None
            if len(data) != 2048:
                return None
            return data
    return None


def _read_vob_sectors(
    vob_map: list[tuple[Path, int, int]], start_sector: int, count: int
) -> bytes | None:
    if count <= 0:
        return None
    for path, start, end in vob_map:
        if start <= start_sector <= end:
            max_count = end - start_sector + 1
            count = min(count, max_count)
            offset = (start_sector - start) * 2048
            try:
                with path.open("rb") as handle:
                    handle.seek(offset)
                    data = handle.read(count * 2048)
            except OSError:
                return None
            return data if data else None
    return None


def _scan_navpacks_for_buttons(
    vob_map: list[tuple[Path, int, int]],
    vobu_admap: list[int],
    first_sector: int,
    last_sector: int,
) -> list[tuple[int, int, int, int]]:
    candidates = [sector for sector in vobu_admap if first_sector <= sector <= last_sector]
    if not candidates:
        candidates = list(range(first_sector, min(last_sector, first_sector + 8000) + 1))
    max_candidates = 1200
    if len(candidates) > max_candidates:
        step = max(1, len(candidates) // max_candidates)
        candidates = candidates[::step][:max_candidates]
        logging.getLogger(__name__).info(
            "nav_parse: navpack scan capped to %d samples (stride=%d)",
            len(candidates),
            step,
        )

    best_rects: list[tuple[int, int, int, int]] = []
    deadline = time.monotonic() + 12.0
    total = len(candidates)
    for idx, sector in enumerate(candidates, start=1):
        if time.monotonic() >= deadline:
            logging.getLogger(__name__).warning(
                "nav_parse: navpack scan timed out after %.1fs",
                12.0,
            )
            break
        if idx == 1 or idx % 200 == 0 or idx == total:
            progress = (idx / total) * 100 if total else 100.0
            logging.getLogger(__name__).info(
                "nav_parse: navpack scan progress %d/%d (%.0f%%, best_rects=%d)",
                idx,
                total,
                progress,
                len(best_rects),
            )
        nav_pack = _read_vob_sector_at(vob_map, sector)
        if not nav_pack:
            continue
        rects = _parse_navpack_button_rects(nav_pack)
        if rects and len(rects) >= len(best_rects):
            best_rects = rects
        if len(best_rects) >= 12:
            break
    return best_rects


def _scan_spu_for_buttons(
    vob_map: list[tuple[Path, int, int]],
    vobu_admap: list[int],
    first_sector: int,
    last_sector: int,
) -> tuple[list[tuple[int, int, int, int]], NavPackButtons | None]:
    candidates = [sector for sector in vobu_admap if first_sector <= sector <= last_sector]
    if not candidates:
        candidates = list(range(first_sector, min(last_sector, first_sector + 8000) + 1))
    max_candidates = 600
    if len(candidates) > max_candidates:
        step = max(1, len(candidates) // max_candidates)
        candidates = candidates[::step][:max_candidates]
        logging.getLogger(__name__).info(
            "nav_parse: SPU scan capped to %d samples (stride=%d)",
            len(candidates),
            step,
        )

    best_rects: list[tuple[int, int, int, int]] = []
    best_nav_buttons: NavPackButtons | None = None
    deadline = time.monotonic() + 15.0
    total = len(candidates)
    for idx, sector in enumerate(candidates, start=1):
        if time.monotonic() >= deadline:
            logging.getLogger(__name__).warning(
                "nav_parse: SPU scan timed out after %.1fs",
                15.0,
            )
            break
        if idx == 1 or idx % 150 == 0 or idx == total:
            progress = (idx / total) * 100 if total else 100.0
            logging.getLogger(__name__).info(
                "nav_parse: SPU scan progress %d/%d (%.0f%%, best_rects=%d)",
                idx,
                total,
                progress,
                len(best_rects),
            )
        data = _read_vob_sectors(vob_map, sector, 1024)
        if not data:
            continue
        nav_pack = _read_vob_sector_at(vob_map, sector)
        nav_buttons = parse_nav_pack_buttons(nav_pack) if nav_pack else None
        if nav_buttons and (nav_buttons.hli_ss & 0x03) != 0x01:
            nav_buttons = None
        buffers: dict[int, bytearray] = {}
        expected_sizes: dict[int, int] = {}
        for substream_id, payload in iter_spu_packets(data):
            if substream_id not in buffers:
                buffers[substream_id] = bytearray()
            buffers[substream_id].extend(payload)
            if substream_id not in expected_sizes and len(buffers[substream_id]) >= 2:
                size = read_u16(buffers[substream_id], 0)
                expected_sizes[substream_id] = size if size > 0 else 0
            expected = expected_sizes.get(substream_id, 0)
            buffer = buffers[substream_id]
            if expected > 0 and len(buffer) >= expected:
                packet = bytes(buffer[:expected])
                buffers[substream_id] = bytearray(buffer[expected:])
                expected_sizes[substream_id] = (
                    read_u16(buffers[substream_id], 0)
                    if len(buffers[substream_id]) >= 2
                    else 0
                )
                rects = find_spu_button_rects(packet)
                if rects and len(rects) >= len(best_rects):
                    best_rects = rects
                    best_nav_buttons = nav_buttons
            elif expected == 0 and len(buffer) >= 4:
                rects = find_spu_button_rects(bytes(buffer))
                if rects and len(rects) >= len(best_rects):
                    best_rects = rects
                    best_nav_buttons = nav_buttons
        if len(best_rects) >= 12:
            break
    return best_rects, best_nav_buttons


def _parse_navpack_button_rects(nav_pack: bytes) -> list[tuple[int, int, int, int]]:
    nav_buttons = parse_nav_pack_buttons(nav_pack)
    if nav_buttons is None:
        return []
    if (nav_buttons.hli_ss & 0x03) != 0x01:
        return []
    rects = [
        nav_buttons.rects[idx - 1]
        for idx in nav_buttons.active_indices
        if 0 < idx <= len(nav_buttons.rects)
    ]
    rects = [rect for rect in rects if rect is not None]
    if not rects:
        return []
    return rects


def _parse_pgcit_menu_buttons(
    ifo_path: Path,
    menu_id: str,
    title_id: int | None = None,
    pgc_table_offset: int = 0x00C8,
) -> list[dict]:
    data = ifo_path.read_bytes()
    if len(data) < 0x00D4:
        return []
    
    logger = logging.getLogger(__name__)
    # PGC table sector pointer
    pgc_sector = _read_u32(data, pgc_table_offset)
    if pgc_sector == 0:
        logger.info(
            "nav_parse: %s pgc_table_sector=0x0 (offset 0x%04X)",
            ifo_path.name,
            pgc_table_offset,
        )
        return []

    pgc_table_start = pgc_sector * 2048
    if pgc_table_start + 8 > len(data):
        return []

    nb_pgc = _read_u16(data, pgc_table_start)
    logger.info(
        "nav_parse: %s pgc_table_sector=%d (offset 0x%04X) nb_pgc=%d",
        ifo_path.name,
        pgc_sector,
        pgc_table_offset,
        nb_pgc,
    )

    buttons: list[dict] = []
    btn_idx = 1

    for pgc_idx in range(nb_pgc):
        pgc_entry_offset = pgc_table_start + 8 + (pgc_idx * 8)
        if pgc_entry_offset + 8 > len(data):
            break
        pgc_start_rel = _read_u32(data, pgc_entry_offset + 4)
        if pgc_start_rel == 0:
            continue
        pgc_start = pgc_table_start + pgc_start_rel
        if pgc_start + 0x00EC > len(data):
            continue
        buttons.extend(
            _parse_pgc_buttons(
                data=data,
                pgc_start=pgc_start,
                menu_id=menu_id,
                title_id=title_id,
                pgc_idx=pgc_idx,
                nb_pgc=nb_pgc,
                btn_idx_start=btn_idx,
            )
        )
        btn_idx = len(buttons) + 1

    return buttons


def _parse_pgc_buttons(
    data: bytes,
    pgc_start: int,
    menu_id: str,
    title_id: int | None,
    pgc_idx: int,
    nb_pgc: int,
    btn_idx_start: int,
) -> list[dict]:
    # Button table offset (heuristic across common header offsets)
    btn_tab_rel = 0
    for rel_off in (0x00E6, 0x00EA, 0x00E4):
        candidate = _read_u16(data, pgc_start + rel_off)
        if candidate != 0:
            btn_tab_rel = candidate
            break
    if btn_tab_rel == 0:
        return []

    btn_tab_start = pgc_start + btn_tab_rel
    if btn_tab_start + 6 > len(data):
        return []

    group_offsets = [
        _read_u16(data, btn_tab_start + 2),
        _read_u16(data, btn_tab_start + 4),
        _read_u16(data, btn_tab_start + 6),
    ]
    group_rel = next((offset for offset in group_offsets if offset != 0), 0)
    if group_rel == 0:
        return []

    group_start = btn_tab_start + group_rel
    if group_start + 2 > len(data):
        return []

    nb_buttons = data[group_start]
    menu_page_id = menu_id
    if nb_pgc > 1:
        menu_page_id = f"{menu_id}_pgc{pgc_idx + 1:02d}"

    buttons: list[dict] = []
    btn_idx = btn_idx_start
    for _ in range(nb_buttons):
        btn_offset = group_start + 2 + ((btn_idx - btn_idx_start) * 18)
        if btn_offset + 18 > len(data):
            break

        rect = decode_btn_it_rect(data[btn_offset : btn_offset + 18])
        if rect is None:
            btn_idx += 1
            continue
        x1, y1, x2, y2 = rect
        if x2 > 720 or y2 > 576:
            # Some IFOs store button coordinates on a 0..1023 grid.
            target_w = 720
            if y2 > 576:
                target_h = 576
            elif y2 > 480:
                target_h = 576
            else:
                target_h = 480
            x1 = round(x1 * target_w / 1024)
            x2 = round(x2 * target_w / 1024)
            y1 = round(y1 * target_h / 1024)
            y2 = round(y2 * target_h / 1024)
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        if x2 - x1 < 1 or y2 - y1 < 1:
            btn_idx += 1
            continue

        cmd = data[btn_offset + 12 : btn_offset + 20]
        target_title = None
        target_pgc = None

        if cmd[0] == 0x30 and cmd[1] == 0x02:
            target_title = cmd[5]
            target_pgc = 1
        elif cmd[0] == 0x30 and cmd[1] == 0x03:
            target_title = cmd[5]
            target_pgc = 1

        buttons.append(
            {
                "button_id": f"btn{btn_idx}",
                "menu_id": menu_page_id,
                "selection_rect": {
                    "x": x1,
                    "y": y1,
                    "w": x2 - x1 + 1,
                    "h": y2 - y1 + 1,
                },
                "highlight_rect": {
                    "x": x1,
                    "y": y1,
                    "w": x2 - x1 + 1,
                    "h": y2 - y1 + 1,
                },
                "title_id": target_title or (title_id if title_id else 1),
                "pgc_id": target_pgc or btn_idx,
            }
        )
        btn_idx += 1

    return buttons


def _playback_to_seconds(playback_time, framerate_map: dict[int, Fraction]) -> float:
    fps_key = playback_time.fps
    if fps_key not in framerate_map:
        raise ValidationError(f"Unsupported FPS key {fps_key}")
    fps = float(framerate_map[fps_key])
    total = (
        playback_time.hours * 3600
        + playback_time.minutes * 60
        + playback_time.seconds
        + (playback_time.frames / fps)
    )
    if total <= 0:
        raise ValidationError("Playback time must be positive")
    return total


def _iter_vts_ifo_files(video_ts: Path) -> Iterable[tuple[int, Path]]:
    for path in sorted(video_ts.glob("VTS_*_0.IFO")):
        parts = path.stem.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            yield int(parts[1]), path


def parse_dvd_ifo_titles(video_ts: Path) -> tuple[list[DvdIfoTitle] | None, str | None]:
    try:
        import pyparsedvd
    except Exception:
        return None, "pyparsedvd not available"

    ifo_files = list(_iter_vts_ifo_files(video_ts))
    if not ifo_files:
        return None, "no VTS_*_0.IFO files found"

    titles: list[DvdIfoTitle] = []
    global_cell_id = 1

    for title_id, ifo_path in ifo_files:
        try:
            with ifo_path.open("rb") as handle:
                pgci = pyparsedvd.load_vts_pgci(handle)
        except Exception:
            return None, f"failed parsing {ifo_path.name}"
        c_adt = parse_vts_c_adt(ifo_path)
        pgc_positions = parse_vts_pgci_cell_positions(ifo_path)

        pgcs: list[DvdIfoPgc] = []
        for pgc_index, program_chain in enumerate(pgci.program_chains, start=1):
            durations = [
                _playback_to_seconds(time, pyparsedvd.FRAMERATE)
                for time in program_chain.playback_times
            ]
            pgc_duration = _playback_to_seconds(
                program_chain.duration, pyparsedvd.FRAMERATE
            )
            if not durations:
                durations = [pgc_duration]
            else:
                total = sum(durations)
                if pgc_duration > total + 0.05:
                    durations[-1] = pgc_duration - sum(durations[:-1])
                elif pgc_duration < total - 0.05:
                    pgc_duration = total
            cumulative = 0.0
            cells: list[DvdIfoCell] = []
            playback_items = getattr(program_chain, "cell_playback", []) or []
            position_items = getattr(program_chain, "cell_positions", []) or []
            for idx, duration in enumerate(durations):
                start = cumulative
                end = cumulative + duration
                playback_item = playback_items[idx] if idx < len(playback_items) else None
                position_item = position_items[idx] if idx < len(position_items) else None
                vob_id = None
                cell_idn = None
                first_sector = None
                last_sector = None
                for source in (playback_item, position_item):
                    if source is None:
                        continue
                    vob_id = vob_id or getattr(
                        source,
                        "vob_id",
                        getattr(source, "vob_idn", None),
                    )
                    if vob_id is None:
                        vob_id = getattr(source, "vob_idn", None)
                    if cell_idn is None:
                        cell_idn = getattr(source, "cell_idn", None)
                    if cell_idn is None:
                        cell_idn = getattr(source, "cell_id", None)
                    if cell_idn is None:
                        cell_idn = getattr(source, "cell_number", None)
                    first_sector = first_sector or getattr(
                        source,
                        "first_sector",
                        getattr(source, "start_sector", None),
                    )
                    last_sector = last_sector or getattr(
                        source,
                        "last_sector",
                        getattr(source, "end_sector", None),
                    )
                if vob_id is None or cell_idn is None:
                    positions = pgc_positions.get(pgc_index, [])
                    if idx < len(positions):
                        vob_id, cell_idn = positions[idx]
                if first_sector is None or last_sector is None:
                    if vob_id is not None and cell_idn is not None:
                        sector_range = c_adt.get((int(vob_id), int(cell_idn)))
                    else:
                        sector_range = None
                    if sector_range is not None:
                        first_sector, last_sector = sector_range
                cells.append(
                    DvdIfoCell(
                        cell_id=global_cell_id,
                        start_time=start,
                        end_time=end,
                        first_sector=first_sector,
                        last_sector=last_sector,
                        vob_id=vob_id,
                    )
                )
                global_cell_id += 1
                cumulative = end
            pgcs.append(DvdIfoPgc(pgc_id=pgc_index, cells=cells))

        if pgcs:
            titles.append(DvdIfoTitle(title_id=title_id, pgcs=pgcs))

    if not titles:
        return None, "no program chains parsed"
    return titles, None
