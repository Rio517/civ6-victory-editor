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
|  one zlib stream         |   <-- the entire game state, tens of MB inflated
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

## Prior art

[pydt/civ6-save-parser](https://github.com/pydt/civ6-save-parser) documents the
container and record types and is the reference implementation for reading these
files; it identifies fields by hardcoded byte markers rather than by hashing
names. This project adds the key-hash derivation and the victory-specific
editing on top.

## License

MIT
