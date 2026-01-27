from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable
import logging

from dvdmenu_extract.util.assertx import ValidationError


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
    return int.from_bytes(data[offset : offset + 2], byteorder="big", signed=False)


def _read_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], byteorder="big", signed=False)


def parse_vts_c_adt(ifo_path: Path) -> dict[tuple[int, int], tuple[int, int]]:
    data = ifo_path.read_bytes()
    if len(data) < 0x00E4:
        return {}
    table_sector = _read_u32(data, 0x00E0)
    if table_sector == 0:
        return {}
    table_offset = table_sector * 2048
    if table_offset + 8 > len(data):
        return {}
    end_addr = _read_u32(data, table_offset + 4)
    table_end = table_offset + end_addr + 1
    if table_end > len(data):
        table_end = len(data)
    entries_offset = table_offset + 8
    mapping: dict[tuple[int, int], tuple[int, int]] = {}
    offset = entries_offset
    while offset + 12 <= table_end:
        vob_idn = _read_u16(data, offset)
        cell_idn = data[offset + 2]
        start_sector = _read_u32(data, offset + 4)
        last_sector = _read_u32(data, offset + 8)
        mapping[(vob_idn, cell_idn)] = (start_sector, last_sector)
        offset += 12
    return mapping


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


def parse_dvd_nav_menu_buttons(video_ts: Path) -> list[dict]:
    """Parses menu button geometry from IFO files.

    Uses VMGM/VTSM PGC tables to locate button data (more reliable than PGCI_UT).
    """
    buttons: list[dict] = []

    logger = logging.getLogger(__name__)

    # 1. VIDEO_TS.IFO (VMGM PGCIT at 0x00C8)
    vmgm_ifo = video_ts / "VIDEO_TS.IFO"
    if vmgm_ifo.is_file():
        vmgm_buttons = _parse_pgcit_menu_buttons(
            vmgm_ifo,
            "VMGM",
            pgc_table_offset=0x00C8,
        )
        logger.info("nav_parse: VMGM buttons=%d", len(vmgm_buttons))
        buttons.extend(vmgm_buttons)

    # 2. VTS_XX_0.IFO (VTSM PGCIT at 0x00D4)
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

        b6 = data[btn_offset + 6]
        b7 = data[btn_offset + 7]
        b8 = data[btn_offset + 8]
        b9 = data[btn_offset + 9]
        b10 = data[btn_offset + 10]
        b11 = data[btn_offset + 11]

        y1 = ((b6 >> 6) << 8) | b7
        y2 = (((b6 >> 2) & 0x03) << 8) | b8
        x1 = ((b9 >> 6) << 8) | b10
        x2 = (((b9 >> 2) & 0x03) << 8) | b11
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
