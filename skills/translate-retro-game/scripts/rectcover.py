"""Does each text rect cover all of the original's text? Finds strokes that start inside a rect and run past its edge,
so a clear-and-redraw doesn't leave a dakuten, a tail or a glyph's edge behind (they show as stray pixels in game).

    python rectcover.py ORIGINAL.png x,y,w,h [x,y,w,h ...] [--pad 4] [--diff 0]

Run it on the original, Japanese image (a TIM or tile sheet exported to PNG, or a screenshot), never the English one.
Per row, the background is the commonest value of the --pad margin beside the rect (rows above and below: the whole
widened row); ink is any pixel more than --diff
from it in some channel (0 for indexed art exported exactly; 30-40 for screenshots). Ink 8-connected to ink inside the
rect counts as the rect's text. Prints, for each rect, how far its text runs past each edge and the rect that covers
it. Exit 1 if any rect needs to grow. A stroke that reaches the widened window's border is the art's own (a frame, a
character) and is reported as "joins art" without failing: check those by eye.

Library: spill(px, rect, pad=4, diff=0) on a 2D list of values (palette indices, or RGB tuples) gives
(left, right, top, bottom, joins_art), each side in pixels past the rect.
"""
import argparse, collections, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _far(a, b, diff):
    if isinstance(a, tuple):
        return max(abs(p - q) for p, q in zip(a, b)) > diff
    return abs(a - b) > diff


def spill(px, rect, pad=4, diff=0):
    """(left, right, top, bottom, joins_art): pixels the rect's text runs past each side of rect."""
    x, y, w, h = rect
    H, W = len(px), len(px[0])
    x0, y0, x1, y1 = max(x - pad, 0), max(y - pad, 0), min(x + w + pad, W), min(y + h + pad, H)
    ink = set()
    for j in range(y0, y1):
        # the margin beside the rect, not the row through it: long strokes (ー) can outnumber the background there
        row = px[j][x0:x] + px[j][x + w:x1] if y <= j < y + h and (x > x0 or x + w < x1) else px[j][x0:x1]
        bg = collections.Counter(row).most_common(1)[0][0]
        ink.update((i, j) for i in range(x0, x1) if _far(px[j][i], bg, diff))
    seen = {p for p in ink if x <= p[0] < x + w and y <= p[1] < y + h}
    todo = list(seen)
    while todo:
        i, j = todo.pop()
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                q = (i + di, j + dj)
                if q in ink and q not in seen:
                    seen.add(q)
                    todo.append(q)
    if not seen:
        return 0, 0, 0, 0, False
    xs, ys = [p[0] for p in seen], [p[1] for p in seen]
    outside = [p for p in seen if not (x <= p[0] < x + w and y <= p[1] < y + h)]
    art = bool(pad) and any(p[0] in (x0, x1 - 1) or p[1] in (y0, y1 - 1) for p in outside)
    return max(x - min(xs), 0), max(max(xs) - (x + w - 1), 0), max(y - min(ys), 0), max(max(ys) - (y + h - 1), 0), art


def check(px, rects, pad=4, diff=0, out=print):
    """Exit code: 1 if any rect's text spills past it (art joins excluded)."""
    rc = 0
    for r in rects:
        l, rt, t, b, art = spill(px, r, pad, diff)
        x, y, w, h = r
        if art:
            out(f"{r}: joins art (a stroke reaches {pad} px past the rect): check by eye")
        elif l or rt or t or b:
            out(f"{r}: text past left {l}, right {rt}, top {t}, bottom {b}; covering rect "
                f"{x - l},{y - t},{w + l + rt},{h + t + b}")
            rc = 1
        else:
            out(f"{r}: ok")
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("png")
    ap.add_argument("rects", nargs="+", help="x,y,w,h")
    ap.add_argument("--pad", type=int, default=4)
    ap.add_argument("--diff", type=int, default=0)
    a = ap.parse_args()
    from sheet import read_png
    w, h, bpp, rows = read_png(a.png)
    px = [[tuple(r[i * bpp:i * bpp + 3]) for i in range(w)] for r in rows]
    rects = [tuple(int(v) for v in s.split(",")) for s in a.rects]
    for r in rects:
        if r[0] < 0 or r[1] < 0 or r[0] + r[2] > w or r[1] + r[3] > h:
            raise SystemExit(f"{r} is outside the {w}x{h} image")
    sys.exit(check(px, rects, a.pad, a.diff))


if __name__ == "__main__":
    main()
