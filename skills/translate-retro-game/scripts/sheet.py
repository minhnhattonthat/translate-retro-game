"""Contact sheets from emulator screenshots (stdlib only: no PIL needed).

    python sheet.py DIR [--cols 4] [--div 2] [--max 16] [--changed 0.02] [--out DIR/sheet.png]

Takes DIR/f*.png in name order. --changed keeps a frame only when more than that fraction of its pixels differ
from the last kept frame, so a static screen held for 600 frames costs one tile, not ten. Read the sheet instead
of the individual PNGs: one image Read instead of sixteen.
"""
import argparse, glob, os, struct, zlib


def read_png(path):
    d = open(path, "rb").read()
    pos, idat, w, h, ct = 8, b"", 0, 0, 0
    while pos < len(d):
        ln, = struct.unpack(">I", d[pos:pos + 4])
        tag, body = d[pos + 4:pos + 8], d[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h, depth, ct = struct.unpack(">IIBB", body[:10])
            if depth != 8 or ct not in (2, 6):
                raise ValueError(f"{path}: only 8-bit RGB/RGBA PNGs supported")
        elif tag == b"IDAT":
            idat += body
    bpp = {2: 3, 6: 4}[ct]
    raw, stride, rows, prev, i = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line))
        prev = line
    return w, h, bpp, rows


def write_png(path, w, h, rows):
    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"".join(b"\0" + r for r in rows))) + chunk(b"IEND", b""))


def diff(a, b):
    """Fraction of pixels that differ between two decoded images (compared over the common area)."""
    (wa, ha, pa, ra), (wb, hb, pb, rb) = a, b
    n = d = 0
    for y in range(min(ha, hb)):
        for x in range(min(wa, wb)):
            n += 1
            d += ra[y][x * pa:x * pa + 3] != rb[y][x * pb:x * pb + 3]
    return d / n if n else 0.0


def is_blank(img, tol=8):
    """True when every pixel is within tol of the first one (black screen, white flash, frozen fill)."""
    w, h, bpp, rows = img
    ref = rows[0][:3]
    return all(abs(r[x] - ref[x % 3]) <= tol for r in rows for x in range(0, w * bpp) if x % bpp < 3)


def select(paths, changed):
    kept, last = [], None
    for p in paths:
        img = read_png(p)
        if last is None or diff(last, img) > changed:
            kept.append((p, img))
            last = img
    return kept


def sheet(imgs, cols, out, div=1):
    w, h = max(i[0] for i in imgs) // div, max(i[1] for i in imgs) // div  # PS1/NDS games change resolution
    r = (len(imgs) + cols - 1) // cols
    W, H = cols * (w + 2), r * (h + 2)
    canvas = [bytearray(b"\x40\x00\x40" * W) for _ in range(H)]
    for k, (iw, _, bpp, rows) in enumerate(imgs):
        ox, oy = (k % cols) * (w + 2), (k // cols) * (h + 2)
        for y in range(min(h, len(rows) // div)):
            src = rows[y * div]
            for x in range(iw // div):
                p = x * div * bpp
                canvas[oy + y][(ox + x) * 3:(ox + x) * 3 + 3] = src[p:p + 3]
    write_png(out, W, H, [bytes(c) for c in canvas])
    return out


def make(d, cols=4, div=2, limit=16, changed=0.0, out=None):
    paths = sorted(glob.glob(os.path.join(d, "f[0-9]*.png")))
    if not paths:
        raise SystemExit(f"no f<frame>.png in {d}")
    kept = select(paths, changed) if changed else [(p, read_png(p)) for p in paths]
    if len(kept) > limit:  # spread the tiles over the whole run rather than taking the first ones
        step = len(kept) / limit
        kept = [kept[int(i * step)] for i in range(limit)]
    out = out or os.path.join(d, "sheet.png")
    sheet([img for _, img in kept], cols, out, div)
    print(out)
    print("tiles (row-major):", " ".join(os.path.basename(p)[:-4] for p, _ in kept))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--div", type=int, default=2, help="downscale factor (1 = full size, for reading small text)")
    ap.add_argument("--max", type=int, default=16)
    ap.add_argument("--changed", type=float, default=0.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    make(a.dir, a.cols, a.div, a.max, a.changed, a.out)
