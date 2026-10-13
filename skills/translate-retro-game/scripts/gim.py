"""PSP GIM (MIG.00.1PSP) reader/writer for 4/8-bit indexed and 16/32-bit images.
Library: parse(bytes) -> list of Image(w,h,fmt,swz,pix_off,pal) ; to_rgba(img,data) ; replace(data, idx, rgba_rows)
usage: gim.py FILE.gim [OUT.png]   (prints info; writes PNG with PIL)"""
import struct, sys

FMT = {0: 'rgb565', 1: 'rgba5551', 2: 'rgba4444', 3: 'rgba8888', 4: 'idx4', 5: 'idx8', 6: 'idx16', 7: 'idx32',
       0x40: 'dxt1', 0x41: 'dxt3', 0x42: 'dxt5'}
BPP = {0: 16, 1: 16, 2: 16, 3: 32, 4: 4, 5: 8, 6: 16, 7: 32}

class Img:
    pass

def walk(d, p, end, out, ctx):
    while p < end:
        t, _, sz, nx, off = struct.unpack_from('<HHIII', d, p)
        if sz == 0: break
        if t in (2, 3): walk(d, p + off, p + sz, out, ctx)
        elif t == 4:
            b = p + off
            hs, _, fmt, order, w, h, bpp, pa, ha = struct.unpack_from('<HHHHHHHHH', d, b)
            idx_start, pix_start, pix_end = struct.unpack_from('<III', d, b + 0x18)
            i = Img(); i.w, i.h, i.fmt, i.swz, i.bpp = w, h, fmt, order, BPP.get(fmt)
            i.pix = b + pix_start; i.pix_end = b + pix_end; i.block = p; i.pal = None
            ctx.append(i); out.append(i)
        elif t == 5:
            b = p + off
            hs, _, fmt, order, w, h = struct.unpack_from('<HHHHHH', d, b)
            idx_start, pix_start, pix_end = struct.unpack_from('<III', d, b + 0x18)
            pal = (fmt, w, h, b + pix_start)
            if ctx: ctx[-1].pal = pal
        p += sz

def parse(d):
    assert d[:11] == b'MIG.00.1PSP'
    out = []; walk(d, 16, len(d), out, [])
    return out

def unswizzle(raw, rowbytes, h):
    """PSP swizzle: blocks of 16 bytes x 8 rows, left to right, top to bottom."""
    out = bytearray(rowbytes * h); bw = rowbytes // 16; i = 0
    for by in range(0, h, 8):
        for bx in range(bw):
            for y in range(8):
                o = (by + y) * rowbytes + bx * 16
                out[o:o + 16] = raw[i:i + 16]; i += 16
    return bytes(out)

def swizzle(lin, rowbytes, h):
    out = bytearray(len(lin)); bw = rowbytes // 16; i = 0
    for by in range(0, h, 8):
        for bx in range(bw):
            for y in range(8):
                o = (by + y) * rowbytes + bx * 16
                out[i:i + 16] = lin[o:o + 16]; i += 16
    return bytes(out)

