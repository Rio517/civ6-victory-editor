"""Two-level alignment.

Level 1 aligns coarse content-defined chunks. Wherever a gap between matched
runs changed length, level 2 re-chunks just that gap much more finely and aligns
again. Without this, every resized gap is invisible - about half the changed
bytes in a Civ VI turn diff.
"""
import bisect, difflib, cdc, seqalign

def _sub(a, b, target=64, window=16):
    ca = cdc.chunks(a, window=window, target=target)
    cb = cdc.chunks(b, window=window, target=target)
    sm = difflib.SequenceMatcher(None, [h for _,_,h in ca], [h for _,_,h in cb], autojunk=False)
    return ca, cb, [bl for bl in sm.get_matching_blocks() if bl.size]

class Align2:
    def __init__(self, A, B, ca, cb, max_gap=400_000):
        self.A, self.B = A, B
        self.top = seqalign.SeqAlign(ca, cb)
        self.sub = {}                       # a0 -> (ca,cb,blocks,a0,b0)
        for a0, a1, b0, b1 in self.top.gaps():
            if (a1-a0) == (b1-b0) or not (0 < a1-a0 <= max_gap) or not (0 < b1-b0 <= max_gap):
                continue
            self.sub[a0] = (*_sub(A[a0:a1], B[b0:b1]), a0, b0)
        self._gapstarts = sorted(self.sub)

    def map(self, pos):
        q = self.top.map(pos)
        if q is not None: return q
        i = bisect.bisect_right(self._gapstarts, pos) - 1
        if i < 0: return None
        a0 = self._gapstarts[i]
        ca, cb, blocks, a0, b0 = self.sub[a0]
        rel = pos - a0
        s = seqalign.SeqAlign.__new__(seqalign.SeqAlign)
        s.ca, s.cb, s.blocks = ca, cb, blocks
        s.starts = [ca[bl.a][0] for bl in blocks]
        r = s.map(rel)
        return None if r is None else b0 + r

    def fine_diffs(self, maxrun=8):
        """Exact differing runs inside resized gaps: (pos_in_A, width)."""
        out = []
        for a0 in self._gapstarts:
            ca, cb, blocks, a0, b0 = self.sub[a0]
            for bl, nb in zip(blocks, blocks[1:]):
                x0 = ca[bl.a+bl.size-1][1]; x1 = ca[nb.a][0]
                y0 = cb[bl.b+bl.size-1][1]; y1 = cb[nb.b][0]
                if (x1-x0) != (y1-y0) or x1 <= x0: continue
                X = self.A[a0+x0:a0+x1]; Y = self.B[b0+y0:b0+y1]
                k = 0
                while k < len(X):
                    if X[k] != Y[k]:
                        s2 = k
                        while k < len(X) and X[k] != Y[k]: k += 1
                        if k-s2 <= maxrun: out.append((a0+x0+s2, k-s2))
                    else: k += 1
        return out
