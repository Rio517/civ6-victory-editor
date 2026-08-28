# civ6-victory-editor

Inspect and edit **victory conditions** and **recorded victories** in Sid Meier's
Civilization VI save files — without touching the compressed game state.

Won a Science victory, hit "One More Turn", and now want to keep playing without
immediately tripping another victory? That's what this is for.

```bash
python3 civ6victory.py inspect "TRAJAN 646 1997 AD.Civ6Save"

python3 civ6victory.py edit "TRAJAN 646 1997 AD.Civ6Save" \
    -o "TRAJAN 646 continued.Civ6Save" \
    --disable science,culture,religion --clear-victory
```

No dependencies, Python 3.8+. Drop the output in your `Saves/Single` folder and load it.

---

## The save format

```
+--------------------------+  offset 0
|  'CIV6' + version words  |
|  plaintext record tree   |   <-- all game configuration lives here
+--------------------------+  ~150 KB in a late-game save
|  CHUNKED deflate stream  |   <-- the entire game state, tens of MB inflated
|  ends 00 00 FF FF        |       (Z_SYNC_FLUSH, no adler32 checksum)
+--------------------------+
|  30025-byte trailer      |
+--------------------------+
```

Three properties make editing safe:

- **No checksums.** Nothing validates the header against the payload.
- **No stored offsets or lengths.** Searching a save for its own header length,
  file size, or compressed length yields zero hits, so the header can grow or
  shrink freely.
- **Configuration is header-only.** The compressed payload contains no copy of
  the config keys, so this tool never re-encodes it — the payload and trailer are
  copied through byte-for-byte.

### Records

The header is a tree of records:

```
u32 key       ( = ~crc32(name) )
u32 type
... type-specific payload
```

| Type | Payload |
|-----:|---------|
| `0x00` | none |
| `0x01` `0x02` `0x03` `0x04` | 8 pad bytes + `i32` (bool / int / hashed enum) |
| `0x05` | `u24` len + `u8` tag + `u32` + len bytes, UTF-8, NUL-terminated |
| `0x06` | as above, len×2 bytes, UTF-16LE |
| `0x18` | as above, payload is a nested zlib blob |
| `0x0a` | `u32` count, then that many child records |
| `0x0b` | `u32` count, then that many anonymous `0x0a` groups |
| `0x14` `0x15` | 16 bytes |

Tag `0x21` marks a normal string. Tags `0x00` and `0x20` mark a null string,
which carries 4 trailing bytes and no data.

### Keys are inverted CRC-32

This is the part that makes the header readable, and it does not appear to be
documented elsewhere:

```python
def civhash(name):
    return (~zlib.crc32(name.encode())) & 0xFFFFFFFF
```

That is the raw CRC-32 register value *before* the final complement. Hash the
identifiers the game ships in its own XML and binaries and the header decodes
itself:

```
0x150c2d79  VICTORY_TECHNOLOGY      0x871d5b63  GAME_ROOT
0x1843ff8c  VICTORY_CONQUEST        0xcfcadc3e  GAME_NAME
0x18c44790  VICTORY_RELIGIOUS       0x626c4c82  GAME_STATE
0xeabc48eb  VICTORY_CULTURE         0xc5fbfa24  GAME_HANDICAP
0x5529a9bb  VICTORY_SCORE           0x1b8cd1c8  ENABLED_MODS
```

Type `0x03` values are the *same hash applied to an enum name*, so they decode
with the same table: `GAME_HANDICAP -> DIFFICULTY_PRINCE`,
`GAME_STATE -> GAMESTATE_LAUNCHED`, `TURN_TIMER_TYPE -> TURNTIMER_NONE`.

To build a lookup table, harvest identifiers from an installed copy of the game
(`Assets/**/Configuration/**.xml` and the `GameCore_*.dll` string tables) and
hash each one.

### Victory configuration

