"""Locate a byte field across saves by matching its surrounding context.

Alignment-free: instead of aligning whole payloads, take K bytes either side of a
candidate field and look for that exact context elsewhere. Returns the value the
field holds in each save, or None if the context is absent/ambiguous.
"""
def lookup(buf, pre, suf, width, tries=8):
    q = buf.find(pre)
    n = 0
    while q != -1 and n < tries:
        mid_at = q + len(pre)
        if buf[mid_at + width: mid_at + width + len(suf)] == suf:
            return buf[mid_at: mid_at + width]
        q = buf.find(pre, q + 1); n += 1
    return None

def probe(src, pos, width, others, K=24):
    """others: {tag: buffer}. -> (value_in_src, {tag: value_or_None})"""
    pre, suf = src[pos-K:pos], src[pos+width:pos+width+K]
    if len(pre) < K or len(suf) < K: return None, {}
    return src[pos:pos+width], {t: lookup(o, pre, suf, width) for t, o in others.items()}
