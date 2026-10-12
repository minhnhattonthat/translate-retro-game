"""Find Japanese text still sitting in a built ROM/file: the "is anything left untranslated?" scan.

    python jp_left.py BUILT [--orig ORIG] (--sjis | --tbl jp.tbl [--rows] [--le16]) [--min 4] [--range 80000-BFFFF ...]
                      [--limit 200] [--gba-ptrs | --slots FILE] [--known FILE]

--sjis       Shift-JIS games (most GBA/NDS/PS1): runs of kana/kanji double-byte codes.
--tbl FILE   custom encodings (most SNES): Thingy table "XX=char" / "XXYY=char"; entries whose char is kana/kanji
             count as Japanese. Longest match wins, so multi-byte entries work.
--rows       (with --tbl) row-format table: "0A0=りるれろ..." maps consecutive codes 0A0, 0A1, ... to its chars.
--le16       (with --tbl) codes are 16-bit little-endian in the data ("0A0=り" matches bytes A0 00), at even offsets.
--orig ORIG  report only runs whose bytes are unchanged from the original (= text you never touched). Without it,
             every Japanese-looking run is reported, including ones you meant to keep (credits in kanji).
--range      limit to hex offset ranges (text banks); graphics and code produce false runs, so narrow it once
             you know where text lives.
--halfwidth  (with --sjis) also count half-width katakana bytes A6-DF (ｸﾚｽ): debug menus, names, system text.
             Noisier, because single bytes in that range are common in data.
--gba-ptrs   keep only runs that some aligned 0x08xxxxxx pointer in the ROM points into. Relocating text leaves
             the old Japanese behind, unreferenced: on one game this cut ~1,950 runs to the few the game can still
             show, including broken pointers that land mid-line. Each run prints the first pointer slot that
             reaches it ("<- 0x0123A8 +2" = two more). Old pointer arrays your build no longer uses still count,
             so after relocation pass --slots (exact) or list the confirmed-dead runs in --known.
--slots FILE pointers the game really uses, one per line: "SLOT" (hex file offset of a 4-byte GBA pointer) or
             "SLOT TARGET" (target file offset given, for any platform's pointer format). Keeps only runs these
             reach; replaces the --gba-ptrs word scan. Dump it from your extractor's pointer list.
--known FILE runs to stop reporting, one hex offset per line (anything after it is a note): Japanese you keep on
             purpose, kana order tables, dead arrays you checked. A run is dropped if a listed offset falls in it.
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


def gba_ptrs(b):
    """(target, slot) for every aligned little-endian 0x08xxxxxx word in the ROM, sorted by target."""
    hi = 0x08000000 + len(b)
    return sorted((w - 0x08000000, i * 4) for i, (w,) in enumerate(struct.iter_unpack("<I", b[:len(b) & ~3]))
                  if 0x08000000 <= w < hi)


def hex_lines(path):
    """First hex token(s) of each non-comment line."""
    for line in open(path, encoding="utf-8-sig"):
        tok = line.split("#")[0].replace(",", " ").split()
        if tok:
            yield [int(t, 16) for t in tok[:2] if all(c in "0123456789abcdefABCDEFxX" for c in t)]


def load_slots(path, b):
    return sorted((t[1], t[0]) if len(t) > 1 else (int.from_bytes(b[t[0]:t[0] + 4], "little") - 0x08000000, t[0])
                  for t in hex_lines(path) if t)


def refs(ptrs, s, e):
    """Slots of the pointers that land in [s, e)."""
    k, out = bisect.bisect_left(ptrs, (s, -1)), []
    while k < len(ptrs) and ptrs[k][0] < e:
        out.append(ptrs[k][1])
        k += 1
    return out


def pointed(offsets, s, e):
    k = bisect.bisect_left(offsets, s)
    return k < len(offsets) and offsets[k] < e


def load_tbl(path, rows=False, le16=False):
    entries = {}
    for line in open(path, encoding="utf-8-sig"):
        line = line.rstrip("\r\n")
        if "=" not in line or line.startswith(("#", ";", "/", "*")):
            continue
        hexpart, ch = line.split("=", 1)
        try:
            base = int(hexpart, 16)
        except ValueError:
            continue
        width = 2 if le16 else (len(hexpart.strip()) + 1) // 2
        for i, c in enumerate(ch if rows else [ch]):
            if JP.search(c):
                entries[(base + i).to_bytes(width, "little" if le16 else "big")] = c
    return entries, max((len(k) for k in entries), default=1)


def tbl_char(entries, longest, even=False):
    def f(b, i):
        if even and i & 1:  # shortcut: 16-bit text at odd offsets is missed; add an --odd pass if a game needs it
            return 0
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
    ap.add_argument("--slots")
    ap.add_argument("--known")
    ap.add_argument("--rows", action="store_true")
    ap.add_argument("--le16", action="store_true")
    a = ap.parse_args(argv)
    b = open(a.built, "rb").read()
    orig = open(a.orig, "rb").read() if a.orig else None
    ptrs = load_slots(a.slots, b) if a.slots else gba_ptrs(b) if a.gba_ptrs else None
    known = sorted(t[0] for t in hex_lines(a.known) if t) if a.known else []
    if a.sjis:
        char_at = sjis_char_hw if a.halfwidth else sjis_char
        decode = lambda s: s.decode("shift_jis", "replace")  # noqa: E731
    else:
        entries, longest = load_tbl(a.tbl, a.rows, a.le16)
        char_at = tbl_char(entries, longest, a.le16)

        def decode(s):
            out, i = [], 0
            while i < len(s):
                n = char_at(s, i) or 1
                out.append(entries.get(bytes(s[i:i + n]), "."))
                i += n
            return "".join(out)
    ranges = [tuple(int(x, 16) for x in r.split("-")) for r in a.range] or [(0, len(b) - 1)]
    found, skipped = [], 0
    for lo, hi in ranges:
        for s, e in scan(b, char_at, lo, min(hi + 1, len(b)), a.min):
            if orig is not None and orig[s:e] != b[s:e]:
                continue
            if not a.kanji_runs and not text_like(decode(b[s:e])):
                continue
            slots = refs(ptrs, s, e) if ptrs is not None else None
            if slots == []:
                continue
            if pointed(known, s, e):
                skipped += 1
                continue
            found.append((s, e, slots))
    for s, e, slots in found[:a.limit]:
        via = f"  <- 0x{slots[0]:06X}" + (f" +{len(slots) - 1}" if len(slots) > 1 else "") if slots else ""
        print(f"0x{s:06X} {e - s:4d}B  {decode(b[s:e])}{via}")
    total = sum(e - s for s, e, _ in found)
    print(f"{len(found)} Japanese runs, {total} bytes" + (" (unchanged from original)" if orig else "")
          + (f"; {skipped} known runs skipped" if skipped else ""))
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
    p = gba_ptrs(rom)
    assert p == [(0x10, 0)] and refs(p, 0x0E, 0x12) == [0] and refs(p, 0x11, 0x14) == []
    assert pointed([5], 3, 6) and not pointed([5], 6, 9)
    import os, tempfile
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "t.tbl"), "w", encoding="utf-8").write("# rows\n0A0=りるAれ\n")
        e, n = load_tbl(os.path.join(d, "t.tbl"), rows=True, le16=True)
        assert e == {b"\xa0\x00": "り", b"\xa1\x00": "る", b"\xa3\x00": "れ"} and n == 2
        f = tbl_char(e, n, even=True)
        data = b"\x00" + b"\xa0\x00\xa1\x00\xa3\x00\xa0\x00"
        assert scan(data, f, 0, len(data), 4) == [] and scan(b"\x00\x00" + data[1:], f, 0, 10, 4) == [(2, 10)]
        open(os.path.join(d, "s.txt"), "w").write("0x0  # real\n8 12\n")
        assert load_slots(os.path.join(d, "s.txt"), rom) == [(0x10, 0), (0x12, 8)]
    print("selftest ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # --help and results hold Japanese; Windows consoles default to cp1252
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit(main())