A save contains two `GAME_ROOT` arrays: `[0]` the live configuration and `[1]`
the original game setup. Both hold one boolean per victory type, named exactly
as the `VictoryType` rows in `Configuration/Data/Victories.xml`:

`VICTORY_TECHNOLOGY` `VICTORY_CULTURE` `VICTORY_CONQUEST` `VICTORY_RELIGIOUS`
`VICTORY_SCORE`, plus `VICTORY_DIPLOMATIC` under the Gathering Storm ruleset.

These booleans back `Game.IsVictoryEnabled()`. Setting one to `0` removes that
victory type from the game — **confirmed in play**: after disabling
`VICTORY_TECHNOLOGY`, the Science row disappears from the Overall panel of the
World Rankings screen, which is gated on exactly that call.

`--disable` writes to both arrays so the live config and the setup config agree.

### What an achieved victory leaves behind

When a victory triggers, four records appear in the live config only:

| Key | Example |
|---|---|
| `VICTORY_TYPE` | `5` (row index in `Victories.xml`) |
| `VICTORY_TEAM` | `0` |
| `VICTORY_NAME` | `{"LOC_VICTORY_SCIENCE_NAME": ...}` localized JSON |
| `VICTORY_PLAYER_NAME` | `LOC_LEADER_TRAJAN_NAME` |

`--clear-victory` deletes all four and decrements the enclosing array's count.
The result is structurally indistinguishable from a save taken before the
victory happened.

## Why not just diff two turns?

A natural idea for finding state inside the compressed payload is to diff a save
against the one from the turn before. Measured on two consecutive late-game
autosaves (turn 613 -> 614, inflated payloads of ~34.9 MB):

| Probe | Result |
|---|---|
| Common prefix / suffix | 133 B / 20 B |
| 4 KB blocks of turn 614 found *anywhere* in turn 613 | 19% |
| 1 KB blocks | 34% |
| 256 B blocks | 39% |

So roughly 60-80% of the payload is rewritten every single turn. There is no
practical way to isolate a few bytes of victory flag from that much legitimate
churn, and byte-level differential analysis of the game state is a dead end.
Reading the payload requires reverse-engineering the `CvGame` serialization
itself. The header, by contrast, is fully structured and safe to edit - which is
why this tool stays there.

## Where an achieved victory actually lives (and why you can't remove it)

Editing the header's `VICTORY_*` records makes a save *look* un-won, but it does
not undo the win. Civ VI permanently stops evaluating victory conditions once any
victory has been achieved — "One More Turn" lets you keep playing, not keep
winning. Symptom: every victory type shows **"Victory Not Completable"** on the
World Rankings *Overall* panel, because `Game.GetVictoryProgressForTeam()`
returns nil for every team.

Note the Overall panel and the per-victory tabs do *not* share a data source. The
Domination tab counts `city:IsOriginalCapital()` itself and keeps showing sensible
numbers; only the Overall panel asks the game core whether a win is still
possible. Don't read the tab as evidence the victory is still live.

The real state is in the compressed payload. It is findable — the tail
`GAME_SUMMARY` block, immediately before `CONTEXT_ACHIEVEMENTS`, grows from ~33
bytes to ~481 bytes when a victory fires, gaining one row per player per enabled
victory type, keyed by the same inverted-CRC32 hashes (`VICTORY_TECHNOLOGY` etc.)
the header uses. Pre-win it holds `ff ff ff ff ff ff ff ff`.

### The compressed section is chunked — this is the part that bites

It is **not** one flat zlib stream. The compressed bytes are stored in 64 KiB
chunks with a `u32` little-endian length of the *following* chunk written between
them:

    [64KiB compressed][u32 len][64KiB][u32 len]...[final partial chunk]

In one 3.6 MB save that is 54 separators: 53 reading exactly `65536` and a final
`63707`.

Two traps, both of which cost real time here:

