"""Civ VI .Civ6Save header parser.

Layout (little-endian):
  file: 'CIV6' u32 version u32 saveversion, then a stream of records.
  record: u32 key ( = ~crc32(name) ), u32 type, then type-specific payload.
    type 0x00                    : 0 bytes
    type 0x01/02/03/04/15/16/17  : 8 bytes pad + i32 value   (bool / int / hashed-enum)
    type 0x05                    : u24 len + u8 tag + u32 unk + len bytes  (utf-8, NUL-terminated)
    type 0x06                    : same, len*2 bytes (utf-16le)
    type 0x18                    : same as 0x05, payload is a zlib blob
    type 0x0a                    : u24 0 + u8 tag(0x05) + u32 unk + u32 count, then <count> child records
    type 0x0b                    : u24 0 + u8 tag(0x11) + u32 unk + u32 count, then <count> anonymous 0x0a groups
    type 0x14/0x15               : 16 bytes
"""
import struct, binascii

def civhash(s):
    if isinstance(s, str): s = s.encode()
    return (~binascii.crc32(s)) & 0xFFFFFFFF

FIXED12 = {0x01, 0x02, 0x03, 0x04}
FIXED16 = {0x14, 0x15}
STRLIKE = {0x05, 0x06, 0x18, 0x10}

class Rec:
    __slots__ = ('key','type','off','end','val','val_off','raw','raw_off','tag','unk',
                 'count','count_off','children')
    def __init__(self, **kw):
        for k in self.__slots__: setattr(self, k, kw.get(k))

def parse_records(buf, pos, count=None, limit=None):
    out = []
    n = 0
    while True:
        if count is not None and n >= count: break
        if limit is not None and pos >= limit: break
        if count is None and pos + 8 > len(buf): break
        key, typ = struct.unpack_from('<II', buf, pos)
        r = Rec(key=key, type=typ, off=pos)
        q = pos + 8
        if typ == 0x00:
            pass
        elif typ in FIXED12:
            r.val_off = q + 8
            r.val = struct.unpack_from('<i', buf, q + 8)[0]
            q += 12
        elif typ in FIXED16:
            q += 16
        elif typ in STRLIKE:
            w = struct.unpack_from('<I', buf, q)[0]
            ln, r.tag = w & 0xFFFFFF, w >> 24
            r.unk = struct.unpack_from('<I', buf, q + 4)[0]
            q += 8
            nb = ln * 2 if typ == 0x06 else ln
            r.raw_off, r.raw = q, buf[q:q + nb]
            q += nb
            if r.tag in (0x00, 0x20): q += 4   # null/empty string carries 4 trailing bytes
        elif typ in (0x0a, 0x0b):
            r.tag = struct.unpack_from('<I', buf, q)[0] >> 24
            r.unk = struct.unpack_from('<I', buf, q + 4)[0]
            r.count_off = q + 8
            r.count = struct.unpack_from('<I', buf, q + 8)[0]
            q += 12
            if typ == 0x0a:
                r.children, q = parse_records(buf, q, count=r.count)
            else:
                r.children = []
                for _ in range(r.count):
                    g = Rec(key=None, type=0x0a, off=q)
                    g.count = struct.unpack_from('<I', buf, q + 12)[0]
                    g.count_off = q + 12
                    g.children, q = parse_records(buf, q + 16, count=g.count)
                    g.end = q
                    r.children.append(g)
        else:
            raise ValueError(f'unknown type 0x{typ:x} at {pos}')
        r.end = q
        out.append(r)
        pos = q
        n += 1
    return out, pos

def parse_header(buf):
    assert buf[:4] == b'CIV6'
    recs, end = parse_records(buf, 12, limit=len(buf))
    return recs, end

def walk(recs, depth=0):
    for r in recs:
        yield depth, r
        if r.children:
            for d, c in walk(r.children, depth + 1):
                yield d, c
