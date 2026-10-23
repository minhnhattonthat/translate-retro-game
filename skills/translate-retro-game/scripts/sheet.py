"""Contact sheets from emulator screenshots (stdlib only: no PIL needed).

    python sheet.py SRC.. [--cols 4] [--div 2] [--max 16] [--changed 0.02] [--out DIR/sheet.png]
                    [--from 1200 --to 2400] [--crop x,y,w,h] [--zoom 3] [--rotate 90] [--compare DIR2|B.png]
    python sheet.py shot.png --crop 8,150,240,40 --zoom 3            zoom into one frame's text box
    python sheet.py en/f004200.png --compare jp/f004230.png --zoom 2   two frames side by side, any names

Use this instead of ad-hoc PIL crop/resize/paste snippets: it already does single files, crops, zoom and pairs.
SRC is a directory (takes its f<frame>.png in name order), PNG files, or a quoted glob ("work/qa/f00[3-4]*.png").
Any 8-bit-or-less PNG works (RGB, RGBA, grey, palette).
--changed keeps a frame only when more than that fraction of its pixels differ from the last kept frame, so a
static screen held for 600 frames costs one tile, not ten. Read the sheet instead of the individual PNGs: one
image Read instead of sixteen.
--max N       tiles per page; more frames go to sheet_2.png, sheet_3.png... (no frame is dropped). Pages also
              stay within 2000 px a side (fewer columns or tiles), since readers shrink larger images.
--from/--to   keep frames whose number (from the file name) is in [from, to].
--crop        cut each frame to the text box, x,y,w,h in source pixels, before --rotate and --zoom.
--zoom N      nearest-neighbour upscale to read small or thin glyphs; check fonts this way.
--div N       downscale; default 2, or 1 with --crop/--zoom.
--rotate 90   clockwise, for games played sideways (vertical handheld text); 180/270 also work.
--compare X   pair each frame with the same-named file in directory X, or with the one PNG X (left | right).
"""
import argparse, glob, os, re, struct, zlib

MAX_SIDE = 2000  # image readers downscale anything larger, which makes small text unreadable