1. **Inflating without stripping the separators appears to work.** zlib returns a
   plausible-looking buffer of nearly the right size (35,585,439 vs the correct
   35,594,002). It is silently wrong. The tell is that `00 00 01 00` decodes as a
   deflate stored-block header with `LEN=0, NLEN=1`, which is where an
   *"invalid stored block lengths"* error comes from if you inflate past it.
2. **Writing without re-inserting them makes Civ VI hang on load at 100% CPU** —
   with no error, and identically whether or not you changed anything. Build a
   rebuild-only control save to catch this; if the control hangs too, the
   container is wrong, not your edit.

**Credit where it is due: this chunking scheme is not a discovery of this
project.** It is documented in working code in
[lucienmaloney/civ6save-editing](https://github.com/lucienmaloney/civ6save-editing)
(`index.js`, `decompress`/`recompress`), which strips the separators on read and
re-interleaves them on write. `civ6save.py` here is a Python reimplementation of
that same approach; reading that repository is what unblocked this one after a
day of chasing the wrong cause. If you are doing anything with the compressed
payload, start there.

Undoing a victory is still unproven — Civ VI stops evaluating all victory
conditions permanently once one fires, and whether blanking the `GAME_SUMMARY`
references restores that is untested. Disabling victory conditions is proven.

## Caveats

- Whether the compressed game state *also* records a winner is not established
  here. Disabling the victory condition is the robust half; clearing the config
  records is cosmetic-to-semantic depending on what GameCore reads back.
- Offsets in this README come from one Standard-ruleset save. Use the hash, not
  hardcoded offsets — that is the whole point.
- Mod-heavy or scenario saves are untested.
- Keep a backup. This writes to a new file and never modifies the input, but be
  sensible.

## Verification

Changes are validated rather than assumed:

- Editing nothing reproduces the input **byte-for-byte**.
- Every output is independently re-split and fully inflated; the decompressed
  payload SHA-1 must match the input's.
- Every `GAME_ROOT` array's declared count must equal its parsed child count.
- Against a save from the turn *before* the victory, `--clear-victory` produces
  an identical configuration key set — no difference in either direction.

## Prior art and credit

Almost everything about the *container* here was worked out by other people
first. This project stands on:

- **[lucienmaloney/civ6save-editing](https://github.com/lucienmaloney/civ6save-editing)**
  — the 64 KiB chunking of the compressed section, in both directions. This is
  the single most important piece of knowledge for editing the payload, and it is
  the thing that is easiest to get catastrophically wrong. Its `index.js` is the
  reference `civ6save.py` follows.
- **[pydt/civ6-save-parser](https://github.com/pydt/civ6-save-parser)** — the
  header record layout and data types, and the reference implementation for
  reading these files. Its handling of null strings (tag `0x00`/`0x20` carrying
  four trailing bytes) fixed a parser bug here that had resisted several guesses.
- **[This CivFanatics thread](https://forums.civfanatics.com/threads/civ-6-savegame-editing-round-limit-score-victory.643742/)**
  — first pointed at victory settings living in the header at all. Its published
  offsets anchor one record earlier than the field they name, which the key-hash
  approach below makes moot, but it asked the right question first.
- **Firaxis' own shipped files** — `Assets/**/Configuration/**.xml` and the
  `GameCore_*.dll` string tables are the ground truth for every identifier name.
  Nothing here needed guessing once the hash was known.

What this project adds on top: deriving record keys as **inverted CRC-32** of the
setting name (so fields are identified by name rather than hardcoded offsets or
byte markers), the mapping of the victory configuration and the victory-result
records, and a tool that edits them.

## Acknowledgements

Found the hard way, in a real game, by someone who refused to accept two wrong
conclusions: that the Domination victory had "never been winnable" (a screenshot
of turn 611 showing 6 captured capitals settled that), and that the compressed
section could not be rebuilt (it can — see above). The in-place
`ff ff ff ff` blanking approach, which avoids the length changes that make
splicing unsafe, was their idea too.

## License

MIT
