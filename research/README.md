# Research tooling

Scratch tools from the attempt to remove an achieved victory from a save. Not
needed to use `civ6victory.py`; kept so the next attempt does not start over.
See the investigation log in the top-level README for what these were used for
and what they ruled out.

- `cdc.py` — content-defined chunking. Chunk boundaries follow content, so an
  edit only disturbs the chunks it touches and everything else keeps identical
  boundaries and hashes across two saves.
- `seqalign.py` — aligns two payloads by running a sequence diff over their
  chunk hashes. Matched chunks are byte-identical, so positions inside them map
  exactly between saves.
- `align2.py` — adds a second level: wherever a gap between matched runs changed
  length, it re-chunks that gap finely and aligns again. Without this, roughly
  half the changed bytes in a turn-to-turn diff are never examined.
- `bindiff.py` — greedy byte differ with verified resync. Superseded by the
  chunk-based aligners, which drift less.
- `ctxmatch.py` — alignment-free lookup: find a field in another save by
  matching the bytes surrounding it. Useful when alignment is unavailable, but
  it fails in repetitive regions where the context matches in thousands of
  places.

Normalise each save's own turn number before comparing anything. It appears
around 1750 times per payload and otherwise dominates every diff.
