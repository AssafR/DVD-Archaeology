from __future__ import annotations

"""SPU decoding helpers based on libdvdread/FFmpeg structures.

These functions focus on parsing DVD subpicture (SPU) packets and turning
their RLE-encoded bitmaps into bounding boxes. The goal is to keep the core
SPU logic reusable for a full port later.

References:
- https://ffmpeg.org/doxygen/trunk/dvdsubdec_8c_source.html
- https://en.wikibooks.org/wiki/Inside_DVD-Video/Subpicture_Streams
"""

from dataclasses import dataclass
from typing import Iterable

from dvdmenu_extract.util.libdvdread_compat import read_u16


@dataclass(frozen=True)
class SpuControl:
    x1: int
    y1: int
    x2: int
    y2: int
    offset1: int
    offset2: int
    is_menu: bool


@dataclass(frozen=True)
class SpuBitmap:
    x: int
    y: int
    width: int
    height: int
    pixels: list[list[int]]


def parse_spu_control(packet: bytes) -> SpuControl | None:
    if len(packet) < 4:
        return None
    size = read_u16(packet, 0)
    if size == 0 or size > len(packet):
        size = len(packet)
    control_offset = read_u16(packet, 2)
    if control_offset < 4 or control_offset >= size:
        return None

    x1 = y1 = x2 = y2 = 0
    offset1 = offset2 = -1
    is_menu = False

    pos = control_offset
    while pos + 4 <= size:
        pos += 4  # delay + next offset, not needed for bitmap extraction
        while pos < size:
            cmd = packet[pos]
            pos += 1
            if cmd == 0x00:
                is_menu = True
            elif cmd == 0x03:
                pos += 2  # color mapping
            elif cmd == 0x04:
                pos += 2  # alpha mapping
            elif cmd in (0x05, 0x85):
                if pos + 6 > size:
                    break
                x1 = (packet[pos] << 4) | (packet[pos + 1] >> 4)
                x2 = ((packet[pos + 1] & 0x0F) << 8) | packet[pos + 2]
                y1 = (packet[pos + 3] << 4) | (packet[pos + 4] >> 4)
                y2 = ((packet[pos + 4] & 0x0F) << 8) | packet[pos + 5]
                pos += 6
            elif cmd == 0x06:
                if pos + 4 > size:
                    break
                offset1 = read_u16(packet, pos)
                offset2 = read_u16(packet, pos + 2)
                pos += 4
            elif cmd == 0x86:
                # 8-bit offsets not handled; skip to end of command list.
                pos = size
            elif cmd == 0xFF:
                break
            else:
                break
        if offset1 >= 0 and offset2 >= 0 and x2 >= x1 and y2 >= y1:
            return SpuControl(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                offset1=offset1,
                offset2=offset2,
                is_menu=is_menu,
            )
        if pos <= control_offset:
            break
        if pos >= size:
            break
    return None


def decode_spu_bitmap(packet: bytes, control: SpuControl) -> SpuBitmap | None:
    width = control.x2 - control.x1 + 1
    height = control.y2 - control.y1 + 1
    if width <= 0 or height <= 0:
        return None

    pixels = [[0 for _ in range(width)] for _ in range(height)]
    _decode_field(
        packet=packet,
        start_offset=control.offset1,
        width=width,
        height=(height + 1) // 2,
        row_start=0,
        pixels=pixels,
    )
    _decode_field(
        packet=packet,
        start_offset=control.offset2,
        width=width,
        height=height // 2,
        row_start=1,
        pixels=pixels,
    )
    return SpuBitmap(
        x=control.x1,
        y=control.y1,
        width=width,
        height=height,
        pixels=pixels,
    )


