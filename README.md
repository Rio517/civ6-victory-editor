# civ6-victory-editor

Turns victory conditions on and off in a Civilization VI save, and clears the
record a completed victory leaves behind.

The usual reason to want this: you won a Science victory, chose "One More Turn",
and the game keeps trying to end on conditions you don't care about. Disabling
those conditions in the save stops it.

```bash
python3 civ6victory.py inspect "TRAJAN 646 1997 AD.Civ6Save"

python3 civ6victory.py edit "TRAJAN 646 1997 AD.Civ6Save" \
    -o "TRAJAN 646 continued.Civ6Save" \
    --disable science,culture,religion --clear-victory
```

Python 3.8 or newer, no dependencies. The input file is never modified. Drop the
output into your `Saves/Single` folder and load it from the normal menu.

If you plan to edit the compressed payload rather than the header, read
[The stream is chunked](#the-stream-is-chunked) first.

## Understanding the save format

A `.Civ6Save` is three pieces laid end to end:

```
+--------------------------+  offset 0
|  'CIV6' + version words  |
|  plaintext record tree   |   <-- all game configuration lives here
+--------------------------+  ~150 KB in a late-game save
|  chunked deflate stream  |   <-- the entire game state, tens of MB inflated
+--------------------------+
|  30025-byte trailer      |
+--------------------------+
```

The header is uncompressed and holds every setting the game was configured with.
Three things make it straightforward to edit:

- There are no checksums. Nothing validates one part of the file against another.
- There are no stored offsets or lengths. Searching a save for its own header
  length, compressed length or total size turns up nothing, so the header can
  grow or shrink freely.
- Game configuration exists only in the header. It is not duplicated inside the
  compressed payload, so settings can be rewritten while the compressed bytes and
  the trailer are copied through untouched.

### Records

The header is a tree of records, each starting with a 32-bit key and a 32-bit
type:

| Type | Payload |
|-----:|---------|
| `0x00` | none |
| `0x01` `0x02` `0x03` `0x04` | 8 pad bytes, then an `i32` (bool, int, or hashed enum) |
| `0x05` | `u24` length, `u8` tag, `u32`, then that many bytes of NUL-terminated UTF-8 |
| `0x06` | as `0x05`, but length counts UTF-16LE code units |
| `0x18` | as `0x05`, but the payload is a nested zlib blob |
| `0x0a` | `u32` count, then that many child records |
| `0x0b` | `u32` count, then that many anonymous `0x0a` groups |
| `0x14` `0x15` | 16 bytes |

Tag `0x21` is an ordinary string. Tags `0x00` and `0x20` are both null strings,
which carry no data but still occupy four trailing bytes. Missing that
desynchronises a parser thousands of records later with no obvious cause.

### The keys are hashed field names

Records are keyed by number, which makes the header look opaque. The key is a
CRC-32 of the field name with the final complement left off, i.e. the raw CRC
register value:

```python
def civhash(name):
    return (~zlib.crc32(name.encode())) & 0xFFFFFFFF
```

Hash the identifiers Firaxis ships in the game's own XML and binaries and the
header decodes itself:

```
0x150c2d79  VICTORY_TECHNOLOGY      0x871d5b63  GAME_ROOT
0x1843ff8c  VICTORY_CONQUEST        0xcfcadc3e  GAME_NAME
0x18c44790  VICTORY_RELIGIOUS       0x626c4c82  GAME_STATE
0xeabc48eb  VICTORY_CULTURE         0xc5fbfa24  GAME_HANDICAP
0x5529a9bb  VICTORY_SCORE           0x1b8cd1c8  ENABLED_MODS
```

The same hash covers values as well as keys. Type `0x03` records hold a hashed
enum name, so the same table reads them back: `GAME_HANDICAP` resolves to
`DIFFICULTY_PRINCE`, `GAME_STATE` to `GAMESTATE_LAUNCHED`, `TURN_TIMER_TYPE` to
`TURNTIMER_NONE`.

To build the table, walk an installed copy of the game, pull every
identifier-like string from `Assets/**/Configuration/**.xml` and the
`GameCore_*.dll` string tables, and hash each one. Identifying fields by name
means the tool works on saves whose records sit at different offsets.

### Victory settings

Every save has two `GAME_ROOT` arrays: the live configuration and the original
game setup. Both hold one boolean per victory type, named as the `VictoryType`
rows in the game's `Configuration/Data/Victories.xml`: `VICTORY_TECHNOLOGY`,
`VICTORY_CULTURE`, `VICTORY_CONQUEST`, `VICTORY_RELIGIOUS`, `VICTORY_SCORE`, and
`VICTORY_DIPLOMATIC` under the Gathering Storm ruleset.

These booleans are what `Game.IsVictoryEnabled()` reads, so setting one to zero
removes that victory type from the game. Confirmed in play: after disabling
`VICTORY_TECHNOLOGY`, the Science row disappears from the Overall panel of the
World Rankings screen, which is gated on that call. `--disable` writes both
arrays so the live and setup configurations agree.

### What winning writes into the header

When a victory fires, four records appear in the live configuration and not in
the setup array:

- `VICTORY_TYPE` — the row index from `Victories.xml`
- `VICTORY_TEAM`
- `VICTORY_NAME` — localised JSON, e.g. `{"LOC_VICTORY_SCIENCE_NAME": ...}`
- `VICTORY_PLAYER_NAME`

`--clear-victory` removes all four and decrements the enclosing array's count,
leaving a configuration block indistinguishable from one saved before the
victory. That changes how the save describes itself, not whether the game
considers itself decided; see [Where an achieved victory
lives](#where-an-achieved-victory-lives).

## Working inside the compressed game state

Most things worth changing are in the header. If you need the payload anyway,
two things are worth knowing first.

### The stream is chunked

The compressed section is not one flat zlib stream. It is stored as 64 KiB
chunks of compressed bytes, with a little-endian `u32` giving the length of the
following chunk written between them:

```
[64KiB compressed][u32 len][64KiB][u32 len]...[final partial chunk]
```

A 3.6 MB save has 54 separators, 53 reading exactly `65536` and a last one
giving the size of the remainder.

Both directions fail quietly if you ignore this:

- Inflating without stripping the separators appears to work. zlib returns a
  plausible buffer of nearly the right size — 35,585,439 bytes against a true
  35,594,002 — and the contents are subtly wrong. `00 00 01 00` read as deflate
  is a stored-block header with `LEN=0, NLEN=1`, which is where an "invalid
  stored block lengths" error comes from if you inflate past one.
- Writing without re-inserting them makes the game hang on load at 100% CPU,
  with no error, whether or not you changed anything.

Because the write failure looks identical either way, build a rebuild-only
control save that changes nothing. If the control hangs, the container is wrong
rather than the edit.

The chunking is not something this project worked out. It is implemented in
[lucienmaloney/civ6save-editing](https://github.com/lucienmaloney/civ6save-editing),
whose `index.js` strips the separators on read and re-interleaves them on write.
`civ6save.py` here is a Python reimplementation of the same approach.

### Diffing consecutive turns

Comparing a save against the previous turn to see what moved does not locate
anything useful. Between two consecutive late-game saves:

- Common prefix 133 bytes, common suffix 20 bytes
- Of sampled 4 KB blocks from the later save, 19% appear anywhere in the earlier
- At 1 KB, 34%; at 256 bytes, 39%

Roughly 60–80% of the payload is rewritten every turn, so a few interesting
bytes cannot be separated from ordinary churn. Locating values in the game state
means understanding the serialisation rather than diffing it.

### Where an achieved victory lives

Clearing the header records makes a save look un-won without undoing the win.
Civilization VI stops evaluating victory conditions permanently once any victory
has been achieved; "One More Turn" lets you keep playing, not keep winning. The
symptom is that every remaining victory type reports "Victory Not Completable"
on the World Rankings Overall panel, because `Game.GetVictoryProgressForTeam()`
returns nil for every team.

The per-victory tabs are not evidence to the contrary — they use a different
data source. The Domination tab counts `city:IsOriginalCapital()` itself and goes
on reporting sensible numbers after the game has stopped awarding victories.
Only the Overall panel asks the game core whether a win is still possible.

The record itself is in the payload. The `GAME_SUMMARY` block at the tail,
immediately before `CONTEXT_ACHIEVEMENTS`, grows from about 33 bytes to about 481
when a victory fires, gaining a row per player per enabled victory type, keyed by
the same hashes the header uses. Before the win it holds
`ff ff ff ff ff ff ff ff`.

Whether overwriting those references restores victory evaluation is untested. The
authoritative flag may be elsewhere in the `CvGame` serialisation, with this block
only feeding the end-game screen. Disabling victory conditions is proven; undoing
a victory is not.

## Investigation log: removing an achieved victory

This is unsolved. What follows is what was tried, so the next attempt can start
further along.

**The problem.** After a victory fires, every victory type reports "Victory Not
Completable" on the World Rankings Overall panel, because
`Game.GetVictoryProgressForTeam()` returns nil for every team. The goal was to
restore normal victory evaluation on a late-game save without rolling back.

**Tested in the game and ruled out:**

- Deleting the four `VICTORY_*` records from the header configuration.
- Keeping them but setting `VICTORY_TEAM` and `VICTORY_TYPE` to `-1`. Worth
  testing separately from deletion, since a missing key may read back as `0`,
  which is a valid team id and says "team 0 won" rather than "nobody won". It
  made no difference either.
- Blanking all 29 `VICTORY_TECHNOLOGY` references in the payload's tail
  `GAME_SUMMARY` block. That block is populated when a victory fires and holds
  a row per player per enabled victory type, but editing it changes nothing, so
  it only feeds the end-game screen.
- Reverting 63, then 32, byte-level fields that survived a strict differential
  filter (details below). Both batches, and the single best candidate on its
  own, made no difference.

**How the differential search worked.** Payloads are aligned by content-defined
chunking followed by a sequence diff of the chunk hashes; matched chunks are
byte-identical, so positions map exactly. Each save's own turn number is
normalised first, because it appears ~1750 times and otherwise dominates every
comparison. Candidate fields are then required to hold one value in *both*
pre-win saves and the same different value in *all* post-win saves, which for
this game spanned turns 614 to 657. Ordinary churn does not survive that.

Two traps are worth knowing. A first pass compared only regions of identical
length, which silently skipped every region that resized - 52% of all changed
bytes. Closing that needs a second alignment level that re-chunks each resized
gap more finely. And a chunk-level version of the filter (whole chunks identical
across all post-win saves) only matches static regions, because any chunk
holding the flag also holds per-turn churn.

**What the search concluded.** After both passes, covering essentially all
changed bytes, no field in the payload behaves like a victory flag. The
survivors were all explicable: tile ownership from conquests, diplomacy
requirement caches, per-turn history graphs, unit AI assignments, and one
`FEATURE_FOREST` tile change.

**The confound that was never resolved.** The whole search assumed the victory
caused the change, based on comparing a pre-win save that showed "You are
leading" against a post-win save 33 turns later that showed "Victory Not
Completable". Those two saves differ by a victory *and* by 33 turns of conquest,
including eliminating civilizations. The controlled test is the save from the
turn immediately after the victory, with victory conditions configured
identically to the working pre-win save. If that still reports "Victory Not
Completable", the victory is confirmed as the cause. If it reports "You are
leading", the cause is something during the intervening turns and the entire
search was aimed at the wrong signal. **Run this first next time.**

**Other things known.** The Lua API exposes only `GetVictoryProgressForTeam`,
`GetVictoryRequirements` and `IsVictoryEnabled` - all read-only, with no setter,
so a mod cannot clear a victory either. Domination in base rules requires owning
every non-city-state city, evaluated by the hardcoded C++ requirement
`REQUIREMENT_TEAM_DOMINATION_VICTORY`, which takes no arguments and so cannot be
retuned from XML. The Overall panel and the per-victory tabs do not share a data
source, so the Domination tab continuing to show sensible capital counts says
nothing about whether a victory can still be awarded.

## Limits

- Offsets quoted above come from one Standard-ruleset save and are illustrative.
  Use the hash to find fields, not a hardcoded offset.
- Mod-heavy and scenario saves are untested.
- Keep a backup, though the tool never writes to its input.

Changes are checked rather than assumed:

- Editing nothing reproduces the input byte for byte.
- Every output is independently re-split and re-inflated, and its payload must
  hash identically to the input's unless the payload was deliberately changed.
- Every `GAME_ROOT` array's declared count must match the children parsed.
- `--clear-victory` was validated against a save from the turn before a victory:
  the resulting configuration key sets are identical in both directions.

## Prior art and credit

Nearly everything about the container was worked out by other people first.

- [lucienmaloney/civ6save-editing](https://github.com/lucienmaloney/civ6save-editing)
  documents the 64 KiB chunking in both directions. Reading it is what unblocked
  this project after a long detour.
- [pydt/civ6-save-parser](https://github.com/pydt/civ6-save-parser) is the
  reference implementation for reading these files and documents the header
  record layout and data types. Its handling of null strings, where tags `0x00`
  and `0x20` carry four trailing bytes, fixed a parser bug here.
- [A CivFanatics thread on save
  editing](https://forums.civfanatics.com/threads/civ-6-savegame-editing-round-limit-score-victory.643742/)
  first pointed at victory settings living in the header. Its published offsets
  anchor one record earlier than the field they name, which the hash approach
  makes moot, but it asked the question first.
- Firaxis' shipped files are the ground truth for every identifier name.

What this project adds is the key derivation, which turns numbered records into
named ones and removes the dependence on hardcoded offsets, plus the mapping of
the victory configuration and victory-result records and a tool to edit them.

## Acknowledgements

Worked out during a real game, largely because the person playing it declined to
accept two wrong conclusions: that Domination had never been winnable in that
game, disproved by a screenshot of turn 611 showing six captured capitals, and
that the compressed section could not be rebuilt, which was the chunking bug
above. Overwriting the victory references in place, rather than splicing a
shorter block in from another save, was also their suggestion, and is why the
edit preserves length and leaves surrounding offsets alone.

## License

MIT
