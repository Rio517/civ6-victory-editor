"""Civ VI save container: header | chunked deflate stream | trailer.

The compressed section is NOT one flat zlib stream. It is stored as 64 KiB
chunks of *compressed* bytes, with a u32 little-endian length of the following
chunk written between them:

    [64KiB][u32 len][64KiB][u32 len]...[final partial chunk]

Inflating without stripping those separators appears to succeed but yields
subtly wrong data, because `00 00 01 00` decodes as a deflate stored-block
header with LEN=0/NLEN=1. Writing a save without re-inserting them makes the
game hang on load.
"""
import zlib, re, struct

CHUNK = 64 * 1024

def _find_start(data):
    mod = data.rfind(b'MOD_TITLE')
    i = data.find(b'\x78\x9c', mod if mod != -1 else 0)
    if i == -1:
        raise RuntimeError('no zlib header found')
    return i

def split(path):
    """-> (header, payload, trailer, comp_start, comp_end)."""
    data = open(path, 'rb').read()
    start = _find_start(data)
    end = data.rfind(b'\x00\x00\xff\xff') + 4
    comp = data[start:end - 4]
    parts, pos = [], 0
    while pos < len(comp):
        parts.append(comp[pos:pos + CHUNK])
        pos += CHUNK + 4
    d = zlib.decompressobj()
    payload = d.decompress(b''.join(parts)) + d.flush()
    return data[:start], payload, data[end:], start, end

def separators(path):
    """The u32 chunk lengths as stored, for verification."""
    data = open(path, 'rb').read()
    start = _find_start(data); end = data.rfind(b'\x00\x00\xff\xff')
    comp = data[start:end]
    out, pos = [], CHUNK
    while pos < len(comp):
        out.append(struct.unpack_from('<I', comp, pos)[0]); pos += 4 + CHUNK
    return out

def rebuild(header, payload, trailer, level=6):
    """Deflate and re-interleave the chunk-length separators.

    The whole deflate stream is chunked, terminator included: in a real save the
    closing 00 00 ff ff sits inside the final chunk and is counted by that
    chunk's length. Writing it outside the chunk structure gets the save as far
    as "Save version is incompatible".
    """
    co = zlib.compressobj(level, zlib.DEFLATED, zlib.MAX_WBITS)
    body = co.compress(payload) + co.flush(zlib.Z_SYNC_FLUSH)
    assert body.endswith(b'\x00\x00\xff\xff')
    out = []
    for i in range(0, len(body), CHUNK):
        piece = body[i:i + CHUNK]
        if i:
            out.append(struct.pack('<I', len(piece)))
        out.append(piece)
    return header + b''.join(out) + trailer