def bitmap_connected_components(bitmap: SpuBitmap) -> list[tuple[int, int, int, int]]:
    width = bitmap.width
    height = bitmap.height
    visited = [[False for _ in range(width)] for _ in range(height)]
    rects: list[tuple[int, int, int, int]] = []

    for y in range(height):
        for x in range(width):
            if visited[y][x] or bitmap.pixels[y][x] == 0:
                continue
            stack = [(x, y)]
            visited[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            while stack:
                cx, cy = stack.pop()
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for nx, ny in (
                    (cx - 1, cy),
                    (cx + 1, cy),
                    (cx, cy - 1),
                    (cx, cy + 1),
                ):
                    if 0 <= nx < width and 0 <= ny < height:
                        if not visited[ny][nx] and bitmap.pixels[ny][nx] != 0:
                            visited[ny][nx] = True
                            stack.append((nx, ny))
            rects.append(
                (
                    bitmap.x + min_x,
                    bitmap.y + min_y,
                    bitmap.x + max_x,
                    bitmap.y + max_y,
                )
            )
    return rects


def find_spu_button_rects(packet: bytes) -> list[tuple[int, int, int, int]]:
    control = parse_spu_control(packet)
    if control is None:
        return []
    bitmap = decode_spu_bitmap(packet, control)
    if bitmap is None:
        return []
    rects = bitmap_connected_components(bitmap)
    return [rect for rect in rects if rect[2] > rect[0] and rect[3] > rect[1]]


def iter_spu_packets(ps_data: bytes) -> Iterable[tuple[int, bytes]]:
    start_code = b"\x00\x00\x01"
    offset = 0
    length = len(ps_data)
    while offset + 6 <= length:
        marker = ps_data.find(start_code, offset)
        if marker < 0 or marker + 6 > length:
            break
        stream_id = ps_data[marker + 3]
        pes_len = (ps_data[marker + 4] << 8) | ps_data[marker + 5]
        payload_start = marker + 6
        if stream_id != 0xBD:
            offset = payload_start
            continue
        if payload_start + 3 > length:
            break
        flags = ps_data[payload_start + 1]
        header_len = ps_data[payload_start + 2]
        payload_start = payload_start + 3 + header_len
        if payload_start >= length:
            break
        substream_id = ps_data[payload_start]
        if not (0x20 <= substream_id <= 0x3F):
            offset = payload_start + 1
            continue
        payload_start += 1
        if pes_len == 0:
            payload_end = length
        else:
            payload_end = marker + 6 + pes_len
        payload_end = min(payload_end, length)
        if payload_end <= payload_start + 4:
            offset = payload_end
            continue
        yield (substream_id, ps_data[payload_start:payload_end])
        offset = payload_end


def _decode_field(
    packet: bytes,
    start_offset: int,
    width: int,
    height: int,
    row_start: int,
    pixels: list[list[int]],
) -> None:
    if start_offset < 0 or start_offset >= len(packet):
        return
    bit_pos = start_offset * 8
    for row in range(height):
        x = 0
        while x < width:
            run_len, color, bit_pos = _decode_run(packet, bit_pos)
            if run_len is None:
                run_len = width - x
            if run_len <= 0:
                run_len = width - x
            run_len = min(run_len, width - x)
            target_row = row_start + (row * 2)
            if 0 <= target_row < len(pixels):
                for ix in range(x, x + run_len):
                    pixels[target_row][ix] = color
            x += run_len
        bit_pos = _align_to_byte(bit_pos)


def _decode_run(packet: bytes, bit_pos: int) -> tuple[int | None, int, int]:
    v = 0
    t = 1
    while v < t and t <= 0x40:
        nibble, bit_pos = _read_bits(packet, bit_pos, 4)
        v = (v << 4) | nibble
        t <<= 2
    color = v & 0x03
    if v < 4:
        return None, color, bit_pos
    return v >> 2, color, bit_pos


def _read_bits(packet: bytes, bit_pos: int, count: int) -> tuple[int, int]:
    value = 0
    for _ in range(count):
        byte_index = bit_pos // 8
        if byte_index >= len(packet):
            value <<= 1
            bit_pos += 1
            continue
        bit_index = 7 - (bit_pos % 8)
        value = (value << 1) | ((packet[byte_index] >> bit_index) & 0x01)
        bit_pos += 1
    return value, bit_pos


def _align_to_byte(bit_pos: int) -> int:
    remainder = bit_pos % 8
    if remainder == 0:
        return bit_pos
    return bit_pos + (8 - remainder)
