from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable

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
