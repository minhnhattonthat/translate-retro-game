"""Find Japanese text still sitting in a built ROM/file: the "is anything left untranslated?" scan.

    python jp_left.py BUILT [--orig ORIG] (--sjis | --tbl jp.tbl) [--min 4] [--range 80000-BFFFF ...] [--limit 200]

--sjis       Shift-JIS games (most GBA/NDS/PS1): runs of kana/kanji double-byte codes.
--tbl FILE   custom encodings (most SNES): Thingy table "XX=char" / "XXYY=char"; entries whose char is kana/kanji
             count as Japanese. Longest match wins, so multi-byte entries work.
--orig ORIG  report only runs whose bytes are unchanged from the original (= text you never touched). Without it,
             every Japanese-looking run is reported, including ones you meant to keep (credits in kanji).
--range      limit to hex offset ranges (text banks); graphics and code produce false runs, so narrow it once
             you know where text lives.
--halfwidth  (with --sjis) also count half-width katakana bytes A6-DF (ｸﾚｽ): debug menus, names, system text.
             Noisier, because single bytes in that range are common in data.
--gba-ptrs   keep only runs that some aligned 0x08xxxxxx pointer in the ROM points into. Relocating text leaves
             the old Japanese behind, unreferenced: on one game this cut ~1,950 runs to the few the game can still
             show, including broken pointers that land mid-line.
Exit 1 when anything is found, 0 when clean, so it can gate a release.
"""
import argparse, bisect, re, struct, sys

JP = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]")
KANA = re.compile(r"[぀-ヿｦ-ﾟ]")
HALF = re.compile(r"[ｦ-ﾟ]")
KANJI = re.compile(r"[㐀-鿿]")


def text_like(s):
    """Heuristic: does a decoded run read like text rather than data that happens to decode?
    Prose is >= ~1/4 kana (data decodes to rare kanji), is not one or two chars repeated, and is not a run of
    consecutive code points (font maps, kana order tables)."""
    if "�" in s or len(set(s)) * 2 < len(s):
        return False
    steps = sum(0 < abs(ord(b) - ord(a)) <= 2 for a, b in zip(s, s[1:]))
    if steps * 2 > len(s):
        return False
    if HALF.search(s) and KANJI.search(s):  # real half-width text never mixes in kanji; data bytes do
        return False
    return len(KANA.findall(s)) * 4 >= len(JP.findall(s))


def sjis_char(b, i):
    """Length of the Japanese SJIS char at i (2), or 0."""
    if i + 1 >= len(b):
        return 0
    c = b[i] << 8 | b[i + 1]
    kana = 0x829F <= c <= 0x82F1 or 0x8340 <= c <= 0x8396
    kanji = (0x889F <= c <= 0x9FFC or 0xE040 <= c <= 0xEAA4) and 0x40 <= b[i + 1] <= 0xFC and b[i + 1] != 0x7F
    return 2 if kana or kanji else 0


def sjis_char_hw(b, i):
    return sjis_char(b, i) or (1 if i < len(b) and 0xA6 <= b[i] <= 0xDF else 0)


def gba_targets(b):
    """Sorted file offsets that aligned little-endian 0x08xxxxxx words in the ROM point at."""
    hi = 0x08000000 + len(b)
    return sorted({w - 0x08000000 for (w,) in struct.iter_unpack("<I", b[:len(b) & ~3]) if 0x08000000 <= w < hi})


def pointed(targets, s, e):
    k = bisect.bisect_left(targets, s)
    return k < len(targets) and targets[k] < e


def load_tbl(path):
    entries = {}
    for line in open(path, encoding="utf-8-sig"):
        line = line.rstrip("\r\n")
        if "=" not in line or line.startswith(("#", ";", "/", "*")):
            continue
        hexpart, ch = line.split("=", 1)
        try:
            key = bytes.fromhex(hexpart)
        except ValueError:
            continue
        if JP.search(ch):
            entries[key] = ch
    return entries, max((len(k) for k in entries), default=1)


