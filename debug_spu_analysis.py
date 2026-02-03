"""
Debug script to analyze SPU data from Friends and Ellen DVDs.
This will help us understand why SPU extraction fails for Friends but works for Ellen.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dvdmenu_extract.util.libdvdread_spu import (
    iter_spu_packets, 
    decode_spu_bitmap, 
    bitmap_connected_components,
    parse_spu_control,
)
from dvdmenu_extract.util.libdvdread_compat import read_u16

def analyze_vob_spu(vob_path: Path, name: str):
    """Analyze SPU data in a VOB file."""
    print(f"\n{'='*80}")
    print(f"Analyzing: {name}")
    print(f"File: {vob_path}")
    print(f"Size: {vob_path.stat().st_size:,} bytes")
    print(f"{'='*80}\n")
    
    # Read VOB data
    with vob_path.open("rb") as f:
        vob_data = f.read()
    
    print(f"Read {len(vob_data):,} bytes from VOB\n")
    
    # Reassemble SPU packets
    def reassemble_spu_packets(vob_data: bytes):
        """Reassemble fragmented SPU packets."""
        buffers = {}
        expected_sizes = {}
        
        for substream_id, payload in iter_spu_packets(vob_data):
            if substream_id not in buffers:
                buffers[substream_id] = bytearray()
            
            buffers[substream_id].extend(payload)
            buffer = buffers[substream_id]
            
            if (substream_id not in expected_sizes or expected_sizes[substream_id] == 0) and len(buffer) >= 2:
                size = read_u16(buffer, 0)
                expected_sizes[substream_id] = size if size > 0 else 0
            
            expected = expected_sizes.get(substream_id, 0)
            
            while expected > 0 and len(buffer) >= expected:
                packet = bytes(buffer[:expected])
                buffers[substream_id] = bytearray(buffer[expected:])
                buffer = buffers[substream_id]
                
                yield (substream_id, packet)
                
                if len(buffer) >= 2:
                    expected_sizes[substream_id] = read_u16(buffer, 0)
                else:
                    expected_sizes[substream_id] = 0
                
                expected = expected_sizes.get(substream_id, 0)
    
    # Analyze packets
    packet_count = 0
    total_buttons = 0
    
    for substream_id, packet in reassemble_spu_packets(vob_data):
        packet_count += 1
        page_index = packet_count - 1
        
        print(f"Packet {packet_count} (Page {page_index}):")
        print(f"  Substream ID: 0x{substream_id:02x}")
        print(f"  Packet size: {len(packet):,} bytes")
        
        if len(packet) < 4:
            print(f"  ERROR: Packet too small ({len(packet)} bytes)\n")
            continue
        
        # Parse packet header
        size = read_u16(packet, 0)
        ctrl_offset = read_u16(packet, 2)
        
        print(f"  Size field: {size}")
        print(f"  Control offset: {ctrl_offset}")
        
        # Parse control data first
        try:
            control = parse_spu_control(packet)
            if not control:
                print(f"  ERROR: Failed to parse SPU control data\n")
                continue
            
            w = control.x2 - control.x1
            h = control.y2 - control.y1
            print(f"  Display area: ({control.x1}, {control.y1}) to ({control.x2}, {control.y2}) = {w}x{h}")
            print(f"  Field offsets: offset1={control.offset1}, offset2={control.offset2}")
            print(f"  Is menu: {control.is_menu}")
            
            # Decode bitmap
            bitmap_result = decode_spu_bitmap(packet, control)
            if not bitmap_result:
                print(f"  ERROR: Failed to decode SPU bitmap\n")
                continue
            
            width, height = bitmap_result.width, bitmap_result.height
            print(f"  Bitmap decoded: {width}x{height}")
            
            # Count non-zero pixels (bitmap_result.pixels is list[list[int]])
            non_zero = sum(1 for row in bitmap_result.pixels for p in row if p != 0)
            total_pixels = width * height
            print(f"  Non-zero pixels: {non_zero:,} ({non_zero/total_pixels*100:.1f}%)")
            
            # Find connected components (button regions)
            button_rects = bitmap_connected_components(bitmap_result)
            print(f"  Connected components found: {len(button_rects)}")
            
            # button_rects is already filtered and returns (x1, y1, x2, y2) tuples
            print(f"  Buttons found: {len(button_rects)}")
            for i, (x1, y1, x2, y2) in enumerate(button_rects, 1):
                w = x2 - x1
                h = y2 - y1
                print(f"    Button {i}: ({x1},{y1})-({x2},{y2}) {w}x{h}")
            
            total_buttons += len(button_rects)
            
        except Exception as e:
            print(f"  ERROR decoding bitmap: {e}")
        
        print()
    
    print(f"Summary:")
    print(f"  Total packets: {packet_count}")
    print(f"  Total buttons: {total_buttons}")
    print()

if __name__ == "__main__":
    # Analyze Friends DVD
    friends_vob = Path(r"Q:\DVDs\Friends_S09-10\VIDEO_TS\VIDEO_TS.VOB")
    if friends_vob.exists():
        analyze_vob_spu(friends_vob, "Friends S09-10")
    else:
        print(f"Friends VOB not found: {friends_vob}")
    
    # Analyze Ellen DVD
    ellen_vob = Path(r"C:\Users\Assaf\Desktop\Temporary\Ellen_Season_04\VIDEO_TS\VIDEO_TS.VOB")
    if ellen_vob.exists():
        analyze_vob_spu(ellen_vob, "Ellen Season 04")
    else:
        print(f"Ellen VOB not found: {ellen_vob}")
