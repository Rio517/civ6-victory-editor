"""Anchored binary diff with verified resync.

A candidate realignment is only accepted if a long run matches after the anchor,
which stops a coincidental 24-byte hit from throwing the alignment off for the
rest of the file.
"""
SKIPS = [0,2,4,6,8,12,16,24,32,48,64,96,128,192,256,384,512,1024,2048,4096,16384,65536]

def _match_len(a, i, b, j, cap):
    lo, step = 0, 1 << 16
    while lo < cap:
        n = min(step, cap - lo)
        if a[i+lo:i+lo+n] == b[j+lo:j+lo+n]:
            lo += n
        else:
            hi = lo + n
            while lo < hi:
                mid = (lo + hi) // 2
                if a[i+lo:i+mid+1] == b[j+lo:j+mid+1]: lo = mid + 1
                else: hi = mid
            return lo
    return cap

def _similar(a, i, b, j, n, need=0.60):
    n = min(n, len(a)-i, len(b)-j)
    if n <= 0: return False
    x, y = a[i:i+n], b[j:j+n]
    same = sum(1 for p, q in zip(x, y) if p == q)
    return same >= need * n

def diff(a, b, anchor=32, verify=512, window=1 << 18):
    la, lb = len(a), len(b)
    i = j = 0
    while i < la and j < lb:
        m = _match_len(a, i, b, j, min(la-i, lb-j))
        i += m; j += m
        if i >= la or j >= lb: break
        best = None
        for k in SKIPS:                       # skip forward in b, look in a
            if j+k+anchor > lb: break
            ai = a.find(b[j+k:j+k+anchor], i, min(i+window, la))
            if ai != -1 and _similar(a, ai, b, j+k, verify):
                best = (ai, j+k, (ai-i)+k); break
        for k in SKIPS:                       # skip forward in a, look in b
            if i+k+anchor > la: break
            bj = b.find(a[i+k:i+k+anchor], j, min(j+window, lb))
            if bj != -1 and _similar(a, i+k, b, bj, verify):
                cost = (bj-j)+k
                if best is None or cost < best[2]: best = (i+k, bj, cost)
                break
        if best is None:
            yield (i, la, j, lb); return
        ai, bj, _ = best
        yield (i, ai, j, bj)
        i, j = ai, bj
