"""Find where the tiles in a VRAM dump come from: a ROM, or a directory of decompressed blocks (stdlib only).

    python -X utf8 vramfind.py X.vram.bin SRC.. [--fmt snes4 | --tile 32] [--lo HEX --hi HEX] [--others Y.vram.bin ..]
    python -X utf8 vramfind.py --selftest

SRC: a ROM file, or a directory (every file under it, e.g. blocks you decompressed). Prints runs of consecutive
VRAM tiles that sit at consecutive offsets in one source, then the count of non-blank tiles found nowhere: those
are compressed (decompress the blocks and pass the directory) or built at run time.
Flags per run:  dup:N   a tile of the run also occurs at N other source offsets (the match may be the wrong copy);
                shared  a tile of the run also appears in an --others dump (another screen loads it: editing it
                        changes that screen too).
Confirm a match before editing: corrupt those source bytes, boot, and check the screen changed.
"""
import argparse
import os
import sys

SIZE = {"1bpp": 8, "snes2": 16, "snes4": 32, "snes8": 64, "gba4": 32, "gba8": 64}


def load_sources(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                out += [(os.path.join(root, f), open(os.path.join(root, f), "rb").read()) for f in sorted(files)]
        else:
            out.append((p, open(p, "rb").read()))
    return out


def find_all(data, t):
    i = data.find(t)
    while i >= 0:
        yield i
        i = data.find(t, i + 1)


def match(vram, sources, tile, lo=0, hi=None, others=()):
    """Runs [vram_start, source_name, src_start, ntiles, dups, shared] and the count of tiles found nowhere."""
    other_tiles = {o[i:i + tile] for o in others for i in range(0, len(o) - tile + 1, tile)}
    runs, missing, prev = [], 0, None
    for va in range(lo, min(hi or len(vram), len(vram)) - tile + 1, tile):
        t = vram[va:va + tile]
        if len(set(t)) <= 1:  # blank or flat fill: matches everywhere, says nothing
            prev = None
            continue
        hits = [(name, off) for name, data in sources for off in find_all(data, t)]
        if not hits:
            missing += 1
            prev = None
            continue
        r = runs[-1] if prev else None
        cont = r and (r[1], r[2] + r[3] * tile) in hits and va == r[0] + r[3] * tile
        if cont:
            r[3] += 1
        else:
            r = [va, hits[0][0], hits[0][1], 1, 0, False]
            runs.append(r)
        r[4] = max(r[4], len(hits) - 1)
        r[5] = r[5] or t in other_tiles
        prev = True
    return runs, missing


def selftest():
    a, b, c = bytes(range(32)), bytes(range(32, 64)), bytes(range(64, 96))
    rom = b"\0" * 64 + a + b + b"\x11" * 32 + c + c
    vram = a + b + bytes(32) + c + bytes(range(100, 132))
    runs, missing = match(vram, [("rom", rom)], 32, others=[b + bytes(32)])
    assert [r[:4] for r in runs] == [[0, "rom", 64, 2], [96, "rom", 160, 1]], runs
    assert runs[0][5] and not runs[1][5] and runs[1][4] == 1 and missing == 1
    print("selftest ok")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vram")
    ap.add_argument("src", nargs="+")
    ap.add_argument("--fmt", choices=SIZE, default="snes4", help="sets the tile size")
    ap.add_argument("--tile", type=int, help="tile size in bytes (overrides --fmt)")
    ap.add_argument("--lo", type=lambda s: int(s, 16), default=0, help="VRAM byte range to scan")
    ap.add_argument("--hi", type=lambda s: int(s, 16))
    ap.add_argument("--others", nargs="+", default=[], help="VRAM dumps of other screens")
    a = ap.parse_args()
    tile = a.tile or SIZE[a.fmt]
    vram = open(a.vram, "rb").read()
    runs, missing = match(vram, load_sources(a.src), tile, a.lo, a.hi, [open(p, "rb").read() for p in a.others])
    for va, name, off, n, dups, shared in runs:
        flags = (f" dup:{dups}" if dups else "") + (" shared" if shared else "")
        print(f"VRAM {va:05X}-{va + n * tile - 1:05X} ({n:3d} tiles) <- {name} {off:06X}-{off + n * tile - 1:06X}{flags}")
    print(f"{len(runs)} runs; {missing} non-blank tiles not found raw (compressed or built at run time)")


if __name__ == "__main__":
    main()
