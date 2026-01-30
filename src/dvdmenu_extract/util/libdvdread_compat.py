from __future__ import annotations

"""Compatibility helpers based on libdvdread structures.

Ported from libdvdread's IFO layout and NAV pack parsing so future
full ports can reuse the same field offsets and decoding logic.
Reference:
https://raw.githubusercontent.com/mirror/libdvdread/master/src/dvdread/ifo_types.h
"""

from dataclasses import dataclass


DVD_BLOCK_LEN = 2048


def read_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], byteorder="big", signed=False)


def read_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], byteorder="big", signed=False)


def parse_c_adt(data: bytes, sector_offset: int) -> dict[tuple[int, int], tuple[int, int]]:
    if len(data) < sector_offset + 4:
        return {}
    table_sector = read_u32(data, sector_offset)
    if table_sector == 0:
        return {}
    table_offset = table_sector * DVD_BLOCK_LEN
    if table_offset + 8 > len(data):
        return {}
    end_addr = read_u32(data, table_offset + 4)
    table_end = min(table_offset + end_addr + 1, len(data))
    entries_offset = table_offset + 8
    mapping: dict[tuple[int, int], tuple[int, int]] = {}
    offset = entries_offset
    while offset + 12 <= table_end:
        vob_idn = read_u16(data, offset)
        cell_idn = data[offset + 2]
        start_sector = read_u32(data, offset + 4)
        last_sector = read_u32(data, offset + 8)
        mapping[(vob_idn, cell_idn)] = (start_sector, last_sector)
        offset += 12
    return mapping


def parse_vobu_admap(data: bytes, sector_offset: int) -> list[int]:
    if len(data) < sector_offset + 4:
        return []
    table_sector = read_u32(data, sector_offset)
    if table_sector == 0:
        return []
    table_offset = table_sector * DVD_BLOCK_LEN
    if table_offset + 4 > len(data):
        return []
    last_byte = read_u32(data, table_offset)
    table_end = min(table_offset + last_byte + 1, len(data))
    entries_offset = table_offset + 4
    entries: list[int] = []
    offset = entries_offset
    while offset + 4 <= table_end:
        entries.append(read_u32(data, offset))
        offset += 4
    return entries


@dataclass(frozen=True)
class NavPackButtons:
    hli_ss: int
    btn_md: int
    btn_sn: int
    btn_ns: int
    rects: list[tuple[int, int, int, int] | None]
    links: list[dict[str, int]]
    active_indices: list[int]


def parse_nav_pack_buttons(nav_pack: bytes) -> NavPackButtons | None:
    marker = nav_pack.find(b"\x00\x00\x01\xbf")
    if marker < 0 or marker + 7 >= len(nav_pack):
        return None
    pci_start = marker + 4 + 2 + 1
    if pci_start + 0x0bb + (36 * 18) > len(nav_pack):
        return None
    hli_ss = read_u16(nav_pack, pci_start + 0x60)
    btn_md = read_u16(nav_pack, pci_start + 0x6E)
    btn_sn = nav_pack[pci_start + 0x70]
    btn_ns = nav_pack[pci_start + 0x71]
    if btn_ns == 0:
        return None
    btn_it_start = pci_start + 0x0bb
    rects: list[tuple[int, int, int, int] | None] = []
    links: list[dict[str, int]] = []
    start_index = btn_sn if btn_sn > 0 else 1
    active_indices = list(
        range(start_index, min(start_index + btn_ns, 37))
    )
    for i in range(36):
        entry = nav_pack[btn_it_start + (i * 18) : btn_it_start + ((i + 1) * 18)]
        if len(entry) < 6:
            continue
        rect = decode_btn_it_rect(entry)
        up = entry[6] & 0x3F
        down = entry[7] & 0x3F
        left = entry[8] & 0x3F
        right = entry[9] & 0x3F
        rects.append(rect)
        links.append(
            {
                "index": i + 1,
                "up": up,
                "down": down,
                "left": left,
                "right": right,
            }
        )
    return NavPackButtons(
        hli_ss=hli_ss,
        btn_md=btn_md,
        btn_sn=btn_sn,
        btn_ns=btn_ns,
        rects=rects,
        links=links,
        active_indices=active_indices,
    )


def decode_btn_it_rect(entry: bytes) -> tuple[int, int, int, int] | None:
    b0, b1, b2, b3, b4, b5 = entry[0], entry[1], entry[2], entry[3], entry[4], entry[5]
    x1 = ((b0 & 0x3F) << 4) | (b1 >> 4)
    x2 = ((b1 & 0x03) << 8) | b2
    y1 = ((b3 & 0x3F) << 4) | (b4 >> 4)
    y2 = ((b4 & 0x03) << 8) | b5
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)
