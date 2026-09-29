"""
Input-stream extraction.

Input blocks are located by signature - a u32 count followed by records with
strictly increasing timestamps - rather than by byte offset. That is why this
works unchanged across every patch version from 6.06 to 10.09.
"""
import numpy as np
from whisdom.core.bitstream import BitStream
from .constants import INPUT_BITS

_W32 = (1 << np.arange(31, -1, -1)).astype(np.uint64)

def u32_at_all(buf):
    """Value of the u32 starting at every bit offset (vectorised)."""
    bits = np.unpackbits(np.frombuffer(bytes(buf), dtype=np.uint8)).astype(np.uint64)
    if len(bits) < 32:
        return np.zeros(0, dtype=np.uint64)
    return np.lib.stride_tricks.sliding_window_view(bits, 32) @ _W32

def find_blocks(buf, min_count=8, max_count=20000):
    vals = u32_at_all(buf)
    if vals.size == 0: return []
    cand = np.nonzero((vals >= min_count) & (vals <= max_count))[0]
    blocks = []; skip_to = 0
    for off in cand:
        off = int(off)
        if off < skip_to: continue
        cnt = int(vals[off])
        s = BitStream(buf, off + 32); prev = -1; ok = True
        try:
            for _ in range(min(cnt, 12)):
                ts = s.u32()
                if ts <= prev: ok = False; break
                prev = ts
                if s.bit(): s.bits(14)
        except Exception:
            ok = False
        if not ok: continue
        s = BitStream(buf, off + 32); prev = -1
        try:
            for _ in range(cnt):
                ts = s.u32()
                if ts <= prev: raise ValueError
                prev = ts
                if s.bit(): s.bits(14)
        except Exception:
            continue
        # `last_ts` is free here (we just walked the whole block) and saves
        # callers a second full read just to learn the block's span.
        blocks.append({"bit": off, "count": cnt, "end": s.ro, "last_ts": prev})
        skip_to = s.ro
    return blocks

def read_block(buf, bit):
    s = BitStream(buf, bit); cnt = s.u32(); out = []
    for _ in range(cnt):
        ts = s.u32()
        st = s.bits(14) if s.bit() else 0
        out.append((ts, st))
    return out

def entity_of(buf, block_bit):
    """The 5-bit entity id immediately preceding a block's count field."""
    return BitStream(buf, block_bit - 5).bits(5) if block_bit >= 5 else None

def presses(events):
    """Held-state stream -> discrete presses (0->1 transitions per bit)."""
    out = []; prev = 0
    for ts, st in events:
        for b, name in INPUT_BITS.items():
            if (st >> b & 1) and not (prev >> b & 1):
                out.append((ts, name))
        prev = st
    return out