def tbl_char(entries, longest):
    def f(b, i):
        for n in range(longest, 0, -1):
            ch = entries.get(bytes(b[i:i + n]))
            if ch:
                return n
        return 0
    return f


def scan(b, char_at, lo, hi, min_chars):
    runs, i = [], lo
    while i < hi:
        n = char_at(b, i)
        if not n:
            i += 1
            continue
        start, count = i, 0
        while i < hi and n:
            i += n
            count += 1
            n = char_at(b, i)
        if count >= min_chars:
            runs.append((start, i))
    return runs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("built")
    ap.add_argument("--orig")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sjis", action="store_true")
    g.add_argument("--tbl")
    ap.add_argument("--min", type=int, default=4, help="minimum run length in characters")
    ap.add_argument("--range", action="append", default=[])
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--kanji-runs", action="store_true", help="also report kana-free runs (names, kanji lists)")
    ap.add_argument("--halfwidth", action="store_true")
    ap.add_argument("--gba-ptrs", action="store_true")
    a = ap.parse_args(argv)
    b = open(a.built, "rb").read()
    orig = open(a.orig, "rb").read() if a.orig else None
    targets = gba_targets(b) if a.gba_ptrs else None
    if a.sjis:
        char_at = sjis_char_hw if a.halfwidth else sjis_char
        decode = lambda s: s.decode("shift_jis", "replace")  # noqa: E731
    else:
        entries, longest = load_tbl(a.tbl)
        char_at = tbl_char(entries, longest)

        def decode(s):
            out, i = [], 0
            while i < len(s):
                n = char_at(s, i) or 1
                out.append(entries.get(bytes(s[i:i + n]), "."))
                i += n
            return "".join(out)
    ranges = [tuple(int(x, 16) for x in r.split("-")) for r in a.range] or [(0, len(b) - 1)]
    found = []
    for lo, hi in ranges:
        for s, e in scan(b, char_at, lo, min(hi + 1, len(b)), a.min):
            if orig is not None and orig[s:e] != b[s:e]:
                continue
            if not a.kanji_runs and not text_like(decode(b[s:e])):
                continue
            if targets is not None and not pointed(targets, s, e):
                continue
            found.append((s, e))
    for s, e in found[:a.limit]:
        print(f"0x{s:06X} {e - s:4d}B  {decode(b[s:e])}")
    total = sum(e - s for s, e in found)
    print(f"{len(found)} Japanese runs, {total} bytes" + (" (unchanged from original)" if orig else ""))
    return 1 if found else 0


def _selftest():
    sj = "こんにちは".encode("shift_jis")
    blob = b"\x00\x01" + sj + b"\x00" + "Hello".encode() + b"\x00" + "少し".encode("shift_jis")
    assert scan(blob, sjis_char, 0, len(blob), 4) == [(2, 12)]
    assert scan(blob, sjis_char, 0, len(blob), 2) == [(2, 12), (19, 23)]
    entries = {b"\x10": "あ", b"\x11": "い", b"\xf0\x01": "漢"}
    f = tbl_char(entries, 2)
    data = b"\x41\x10\x11\xf0\x01\x10\x42"
    assert scan(data, f, 0, len(data), 4) == [(1, 6)]
    hw = b"\x00*" + "ｸﾚｽﾀｰ".encode("shift_jis") + b"\x00"
    assert scan(hw, sjis_char, 0, len(hw), 4) == []
    assert scan(hw, sjis_char_hw, 0, len(hw), 4) == [(2, 7)]
    rom = struct.pack("<II", 0x08000010, 0x08000099) + bytes(8) + b"text"
    t = gba_targets(rom)
    assert t == [0x10] and pointed(t, 0x0E, 0x12) and not pointed(t, 0x11, 0x14)
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit(main())
