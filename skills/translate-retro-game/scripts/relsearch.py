"""Relative search: find text in an unknown encoding by the differences between character codes.

    python -X utf8 relsearch.py ROM いのちをおとした [--width 1|2] [--be] [--order jis|gojuon|...]
    python -X utf8 relsearch.py ROM --values 5,3,9,9 [--width 2]      # raw code pattern (any base offset)
    python -X utf8 relsearch.py --selftest

Each word is tried under every order its letters fit (kana in JIS or gojuon order, with or without small kana;
latin a-z / A-Z). A hit prints the order, the file offset and the code of the first letter, so the table follows:
code(letter) = base + order.index(letter). Use a word of 5+ letters, with no repeated-letter-only runs, to cut noise.
"""
import argparse
import sys
from array import array

HIRA_JIS = "ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをん"
GOJUON = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
KATA = str.maketrans({chr(c): chr(c + 0x60) for c in range(0x3041, 0x3097)})
ORDERS = {
    "jis": HIRA_JIS, "gojuon": GOJUON, "gojuon_small": GOJUON + "ぁぃぅぇぉっゃゅょ",
    "kata_jis": HIRA_JIS.translate(KATA) + "ヴヵヶ", "kata_gojuon": GOJUON.translate(KATA),
    "kata_gojuon_small": (GOJUON + "ぁぃぅぇぉっゃゅょ").translate(KATA),
    "lower": "abcdefghijklmnopqrstuvwxyz", "upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
}


def find_pattern(data, values, width=1, be=False):
    """File offsets where `values` occur up to a constant offset (codes width bytes each). Yields (offset, base)."""
    mask = (1 << (8 * width)) - 1
    deltas = [(b - a) & mask for a, b in zip(values, values[1:])]
    code = "B" if width == 1 else "H"
    needle = array(code, deltas).tobytes()
    for align in range(width):
        n = (len(data) - align) // width
        vals = array(code, data[align:align + n * width])
        if be and width == 2:
            vals.byteswap()
        hay = array(code, ((b - a) & mask for a, b in zip(vals, vals[1:]))).tobytes()
        i = hay.find(needle)
        while i >= 0:
            if i % width == 0:
                k = i // width
                yield align + k * width, (vals[k] - values[0]) & mask
            i = hay.find(needle, i + 1)


def search(data, word, width=1, be=False, orders=None):
    for name in orders or ORDERS:
        order = ORDERS[name]
        if all(c in order for c in word):
            idx = [order.index(c) for c in word]
            for off, base in find_pattern(data, idx, width, be):
                yield name, off, base


def selftest():
    order = ORDERS["gojuon"]
    word = "いのちをおとす"
    enc = bytes(0x40 + order.index(c) for c in word)
    blob = b"\x00" * 100 + enc + b"\xff" * 10
    hits = list(search(blob, word, orders=["gojuon"]))
    assert hits == [("gojuon", 100, 0x40)], hits
    enc16 = b"".join((0x8000 + ORDERS["jis"].index(c)).to_bytes(2, "big") for c in "ひらがな")
    hits = list(search(b"\x01" * 7 + enc16, "ひらがな", width=2, be=True, orders=["jis"]))
    assert hits == [("jis", 7, 0x8000)], hits
    assert list(find_pattern(bytes([9, 1, 2, 3]), [10, 11, 12])) == [(1, 0xF7)]
    print("selftest ok")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("word", nargs="?")
    ap.add_argument("--values", help="comma-separated codes instead of a word")
    ap.add_argument("--width", type=int, choices=[1, 2], default=1)
    ap.add_argument("--be", action="store_true", help="16-bit codes are big-endian")
    ap.add_argument("--order", action="append", choices=ORDERS, help="limit to these orders (repeatable)")
    ap.add_argument("--max", type=int, default=50, help="stop after this many hits")
    a = ap.parse_args()
    if not a.word and not a.values:
        ap.error("give a WORD or --values")
    data = open(a.rom, "rb").read()
    if a.values:
        hits = (("values", o, b) for o, b in find_pattern(data, [int(v, 0) for v in a.values.split(",")], a.width, a.be))
    else:
        hits = search(data, a.word, a.width, a.be, a.order)
    n = 0
    for name, off, base in hits:
        span = len(a.values.split(",")) if a.values else len(a.word)
        print(f"{name:18s} @ {off:08X}  base={base:0{2 * a.width}X}  {data[off:off + span * a.width].hex(' ')}")
        n += 1
        if n >= a.max:
            print(f"... stopped at {a.max} hits (--max)")
            break
    print(f"{n} hits")
    sys.exit(0 if n else 1)


if __name__ == "__main__":
    main()
