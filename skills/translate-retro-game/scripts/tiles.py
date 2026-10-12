"""Tile graphics to PNG and back (stdlib only). For text drawn as graphics: title logos, menus, signs.

    python -X utf8 tiles.py render FILE OUT.png --fmt snes4 [--at HEX] [--len HEX] [--cols 16] [--zoom 2]
                                    [--pal X.pal.bin --pal-index N]
    python -X utf8 tiles.py import EDITED.png FILE --out NEW --fmt snes4 --at HEX [--count N] [--zoom 2] [--pal ..]
    python -X utf8 tiles.py map VRAM.bin OUT.png --fmt snes4 --map-at HEX --tiles-at HEX [--w 32 --h 32] [--pal ..]
    python -X utf8 tiles.py --selftest

Formats: snes2 snes4 snes8 (planar), gba4 gba8 (linear, also NDS), 1bpp (8 bytes per tile, MSB = left pixel).
FILE is a ROM, a decompressed block or an emulator VRAM dump. --pal is a BGR555 dump (SNES CGRAM, GBA/NDS palette
RAM); --pal-index picks the sub-palette (2**bpp colours each). Without --pal the sheet is greyscale by index.
render writes plain tiles (no labels or grid) so the PNG can be edited and imported back with the same --fmt, --pal,
--pal-index and --zoom; it prints the import command. Save edits as 8-bit RGB PNG. import refuses any colour not in
the palette, and where several indices share a colour it keeps the index the original pixel had.
map renders a BG tilemap (32x32 screens, entries 16-bit LE; SNES vhopppcc cccccccc, GBA text-BG ppppvhcc cccccccc).
Byte addresses throughout: a SNES VRAM word address times 2.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheet as sheetmod  # noqa: E402  (stdlib PNG read/write)

SIZE = {"1bpp": 8, "snes2": 16, "snes4": 32, "snes8": 64, "gba4": 32, "gba8": 64}
BPP = {"1bpp": 1, "snes2": 2, "snes4": 4, "snes8": 8, "gba4": 4, "gba8": 8}


def decode(fmt, d):
    """One tile -> 64 colour indices, row-major."""
    if fmt == "gba8":
        return list(d[:64])
    if fmt == "gba4":
        return [d[i // 2] >> (4 * (i & 1)) & 15 for i in range(64)]  # low nibble = left pixel
    if fmt == "1bpp":
        return [d[y] >> (7 - x) & 1 for y in range(8) for x in range(8)]
    bpp = BPP[fmt]
    return [sum((d[16 * (p // 2) + 2 * y + (p & 1)] >> (7 - x) & 1) << p for p in range(bpp))
            for y in range(8) for x in range(8)]


def encode(fmt, px):
    if fmt == "gba8":
        return bytes(px)
    if fmt == "gba4":
        return bytes(px[i] | px[i + 1] << 4 for i in range(0, 64, 2))
    out = bytearray(SIZE[fmt])
    for i, c in enumerate(px):
        y, x = divmod(i, 8)
        for p in range(BPP[fmt]):
            if c >> p & 1:
                out[y if fmt == "1bpp" else 16 * (p // 2) + 2 * y + (p & 1)] |= 0x80 >> x
    return bytes(out)


def palette(path, index, bpp):
    """2**bpp RGB tuples: sub-palette `index` of a BGR555 dump, or greys by index."""
    n = 1 << bpp
    if not path:
        return [(v * 255 // (n - 1),) * 3 for v in range(n)]
    raw = open(path, "rb").read()
    out = []
    for i in range(index * n, index * n + n):
        w = raw[2 * i] | raw[2 * i + 1] << 8 if 2 * i + 1 < len(raw) else 0
        out.append(((w & 31) << 3, (w >> 5 & 31) << 3, (w >> 10 & 31) << 3))
    return out


def to_rows(grid, zoom):
    """grid: rows of RGB tuples -> PNG rows, nearest-neighbour zoom."""
    rows = []
    for r in grid:
        line = b"".join(bytes(c) * zoom for c in r)
        rows += [line] * zoom
    return rows


def render(data, fmt, pal, cols, zoom, out):
    size = SIZE[fmt]
    n = len(data) // size
    w, h = cols * 8, -(-n // cols) * 8
    grid = [[pal[0]] * w for _ in range(h)]
    for t in range(n):
        px = decode(fmt, data[t * size:(t + 1) * size])
        ox, oy = t % cols * 8, t // cols * 8
        for i, c in enumerate(px):
            grid[oy + i // 8][ox + i % 8] = pal[c]
    sheetmod.write_png(out, w * zoom, h * zoom, to_rows(grid, zoom))
    return n


def import_png(path, orig, fmt, pal, zoom, count):
    """Edited PNG -> tile bytes. orig: the bytes the PNG was rendered from (keeps indices of duplicate colours)."""
    w, h, bpp, rows = sheetmod.read_png(path)
    if w % (8 * zoom) or h % (8 * zoom):
        raise SystemExit(f"{path}: {w}x{h} is not a multiple of {8 * zoom} (tile size x zoom)")
    choices = {}
    for i, c in enumerate(pal):
        choices.setdefault(c, []).append(i)
    cols, size = w // (8 * zoom), SIZE[fmt]
    total = cols * (h // (8 * zoom))
    count = total if count is None else count
    if count > total:
        raise SystemExit(f"{path}: holds {total} tiles, --count {count}")
    out = bytearray()
    for t in range(count):
        old = decode(fmt, orig[t * size:(t + 1) * size]) if len(orig) >= (t + 1) * size else [0] * 64
        px = []
        for i in range(64):
            x, y = (t % cols * 8 + i % 8) * zoom, (t // cols * 8 + i // 8) * zoom
            c = tuple(rows[y][x * bpp:x * bpp + 3])
            if c not in choices:
                raise SystemExit(f"{path}: pixel ({x},{y}) colour {c} is not in the palette {sorted(choices)}")
            px.append(old[i] if old[i] in choices[c] else choices[c][0])
        out += encode(fmt, px)
    return bytes(out)


def render_map(vram, fmt, map_at, tiles_at, w, h, pal_path, zoom, out):
    bpp, size = BPP[fmt], SIZE[fmt]
    full = palette(pal_path, 0, 8) if pal_path else None
    grey = palette(None, 0, bpp)
    grid = [[(0, 0, 0)] * (w * 8) for _ in range(h * 8)]
    for ty in range(h):
        for tx in range(w):
            k = (ty // 32) * (w // 32 or 1) * 1024 + (tx // 32) * 1024 + (ty % 32) * 32 + tx % 32
            e = int.from_bytes(vram[map_at + 2 * k:map_at + 2 * k + 2], "little")
            if fmt.startswith("snes"):
                tile, pal, hf, vf = e & 0x3FF, e >> 10 & 7, e & 0x4000, e & 0x8000
            else:
                tile, pal, hf, vf = e & 0x3FF, e >> 12, e & 0x400, e & 0x800
            a = (tiles_at + tile * size) % len(vram)
            px = decode(fmt, vram[a:a + size].ljust(size, b"\0"))
            base = 0 if bpp == 8 else pal << bpp
            for i, c in enumerate(px):
                x, y = i % 8, i // 8
                x, y = 7 - x if hf else x, 7 - y if vf else y
                grid[ty * 8 + y][tx * 8 + x] = full[base + c] if full else grey[c]
    sheetmod.write_png(out, w * 8 * zoom, h * 8 * zoom, to_rows(grid, zoom))


def selftest():
    import random
    import tempfile
    rnd = random.Random(1)
    for fmt in SIZE:
        px = [rnd.randrange(1 << BPP[fmt]) for _ in range(64)]
        assert decode(fmt, encode(fmt, px)) == px, fmt
    assert decode("snes2", bytes([0x80, 0x80] + [0] * 14))[0] == 3
    assert decode("gba4", bytes([0x21] + [0] * 31))[:2] == [1, 2]
    pal = [(0, 0, 0), (8, 8, 8), (0, 0, 0), (248, 0, 0)] * 4  # duplicate colours
    data = bytes(rnd.randrange(256) for _ in range(32 * 5))
    with tempfile.TemporaryDirectory() as d:
        png = os.path.join(d, "t.png")
        assert render(data, "snes4", pal, 4, 2, png) == 5
        back = import_png(png, data, "snes4", pal, 2, 5)
        assert [pal[c] for c in decode("snes4", back)] == [pal[c] for c in decode("snes4", data)]
        assert back == data  # duplicate colours kept their original indices
        vram = bytearray(0x10000)
        vram[0x8000:0x8020] = encode("snes4", [1] * 64)
        vram[0:2] = (0x4000).to_bytes(2, "little")  # tile 0, hflip
        render_map(bytes(vram), "snes4", 0, 0x8000, 32, 32, None, 1, png)
        assert sheetmod.read_png(png)[:2] == (256, 256)
    print("selftest ok")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    hexint = lambda s: int(s, 16)  # noqa: E731
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render", "import", "map"):
        p = sub.add_parser(name)
        p.add_argument("src")
        p.add_argument("dst")
        p.add_argument("--fmt", choices=SIZE, required=True)
        p.add_argument("--zoom", type=int, default=1)
        p.add_argument("--pal")
        p.add_argument("--pal-index", type=int, default=0)
        if name == "map":
            p.add_argument("--map-at", type=hexint, required=True)
            p.add_argument("--tiles-at", type=hexint, required=True)
            p.add_argument("--w", type=int, default=32)
            p.add_argument("--h", type=int, default=32)
        else:
            p.add_argument("--at", type=hexint, default=0)
            p.add_argument("--cols", type=int, default=16)
        if name == "render":
            p.add_argument("--len", type=hexint)
        if name == "import":
            p.add_argument("--out", required=True, help="patched copy of FILE (never written in place)")
            p.add_argument("--count", type=int, help="tiles to write (default: every tile in the PNG)")
    a = ap.parse_args()
    if a.cmd == "map":
        render_map(open(a.src, "rb").read(), a.fmt, a.map_at, a.tiles_at, a.w, a.h, a.pal, a.zoom, a.dst)
        print(a.dst)
        return
    pal = palette(a.pal, a.pal_index, BPP[a.fmt])
    if a.cmd == "render":
        data = open(a.src, "rb").read()[a.at:a.at + a.len if a.len else None]
        n = render(data, a.fmt, pal, a.cols, a.zoom, a.dst)
        opts = f" --pal {a.pal} --pal-index {a.pal_index}" if a.pal else ""
        print(f"{a.dst}: {n} tiles\nre-import: tiles.py import {a.dst} {a.src} --out NEW --fmt {a.fmt} --at {a.at:X}"
              f" --count {n} --zoom {a.zoom}{opts}")
        return
    blob = bytearray(open(a.dst, "rb").read())
    new = import_png(a.src, blob[a.at:], a.fmt, pal, a.zoom, a.count)
    if a.at + len(new) > len(blob):
        raise SystemExit(f"import runs past the end of {a.dst}")
    changed = sum(x != y for x, y in zip(blob[a.at:a.at + len(new)], new))
    blob[a.at:a.at + len(new)] = new
    open(a.out, "wb").write(blob)
    print(f"{a.out}: wrote {len(new) // SIZE[a.fmt]} tiles at {a.at:X}, {changed} bytes changed")


if __name__ == "__main__":
    main()
