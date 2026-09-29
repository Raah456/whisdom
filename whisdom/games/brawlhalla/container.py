"""Brawlhalla replay container: zlib inflate -> XOR unmask -> bitstream."""
import zlib
from .constants import XOR_KEY

def load(path):
    """Return the decrypted, decompressed byte buffer for a .replay file."""
    raw = open(path, "rb").read() if isinstance(path, str) else bytes(path)
    dec = bytearray(zlib.decompress(raw))
    k = XOR_KEY; n = len(k)
    for i in range(len(dec)):
        dec[i] ^= k[i % n]
    return dec
