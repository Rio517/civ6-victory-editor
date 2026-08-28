"""Content-defined chunking, so chunk boundaries follow content rather than
absolute offset. An edit only disturbs the chunks it touches; everything else
keeps identical boundaries and identical hashes across files.
"""
import numpy as np, hashlib

_rng = np.random.default_rng(12345)
GEAR = _rng.integers(0, 2**32, size=256, dtype=np.uint64)

def boundaries(buf, window=48, target=512):
    b = np.frombuffer(buf, dtype=np.uint8)
    g = GEAR[b]
    c = np.cumsum(g, dtype=np.uint64)
    roll = c[window:] - c[:-window]            # rolling sum over `window` bytes
    hit = np.flatnonzero((roll % target) == 0) + window
    return hit

def chunks(buf, window=48, target=512):
    """-> list of (start, end, sha1_8bytes)"""
    cuts = boundaries(buf, window, target)
    out, prev = [], 0
    for c in cuts.tolist():
        if c - prev < 64: continue
        out.append((prev, c, hashlib.blake2b(buf[prev:c], digest_size=8).digest()))
        prev = c
    if prev < len(buf):
        out.append((prev, len(buf), hashlib.blake2b(buf[prev:], digest_size=8).digest()))
    return out
