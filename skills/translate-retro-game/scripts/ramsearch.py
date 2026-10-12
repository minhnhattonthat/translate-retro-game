"""Cheat-search style RAM narrowing over dumps (probes/ramdump.lua, L.dump_ram): find HP, money, map id, flags.

    python ramsearch.py DUMP1 OP DUMP2 [OP DUMP3 ..] [--width 1|2|4] [--base 0x7E0000] [--max 40]

OP compares each address between the dumps on either side of it:
  same  changed  inc  dec   value unchanged / changed / went up / went down
  +N  -N                    went up / down by exactly N
  =N                        the right-hand dump holds N (decimal or 0x..)
Every OP narrows the candidates left by the previous ones. Example: HP 30, take a hit, HP 27:
  ramsearch.py ram_000600.bin dec ram_000900.bin =27 ram_000900.bin
--base labels addresses (SNES WRAM 0x7E0000, GBA 0x02000000; PS1 0x80000000, NDS 0x02000000). Values are
little-endian. Then confirm a hit by poking it from Lua and watching the screen change.
"""
import argparse, sys

TESTS = {"same": lambda a, b, n: a == b, "changed": lambda a, b, n: a != b, "inc": lambda a, b, n: b > a,
         "dec": lambda a, b, n: b < a, "+": lambda a, b, n: b - a == n, "-": lambda a, b, n: a - b == n,
         "=": lambda a, b, n: b == n}


def parse_op(op):
    if op in TESTS:
        return TESTS[op], 0
    if op[:1] in "+-=" and len(op) > 1:
        return TESTS[op[0]], int(op[1:], 0)
    sys.exit(f"bad OP {op!r}: same changed inc dec +N -N =N")


def search(dumps, ops, width=1):
    """dumps: list of bytes; ops: list of op strings between them. Returns {offset: [values per dump]}."""
    size = min(len(d) for d in dumps) // width * width
    vals = [[int.from_bytes(d[i:i + width], "little") for i in range(0, size, width)] for d in dumps]
    keep = range(len(vals[0]))
    for k, op in enumerate(ops):
        test, n = parse_op(op)
        a, b = vals[k], vals[k + 1]
        keep = [i for i in keep if test(a[i], b[i], n)]
    return {i * width: [v[i] for v in vals] for i in keep}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seq", nargs="*", help="DUMP OP DUMP [OP DUMP ..]")
    ap.add_argument("--width", type=int, default=1, choices=(1, 2, 4))
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0)
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if len(a.seq) < 3 or len(a.seq) % 2 == 0:
        ap.error("give DUMP OP DUMP [OP DUMP ..]")
    dumps = [open(p, "rb").read() for p in a.seq[0::2]]
    hits = search(dumps, a.seq[1::2], a.width)
    print(f"{len(hits)} candidates")
    for off, vs in list(hits.items())[:a.max]:
        print(f"{a.base + off:08X}  " + " ".join(str(v) for v in vs))


def _selftest():
    d1, d2, d3 = bytes([30, 5, 9, 1]), bytes([27, 5, 8, 1]), bytes([27, 5, 8, 0])
    assert list(search([d1, d2], ["dec"])) == [0, 2]
    assert list(search([d1, d2, d3], ["dec", "same"])) == [0, 2]
    assert list(search([d1, d2], ["-3"])) == [0]
    assert list(search([d1, d2], ["=27"])) == [0]
    assert list(search([d2, d3], ["changed"])) == [3]
    assert search([bytes([1, 1, 2, 1])] * 2, ["=0x101"], 2) == {0: [257, 257]}
    print("ramsearch selftest ok")


if __name__ == "__main__":
    main()
