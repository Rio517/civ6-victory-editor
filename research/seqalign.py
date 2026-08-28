"""Byte-accurate alignment of two payloads via a sequence diff of their
content-defined chunk hashes. Matched chunks are byte-identical, so a position
inside one maps exactly; positions in the gaps map only when the gap has the
same byte length on both sides.
"""
import bisect, difflib

class SeqAlign:
    def __init__(self, ca, cb):
        self.ca, self.cb = ca, cb
        sm = difflib.SequenceMatcher(None, [h for _,_,h in ca], [h for _,_,h in cb], autojunk=False)
        self.blocks = [bl for bl in sm.get_matching_blocks() if bl.size]
        self.starts = [ca[bl.a][0] for bl in self.blocks]

    def map(self, pos):
        i = bisect.bisect_right(self.starts, pos) - 1
        if i < 0: return None
        bl = self.blocks[i]
        a_end = self.ca[bl.a + bl.size - 1][1]
        if pos < a_end:                                  # inside a matched run
            k = bisect.bisect_right([self.ca[bl.a+x][0] for x in range(bl.size)], pos) - 1
            return self.cb[bl.b + k][0] + (pos - self.ca[bl.a + k][0])
        if i + 1 >= len(self.blocks): return None
        nb = self.blocks[i+1]
        gap_a = self.ca[nb.a][0] - a_end
        gap_b = self.cb[nb.b][0] - self.cb[bl.b + bl.size - 1][1]
        if gap_a != gap_b: return None                   # gap resized: unmappable
        return self.cb[bl.b + bl.size - 1][1] + (pos - a_end)

    def gaps(self):
        """Yield (a0,a1,b0,b1) byte spans that differ between the two files."""
        for bl, nb in zip(self.blocks, self.blocks[1:]):
            a0 = self.ca[bl.a + bl.size - 1][1]; a1 = self.ca[nb.a][0]
            b0 = self.cb[bl.b + bl.size - 1][1]; b1 = self.cb[nb.b][0]
            if a1 > a0 or b1 > b0: yield (a0, a1, b0, b1)
