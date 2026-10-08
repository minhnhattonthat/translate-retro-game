"""BPS patches without dependencies, plus the SNES header checksum fix.

    python bps.py make ORIG BUILT OUT.bps     # writes the patch, then re-applies it and checks the result
    python bps.py apply ORIG PATCH OUT        # what a player's patcher does (flips, RomPatcher.js, beat)
    python bps.py snes-checksum ROM [--out FILE]   # recompute $FFDC/$FFDE (HiROM) or $7FDC/$7FDE (LoROM)

The patch holds no original ROM data (bytes equal to the original are SourceRead, the rest TargetRead, long runs
of one byte TargetCopy). Use xdelta3 instead for disc images and >16 MiB files: `xdelta3 -e -s ORIG BUILT OUT`,
verify with `xdelta3 -d -s ORIG OUT check.bin` and compare hashes.
"""
import sys, zlib


def num(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def read_num(p, i):
    n, shift = 0, 1
    while True:
        x = p[i]
        i += 1
        n += (x & 0x7F) * shift
        if x & 0x80:
            return n, i
        shift <<= 7
        n += shift


def make(src, tgt):
    out = bytearray(b"BPS1" + num(len(src)) + num(len(tgt)) + num(0))
    lim, i, trel = min(len(src), len(tgt)), 0, 0

    def carry(a, b):
        if b > a:
            out.extend(num(((b - a - 1) << 2) | 1) + tgt[a:b])

    while i < len(tgt):
        same = i < lim and src[i] == tgt[i]
        j = i + 1
        while j < len(tgt) and (j < lim and src[j] == tgt[j]) == same:
            j += 1
        if same:
            out += num((j - i - 1) << 2)
        else:
            a = k = i
            while k < j:
                r = k + 1
                while r < j and tgt[r] == tgt[k]:
                    r += 1
                if r - k >= 8:  # a run: carry its first byte, TargetCopy the rest from it
                    carry(a, k + 1)
                    rel = k - trel
                    out += num(((r - k - 2) << 2) | 3) + num((rel << 1) if rel >= 0 else ((-rel << 1) | 1))
                    trel = r - 1
                    a = r
                k = r
            carry(a, j)
        i = j
    out += zlib.crc32(src).to_bytes(4, "little") + zlib.crc32(tgt).to_bytes(4, "little")
    return bytes(out + zlib.crc32(out).to_bytes(4, "little"))


def apply(src, p):
    if p[:4] != b"BPS1":
        raise ValueError("not a BPS patch")
    if zlib.crc32(p[:-4]) != int.from_bytes(p[-4:], "little"):
        raise ValueError("patch checksum mismatch (corrupt patch)")
    if zlib.crc32(src) != int.from_bytes(p[-12:-8], "little"):
        raise ValueError("source checksum mismatch: wrong base ROM (headered? different revision?)")
    i = 4
    slen, i = read_num(p, i)
    tlen, i = read_num(p, i)
    mlen, i = read_num(p, i)
    i += mlen
    out, srel, trel = bytearray(), 0, 0
    while i < len(p) - 12:
        d, i = read_num(p, i)
        cmd, n = d & 3, (d >> 2) + 1
        if cmd == 0:
            out += src[len(out):len(out) + n]
        elif cmd == 1:
            out += p[i:i + n]
            i += n
        else:
            o, i = read_num(p, i)
            o = -(o >> 1) if o & 1 else o >> 1
            if cmd == 2:
                srel += o
                out += src[srel:srel + n]
                srel += n
            else:
                trel += o
                for _ in range(n):  # byte by byte: TargetCopy may overlap what it is writing
                    out.append(out[trel])
                    trel += 1
    if len(out) != tlen or zlib.crc32(out) != int.from_bytes(p[-8:-4], "little"):
        raise ValueError("result checksum mismatch")
    return bytes(out)


def snes_checksum(rom):
    """Recompute the header checksum. Picks LoROM/HiROM by which header has a sane map-mode byte.
    ponytail: plain sum, correct for power-of-two sizes; 3/6 MB ROMs need the mirrored-sum rule."""
    rom = bytearray(rom)
    base = 0xFFB0 if len(rom) > 0xFFFF and (rom[0xFFD5] & 0xEF) in (0x21, 0x25, 0x31, 0x35) else 0x7FB0
    rom[base + 0x2C:base + 0x30] = b"\xff\xff\x00\x00"
    total = sum(rom) & 0xFFFF
    rom[base + 0x2C:base + 0x30] = (total ^ 0xFFFF).to_bytes(2, "little") + total.to_bytes(2, "little")
    return bytes(rom), total


def main(argv):
    if len(argv) >= 4 and argv[0] == "make":
        src, tgt = open(argv[1], "rb").read(), open(argv[2], "rb").read()
        p = make(src, tgt)
        assert apply(src, p) == tgt, "patch does not reproduce the build"
        open(argv[3], "wb").write(p)
        print(f"{argv[3]}: {len(p)} bytes, verified. base crc32 {zlib.crc32(src):08X} ({len(src)} bytes), "
              f"result crc32 {zlib.crc32(tgt):08X}")
    elif len(argv) == 4 and argv[0] == "apply":
        out = apply(open(argv[1], "rb").read(), open(argv[2], "rb").read())
        open(argv[3], "wb").write(out)
        print(f"{argv[3]}: crc32 {zlib.crc32(out):08X}")
    elif len(argv) >= 2 and argv[0] == "snes-checksum":
        rom, total = snes_checksum(open(argv[1], "rb").read())
        dst = argv[3] if len(argv) == 4 and argv[2] == "--out" else argv[1]
        open(dst, "wb").write(rom)
        print(f"{dst}: checksum {total:04X}")
    elif argv == ["--selftest"]:
        import random
        rnd = random.Random(1)
        src = bytes(rnd.randrange(256) for _ in range(5000))
        tgt = bytearray(src) + b"\xff" * 3000 + bytes(rnd.randrange(256) for _ in range(100))
        tgt[100:110] = b"English..."
        tgt[2000:2040] = b"\x00" * 40
        assert apply(src, make(src, bytes(tgt))) == bytes(tgt)
        assert apply(src, make(src, src[:4000])) == src[:4000]
        print("selftest ok")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
