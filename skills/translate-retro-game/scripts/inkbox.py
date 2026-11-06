"""Is the text centred in its box? Measures ink margins from a screenshot, so alignment isn't judged by eye.

    python inkbox.py SHOT.png x,y,w,h [x,y,w,h ...] [--tol 2] [--vert] [--diff 40] [--bg R,G,B]

Each rect is the inside of one selection box or bubble: crop inside its border. Ink is any pixel more than --diff
from the background in some channel; the background is the rect's most common colour unless --bg gives it.
Prints the margins of each rect. Exit 1 if left and right margins differ by more than --tol px (with --vert, top and
bottom too), 2 if a rect holds no ink. Use a higher --diff on gradient windows. Check text meant to be centred only:
compare with the original's shot when unsure.
"""
import argparse, collections, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sheet import read_png, write_png  # noqa: E402


def margins(rows, bpp, rect, diff=40, bg=None):
    """(left, right, top, bottom) empty pixels around the ink in rect, or None if it holds no ink."""
    x, y, w, h = rect
    px = [[tuple(rows[y + j][(x + i) * bpp:(x + i) * bpp + 3]) for i in range(w)] for j in range(h)]
    bg = bg or collections.Counter(p for r in px for p in r).most_common(1)[0][0]
    ink = [(i, j) for j, r in enumerate(px) for i, p in enumerate(r) if max(abs(a - b) for a, b in zip(p, bg)) > diff]
    if not ink:
        return None
    xs, ys = [i for i, _ in ink], [j for _, j in ink]
    return min(xs), w - 1 - max(xs), min(ys), h - 1 - max(ys)


def check(path, rects, tol=2, vert=False, diff=40, bg=None):
    w, h, bpp, rows = read_png(path)
    rc = 0
    for r in rects:
        if r[0] < 0 or r[1] < 0 or r[0] + r[2] > w or r[1] + r[3] > h:
            raise SystemExit(f"{r} is outside the {w}x{h} image")
        m = margins(rows, bpp, r, diff, bg)
        if m is None:
            print(f"{r}: NO INK")
            rc = max(rc, 2)
            continue
        off = abs(m[0] - m[1]) > tol or (vert and abs(m[2] - m[3]) > tol)
        print(f"{r}: left {m[0]} right {m[1]} top {m[2]} bottom {m[3]}{'  OFF-CENTRE' if off else ''}")
        rc = max(rc, int(off))
    return rc


def _selftest():
    import tempfile
    rows = [bytearray(b"\x00\x00\x80" * 20) for _ in range(10)]
    for j in range(3, 6):
        for i in range(5, 12):  # ink at x 5..11 of 20: left 5, right 8
            rows[j][i * 3:i * 3 + 3] = b"\xff\xff\xff"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.png")
        write_png(p, 20, 10, [bytes(r) for r in rows])
        assert check(p, [(0, 0, 20, 10)]) == 1
        assert check(p, [(0, 0, 20, 10)], tol=3) == 0
        assert check(p, [(0, 0, 17, 10)]) == 0  # left 5, right 5
        assert check(p, [(0, 0, 17, 10)], vert=True) == 0  # top 3, bottom 4
        assert check(p, [(0, 0, 17, 10)], tol=0, vert=True) == 1
        assert check(p, [(14, 0, 5, 10)]) == 2  # no ink here
        assert check(p, [(0, 0, 20, 10)], bg=(0, 0, 128), tol=3) == 0
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("png")
    ap.add_argument("rects", nargs="+", help="x,y,w,h inside each box")
    ap.add_argument("--tol", type=int, default=2, help="allowed margin difference in px; an odd gap always leaves 1")
    ap.add_argument("--vert", action="store_true", help="also check top against bottom")
    ap.add_argument("--diff", type=int, default=40)
    ap.add_argument("--bg", help="background R,G,B")
    a = ap.parse_args()
    rects = [tuple(int(v) for v in r.split(",")) for r in a.rects]
    bg = tuple(int(v) for v in a.bg.split(",")) if a.bg else None
    return check(a.png, rects, a.tol, a.vert, a.diff, bg)


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit(main())