def conv(fmt, v):
    if fmt == 0: return ((v & 31) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v >> 11) * 255 // 31, 255)
    if fmt == 1: return ((v & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v >> 10 & 31) * 255 // 31, 255 if v >> 15 else 0)
    if fmt == 2: return ((v & 15) * 17, (v >> 4 & 15) * 17, (v >> 8 & 15) * 17, (v >> 12) * 17)
    return (v & 255, v >> 8 & 255, v >> 16 & 255, v >> 24)

def palette(d, img):
    fmt, n, _, off = img.pal
    if fmt == 3: return [tuple(d[off + 4 * i:off + 4 * i + 4]) for i in range(n)]
    return [conv(fmt, struct.unpack_from('<H', d, off + 2 * i)[0]) for i in range(n)]

def to_rgba(d, img):
    """-> (w, h, [bytes RGBA row,...]) ; the stored pitch is rounded up to 16 bytes."""
    bits = img.bpp; rowb = (img.w * bits // 8 + 15) // 16 * 16
    h = (img.h + 7) // 8 * 8 if img.swz else img.h
    raw = d[img.pix:img.pix + rowb * h]
    if img.swz: raw = unswizzle(raw, rowb, h)
    pal = palette(d, img) if img.pal else None
    rows = []
    for y in range(img.h):
        r = raw[y * rowb:(y + 1) * rowb]; line = bytearray()
        for x in range(img.w):
            if img.fmt == 4: v = r[x >> 1] >> (4 * (x & 1)) & 15; line += bytes(pal[v])
            elif img.fmt == 5: line += bytes(pal[r[x]])
            elif img.fmt in (0, 1, 2): line += bytes(conv(img.fmt, r[2 * x] | r[2 * x + 1] << 8))
            elif img.fmt == 3: line += r[4 * x:4 * x + 4]
            else: raise NotImplementedError(FMT.get(img.fmt, img.fmt))
        rows.append(bytes(line))
    return img.w, img.h, rows

def _nearest(pal, px, cache):
    r = cache.get(px)
    if r is None:
        a = px[3]; best = None
        for i, c in enumerate(pal):
            # alpha-weighted colour distance: invisible pixels only need to match alpha
            wgt = (a + c[3]) / 510
            d = wgt * sum((x - y) ** 2 for x, y in zip(px[:3], c[:3])) + 3 * (a - c[3]) ** 2
            if best is None or d < best[0]: best = (d, i)
        r = cache[px] = best[1]
    return r

def quantize(rows, n):
    """Median-cut palette of at most n RGBA entries (uses Pillow when available)."""
    from PIL import Image
    w = len(rows[0]) // 4; h = len(rows)
    im = Image.frombytes('RGBA', (w, h), b''.join(rows)).quantize(colors=n, method=Image.Quantize.FASTOCTREE)
    pal = im.getpalette()[:3 * n]; pal += [0] * (3 * n - len(pal))
    # FASTOCTREE on RGBA keeps alpha in the palette only through convert; rebuild per-index alpha as the mean of members
    idx = list(im.getdata()); src = b''.join(rows); acc = [[0, 0] for _ in range(n)]
    for k, i in enumerate(idx): acc[i][0] += src[4 * k + 3]; acc[i][1] += 1
    return [(pal[3 * i], pal[3 * i + 1], pal[3 * i + 2], acc[i][0] // acc[i][1] if acc[i][1] else 0) for i in range(n)]

def encode(d, img, rows, repalette=None):
    """Return GIM bytes (same length as d) with the image data replaced by rows (RGBA, same w/h as the original).
    Indexed images keep their palette unless repalette is True (or None: only when the original palette fits badly)."""
    out = bytearray(d); w, h = img.w, img.h
    rowb = (w * img.bpp // 8 + 15) // 16 * 16; hh = (h + 7) // 8 * 8 if img.swz else h
    lin = bytearray(rowb * hh)
    if img.fmt in (4, 5):
        pal = palette(d, img); n = len(pal); cache = {}
        if repalette is None:
            err = 0; px = set()
            for r in rows:
                for x in range(w): px.add(tuple(r[4 * x:4 * x + 4]))
            for q in px:
                c = pal[_nearest(pal, q, cache)]; err = max(err, abs(q[3] - c[3]) + (sum(abs(a - b) for a, b in zip(q[:3], c[:3])) if q[3] > 16 else 0))
            repalette = err > 48
        if repalette:
            pal = quantize(rows, n); cache = {}
            fmt, cnt, _, off = img.pal
            for i, c in enumerate(pal):
                if fmt == 3: out[off + 4 * i:off + 4 * i + 4] = bytes(c)
                else: raise NotImplementedError('palette format %d' % fmt)
        for y in range(h):
            r = rows[y]
            for x in range(w):
                i = _nearest(pal, tuple(r[4 * x:4 * x + 4]), cache)
                if img.fmt == 5: lin[y * rowb + x] = i
                else: lin[y * rowb + (x >> 1)] |= i << (4 * (x & 1))
    elif img.fmt == 3:
        for y in range(h): lin[y * rowb:y * rowb + 4 * w] = rows[y]
    else: raise NotImplementedError(FMT.get(img.fmt, img.fmt))
    raw = swizzle(bytes(lin), rowb, hh) if img.swz else bytes(lin)
    out[img.pix:img.pix + len(raw)] = raw
    return bytes(out)

def save_png(path, w, h, rows):
    from PIL import Image
    Image.frombytes('RGBA', (w, h), b''.join(rows)).save(path)

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    for i, im in enumerate(parse(d)):
        print(i, im.w, im.h, FMT.get(im.fmt, im.fmt), 'swz' if im.swz else 'lin', 'pal' if im.pal else '')
        if len(sys.argv) > 2: save_png(sys.argv[2], *to_rgba(d, im))