def read_png(path):
    """(w, h, bpp, rows) with bpp 3 (RGB) or 4 (RGBA); grey, grey+alpha and palette PNGs come back as RGB(A)."""
    d = open(path, "rb").read()
    pos, idat, w, h, ct, depth, plte, trns = 8, b"", 0, 0, 0, 8, b"", b""
    while pos < len(d):
        ln, = struct.unpack(">I", d[pos:pos + 4])
        tag, body = d[pos + 4:pos + 8], d[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h, depth, ct, _, _, interlace = struct.unpack(">IIBBBBB", body[:13])
            if depth == 16 or interlace or (depth < 8 and ct not in (0, 3)):
                raise ValueError(f"{path}: 16-bit and interlaced PNGs are not supported")
        elif tag == b"PLTE":
            plte = body
        elif tag == b"tRNS":
            trns = body
        elif tag == b"IDAT":
            idat += body
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    bpp = max(1, chans * depth // 8)  # filter unit in bytes
    stride = (w * chans * depth + 7) // 8
    rows = _unfilter(zlib.decompress(idat), h, stride, bpp)
    if ct in (2, 6):
        return w, h, chans, rows
    if depth < 8:  # unpack 1/2/4-bit samples to one byte each
        mask, per = (1 << depth) - 1, 8 // depth
        rows = [bytes((r[x // per] >> (8 - depth * (x % per + 1))) & mask for x in range(w)) for r in rows]
        if ct == 0:
            rows = [bytes(v * 255 // mask for v in r) for r in rows]
    if ct == 3:
        alpha = bool(trns)
        lut = [plte[i * 3:i * 3 + 3] + (bytes([trns[i] if i < len(trns) else 255]) if alpha else b"")
               for i in range(256)]
        return w, h, 4 if alpha else 3, [b"".join(lut[v] for v in r) for r in rows]
    if ct == 0:
        return w, h, 3, [bytes(v for v in r for _ in range(3)) for r in rows]
    return w, h, 4, [b"".join(bytes([r[x], r[x], r[x], r[x + 1]]) for x in range(0, len(r), 2)) for r in rows]


def _unfilter(raw, h, stride, bpp):
    rows, prev, i = [], bytearray(stride), 0
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
    return rows


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


def crop(img, x, y, w, h):
    iw, ih, bpp, rows = img
    w, h = min(w, iw - x), min(h, ih - y)
    return w, h, bpp, [r[x * bpp:(x + w) * bpp] for r in rows[y:y + h]]


def rotate(img, deg):
    """Clockwise in 90-degree steps."""
    for _ in range(deg // 90 % 4):
        w, h, bpp, rows = img
        img = h, w, bpp, [b"".join(rows[h - 1 - nx][y * bpp:(y + 1) * bpp] for nx in range(h)) for y in range(w)]
    return img


def zoom(img, n):
    if n == 1:
        return img
    w, h, bpp, rows = img
    out = []
    for r in rows:
        out += [b"".join(r[x * bpp:(x + 1) * bpp] * n for x in range(w))] * n
    return w * n, h * n, bpp, out


def side(a, b):
    """a | b on one RGB canvas, for before/after pairs."""
    def rgb(img):
        return [r if img[2] == 3 else b"".join(r[i:i + 3] for i in range(0, len(r), 4)) for r in img[3]]
    ra, rb, h = rgb(a), rgb(b), max(a[1], b[1])
    gap = b"\x40\x00\x40" * 4
    return a[0] + 4 + b[0], h, 3, [(ra[y] if y < a[1] else bytes(a[0] * 3)) + gap
                                   + (rb[y] if y < b[1] else bytes(b[0] * 3)) for y in range(h)]


def frame_no(path):
    m = re.search(r"(\d+)\D*$", os.path.basename(path))  # f000300.png -> 300
    return int(m[1]) if m else None


def collect(srcs, lo=None, hi=None):
    paths = []
    for s in [srcs] if isinstance(srcs, str) else srcs:
        paths += sorted(glob.glob(os.path.join(s, "f[0-9]*.png") if os.path.isdir(s) else s))
    if lo is not None or hi is not None:
        paths = [p for p in paths if frame_no(p) is not None
                 and (lo is None or frame_no(p) >= lo) and (hi is None or frame_no(p) <= hi)]
    return paths


def make(d, cols=4, div=None, limit=16, changed=0.0, out=None, lo=None, hi=None, box=None, scale=1, turn=0,
         compare=None, side_max=MAX_SIDE):
    """d: a directory, or a list of directories / PNG paths / globs. Writes sheet.png, sheet_2.png, ... so that no
    frame is dropped and no page is so large that the reader downscales it; returns the list of pages."""
    paths = collect(d, lo, hi)
    if not paths:
        raise SystemExit(f"no f<frame>.png matched {d}")
    if div is None:
        div = 1 if box or scale > 1 else 2  # a crop or zoom is for reading small text: never halve it again
    kept = select(paths, changed) if changed else [(p, read_png(p)) for p in paths]

    def view(img):
        return zoom(rotate(crop(img, *box) if box else img, turn), scale)
    imgs = []
    for p, img in kept:
        img = view(img)
        if compare:  # a directory (same-named frames) or one PNG to pair with every frame
            q = os.path.join(compare, os.path.basename(p)) if os.path.isdir(compare) else compare
            other = view(read_png(q)) if os.path.exists(q) else (img[0], img[1], 3, [bytes(img[0] * 3)] * img[1])
            img = side(img, other)
        imgs.append(img)
    w, h = max(i[0] for i in imgs) // div + 2, max(i[1] for i in imgs) // div + 2
    cols = max(1, min(cols, side_max // w, len(imgs)))
    per = max(1, min(limit, cols * max(1, side_max // h)))
    first = d if isinstance(d, str) else d[0]
    out = out or os.path.join(first if os.path.isdir(first) else os.path.dirname(paths[0]) or ".", "sheet.png")
    stem, ext = os.path.splitext(out)
    pages = []
    for k in range(0, len(imgs), per):
        page = out if k == 0 else f"{stem}_{k // per + 1}{ext}"
        sheet(imgs[k:k + per], cols, page, div)
        pages.append(page)
        print(page, "tiles (row-major):", " ".join(os.path.basename(p)[:-4] for p, _ in kept[k:k + per]))
    return pages


def _selftest():
    img = (2, 2, 3, [bytes([1] * 3 + [2] * 3), bytes([3] * 3 + [4] * 3)])  # pixels 1 2 / 3 4
    assert crop(img, 1, 0, 5, 5) == (1, 2, 3, [bytes([2] * 3), bytes([4] * 3)])
    assert rotate(img, 90)[3] == [bytes([3] * 3 + [1] * 3), bytes([4] * 3 + [2] * 3)]  # 3 1 / 4 2
    assert rotate(img, 360) == img and zoom(img, 1) == img
    z = zoom(img, 2)
    assert z[:2] == (4, 4) and z[3][1] == bytes([1] * 6 + [2] * 6)
    s = side(img, (1, 1, 4, [bytes([9, 9, 9, 255])]))
    assert s[:2] == (7, 2) and s[3][0].endswith(bytes([9] * 3)) and s[3][1].endswith(bytes(3))
    assert frame_no("x/f000300.png") == 300 and frame_no("final.png") is None
    import tempfile

    def png(path, w, h, depth, ct, raw, extra=b""):
        def chunk(t, b):
            return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
        open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ct, 0, 0, 0))
                               + extra + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        return chunk
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "g.png")
        png(p, 2, 1, 8, 0, b"\0\x10\x20")  # grey
        assert read_png(p) == (2, 1, 3, [bytes([16] * 3 + [32] * 3)])
        chunk = png(p, 1, 1, 8, 0, b"\0\0")
        png(p, 3, 1, 4, 3, b"\0\x12\x00", chunk(b"PLTE", bytes([0, 0, 0, 10, 20, 30, 40, 50, 60])))  # 4-bit palette
        assert read_png(p)[3] == [bytes([10, 20, 30, 40, 50, 60, 0, 0, 0])]
        for k in range(5):
            write_png(os.path.join(t, f"f{k:06d}.png"), 2, 2, [bytes(6)] * 2)
        pages = make(t, cols=2, limit=2)
        assert [os.path.basename(x) for x in pages] == ["sheet.png", "sheet_2.png", "sheet_3.png"]
        big = make(t, cols=4, limit=16, scale=600, out=os.path.join(t, "z.png"))  # 1200 px tiles: 1 per page
        assert len(big) == 5 and read_png(big[0])[:2] == (1202, 1202)
    print("selftest ok")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(_selftest())
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="+", help="directory, PNG files or a quoted glob")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--div", type=int, help="downscale factor (default 2; 1 with --crop/--zoom)")
    ap.add_argument("--max", type=int, default=16)
    ap.add_argument("--changed", type=float, default=0.0)
    ap.add_argument("--out")
    ap.add_argument("--from", dest="lo", type=int)
    ap.add_argument("--to", dest="hi", type=int)
    ap.add_argument("--crop", type=lambda s: tuple(int(v) for v in s.split(",")), help="x,y,w,h")
    ap.add_argument("--zoom", type=int, default=1)
    ap.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270))
    ap.add_argument("--compare", metavar="DIR2|PNG")
    a = ap.parse_args()
    make(a.src, a.cols, a.div, a.max, a.changed, a.out, a.lo, a.hi, a.crop, a.zoom, a.rotate, a.compare)
