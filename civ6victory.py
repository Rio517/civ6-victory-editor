#!/usr/bin/env python3
"""Inspect and edit victory state in Sid Meier's Civilization VI save files.

A .Civ6Save is:  plaintext header | one zlib stream | fixed 30025-byte trailer

Everything this tool changes lives in the plaintext header, so the multi-megabyte
compressed game state is copied through byte-for-byte and never re-encoded.

    civ6victory.py inspect "TRAJAN 646 1997 AD.Civ6Save"
    civ6victory.py edit in.Civ6Save -o out.Civ6Save --disable science,culture --clear-victory
"""
import argparse, os, re, struct, sys, zlib

import civ6fmt
from civ6fmt import civhash

# Config keys are one boolean per victory type, named exactly as the VictoryType
# rows in Assets/Base/Assets/Configuration/Data/Victories.xml.
VICTORY_FLAGS = {
    'science':    'VICTORY_TECHNOLOGY',
    'culture':    'VICTORY_CULTURE',
    'domination': 'VICTORY_CONQUEST',
    'religion':   'VICTORY_RELIGIOUS',
    'score':      'VICTORY_SCORE',
    'diplomatic': 'VICTORY_DIPLOMATIC',   # Gathering Storm ruleset only
}
# Written into the live config only once a victory has actually been achieved.
VICTORY_RESULT = ['VICTORY_NAME', 'VICTORY_TEAM', 'VICTORY_TYPE', 'VICTORY_PLAYER_NAME']


def find_compressed_start(data: bytes) -> int:
    """Offset of the single real zlib stream (there are many false 78 9c pairs)."""
    for m in re.finditer(b'\x78\x9c', data):
        i = m.start()
        try:
            if len(zlib.decompressobj().decompress(data[i:i + 200_000])) > 100_000:
                return i
        except zlib.error:
            pass
    raise RuntimeError('no compressed section found - not a .Civ6Save?')


def game_roots(header: bytes):
    """The GAME_ROOT config arrays: [0] = live config, [1] = original game setup."""
    sig = struct.pack('<I', civhash('GAME_ROOT')) + b'\x0a\x00\x00\x00'
    roots = []
    for m in re.finditer(re.escape(sig), header):
        recs, _ = civ6fmt.parse_records(header, m.start(), count=1)
        roots.append(recs[0])
    return roots


def inspect(path):
    data = open(path, 'rb').read()
    header = data[:find_compressed_start(data)]
    roots = game_roots(header)
    print(f'{os.path.basename(path)}: header {len(header)} B, '
          f'{len(data) - len(header)} B compressed+trailer')
    for i, root in enumerate(roots):
        label = 'live config' if i == 0 else 'original setup'
        print(f'\n  GAME_ROOT[{i}] ({label}) - {root.count} entries')
        for c in root.children:
            name = next((n for n in list(VICTORY_FLAGS.values()) + VICTORY_RESULT
                         if c.key == civhash(n)), None)
            if not name:
                continue
            if c.type in (5, 6):
                val = c.raw.rstrip(b'\x00').decode('utf-8', 'replace')[:60]
            else:
                val = c.val
            print(f'    {name:22} = {val}')
        if not any(c.key == civhash(n) for c in root.children for n in VICTORY_RESULT):
            print('    (no victory recorded)')


def edit(path, out, disable=(), enable=(), clear_victory=False, quiet=False):
    data = open(path, 'rb').read()
    start = find_compressed_start(data)
    header, rest = bytearray(data[:start]), data[start:]
    log = []

    wanted = {VICTORY_FLAGS[k]: 0 for k in disable}
    wanted.update({VICTORY_FLAGS[k]: 1 for k in enable})

    for root in game_roots(bytes(header)):
        for c in root.children:
            for name, want in wanted.items():
                if c.key == civhash(name) and c.val != want:
                    struct.pack_into('<i', header, c.val_off, want)
                    log.append(f'  {c.off:7d}  {name:22} {c.val} -> {want}')

    if clear_victory:
        targets = {civhash(n): n for n in VICTORY_RESULT}
        while True:
            hit = next(((root, c) for root in game_roots(bytes(header))
                        for c in root.children if c.key in targets), None)
            if not hit:
                break
            root, c = hit
            log.append(f'  {c.off:7d}  delete {targets[c.key]:22} ({c.end - c.off} B)')
            del header[c.off:c.end]
            struct.pack_into('<I', header, root.count_off, root.count - 1)

    open(out, 'wb').write(bytes(header) + rest)

    roots = game_roots(bytes(header))
    assert all(len(r.children) == r.count for r in roots), 'array count check failed'
    if not quiet:
        print(os.path.basename(out))
        print('\n'.join(log) if log else '  (no changes)')
        print(f'  header {start} -> {len(header)} B; {len(rest)} B copied verbatim; '
              f'arrays ' + ', '.join(f'{len(r.children)}/{r.count}' for r in roots) + ' OK')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('inspect', help='show victory config and any recorded victory')
    p.add_argument('save')

    p = sub.add_parser('edit', help='write a modified copy')
    p.add_argument('save')
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--disable', default='', help='comma list: ' + ','.join(VICTORY_FLAGS))
    p.add_argument('--enable', default='', help='comma list: ' + ','.join(VICTORY_FLAGS))
    p.add_argument('--clear-victory', action='store_true',
                   help='remove the VICTORY_* records an achieved victory leaves behind')

    a = ap.parse_args()
    if a.cmd == 'inspect':
        inspect(a.save)
    else:
        split = lambda s: [x.strip() for x in s.split(',') if x.strip()]
        bad = [x for x in split(a.disable) + split(a.enable) if x not in VICTORY_FLAGS]
        if bad:
            sys.exit(f'unknown victory type(s): {bad}; choose from {list(VICTORY_FLAGS)}')
        edit(a.save, a.out, split(a.disable), split(a.enable), a.clear_victory)


if __name__ == '__main__':
    main()
