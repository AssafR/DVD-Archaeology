"""Debug script to inspect SPU packets from a DVD menu VOB."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dvdmenu_extract.util.libdvdread_spu import (
    iter_spu_packets,
    parse_spu_control,
    decode_spu_bitmap,
    bitmap_connected_components,
)
from dvdmenu_extract.util.libdvdread_compat import read_u16


def reassemble_spu_packets(vob_data):
    """Reassemble fragmented SPU packets based on size headers."""
    buffers = {}
    expected_sizes = {}
    
    print(f"\n=== Starting SPU reassembly ===")
    
    for substream_id, payload in iter_spu_packets(vob_data):
        if substream_id not in buffers:
            buffers[substream_id] = bytearray()
            print(f"  New substream {substream_id:#x}")
        
        print(f"  Substream {substream_id:#x}: received {len(payload)} bytes")
        buffers[substream_id].extend(payload)
        
        # Update expected size if we don't have one yet or if it's 0
        buffer = buffers[substream_id]
        if (substream_id not in expected_sizes or expected_sizes[substream_id] == 0) and len(buffer) >= 2:
            size = read_u16(buffer, 0)
            expected_sizes[substream_id] = size if size > 0 else 0
            print(f"    Expected size from header: {expected_sizes[substream_id]}")
        
        expected = expected_sizes.get(substream_id, 0)
        
        print(f"    Buffer size: {len(buffer)}, Expected: {expected}")
        
        while expected > 0 and len(buffer) >= expected:
            packet = bytes(buffer[:expected])
            buffers[substream_id] = bytearray(buffer[expected:])
            print(f"    -> Yielding complete packet ({expected} bytes)")
            
            yield (substream_id, packet)
            
            # Update expected size for next packet
            buffer = buffers[substream_id]
            if len(buffer) >= 2:
                expected_sizes[substream_id] = read_u16(buffer, 0)
                print(f"    -> Next packet expected size: {expected_sizes[substream_id]}")
            else:
                expected_sizes[substream_id] = 0
                print(f"    -> No more complete packets in buffer")
            
            # Check if there's another packet in the buffer
            expected = expected_sizes.get(substream_id, 0)
    
    # Check for any remaining data in buffers
    print(f"\n=== End of SPU stream ===")
    for substream_id, buffer in buffers.items():
        if len(buffer) > 0:
            print(f"  Substream {substream_id:#x}: {len(buffer)} bytes remaining in buffer")
            print(f"    First 16 bytes: {bytes(buffer[:16]).hex()}")


def main():
    vob_path = Path(r"C:\Users\Assaf\program\DVD-Archaeology\DVD_Sample_01\VIDEO_TS\VIDEO_TS.VOB")
    
    print(f"Reading {vob_path}")
    with vob_path.open("rb") as f:
        vob_data = f.read()
    print(f"  Read {len(vob_data)} bytes")
    
    packet_count = 0
    total_buttons = 0
    for substream_id, packet in reassemble_spu_packets(vob_data):
        packet_count += 1
        print(f"\nSPU Packet #{packet_count}")
        print(f"  Substream ID: {substream_id:#x}")
        print(f"  Packet size: {len(packet)} bytes")
        
        # Try to parse control structure
        control = parse_spu_control(packet)
        if control:
            print(f"  Control parsed successfully:")
            print(f"    Rectangle: ({control.x1},{control.y1})->({control.x2},{control.y2})")
            print(f"    Size: {control.x2-control.x1+1}x{control.y2-control.y1+1}")
            print(f"    Offsets: {control.offset1}, {control.offset2}")
            print(f"    Is menu: {control.is_menu}")
            
            # Try to decode bitmap
            bitmap = decode_spu_bitmap(packet, control)
            if bitmap:
                print(f"  Bitmap decoded successfully:")
                print(f"    Position: ({bitmap.x},{bitmap.y})")
                print(f"    Size: {bitmap.width}x{bitmap.height}")
                
                # Count non-zero pixels
                non_zero = sum(1 for row in bitmap.pixels for px in row if px != 0)
                print(f"    Non-zero pixels: {non_zero}/{bitmap.width*bitmap.height}")
                
                # Find connected components
                rects = bitmap_connected_components(bitmap)
                print(f"  Connected components: {len(rects)}")
                for idx, rect in enumerate(rects):
                    w, h = rect[2] - rect[0] + 1, rect[3] - rect[1] + 1
                    print(f"    Component {idx+1}: ({rect[0]},{rect[1]})->({rect[2]},{rect[3]}) size: {w}x{h}")
                    
                    # Count as button if large enough
                    if w >= 80 and h >= 60:
                        total_buttons += 1
                        print(f"      -> Button #{total_buttons}")
            else:
                print(f"  Failed to decode bitmap")
        else:
            print(f"  Failed to parse control structure")
            # Dump first 32 bytes for inspection
            print(f"  First 32 bytes: {packet[:32].hex()}")
    
    print(f"\nTotal packets: {packet_count}")
    print(f"Total buttons found: {total_buttons}")


if __name__ == "__main__":
    main()
