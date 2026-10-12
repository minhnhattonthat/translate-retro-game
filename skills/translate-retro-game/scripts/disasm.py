"""ARM/Thumb (GBA, NDS) and MIPS (PS1) disassembly and cross-references, via capstone (pip install capstone).

    python -X utf8 disasm.py dis  FILE ADDR [COUNT] [--arch thumb|arm|mips] [--base HEX]
    python -X utf8 disasm.py xref FILE TARGET       [--arch ...] [--base HEX]
    python -X utf8 disasm.py --selftest

FILE is a code image: a .gba ROM (base 08000000, Thumb by default), a PS-X EXE (base and MIPS from its header),
or a raw binary with --base = the address of file offset 0 (NDS arm9.bin: 02000000; PS1 overlay: its RAM address).
ADDR/TARGET are hex addresses; values below --base are taken as file offsets.
dis annotates ARM/Thumb literal-pool loads with the loaded word.
xref finds what points at TARGET. ARM/Thumb: literal-pool words (TARGET or TARGET|1) and BL/BLX calls.
MIPS: pointer words, jal, and lui + addiu/ori/load/store pairs that build TARGET (within 16 instructions). A string
you move may have several such references: fix every one.
Named disasm.py, not dis.py: a dis.py next to your scripts shadows the standard library module.
"""
import argparse
import re
import struct
import sys

try:
    import capstone
except ImportError:
    sys.exit("disasm.py needs capstone: pip install capstone")

MODES = {"arm": (capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM),
         "thumb": (capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB),
         "mips": (capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)}


def load(path, base=None, arch=None):
    data = open(path, "rb").read()
    if data[:8] == b"PS-X EXE":
        return data, base if base is not None else struct.unpack_from("<I", data, 0x18)[0] - 0x800, arch or "mips"
    if path.lower().endswith(".gba"):
        return data, 0x08000000 if base is None else base, arch or "thumb"
    return data, base or 0, arch or "arm"


def dis(data, base, arch, addr, count):
    md = capstone.Cs(*MODES[arch])
    md.skipdata = True  # keep going through data words
    off = addr - base if addr >= base else addr
    width = 2 if arch == "thumb" else 4
    out = []
    for ins in md.disasm(data[off:off + count * width * 2], base + off):
        note = ""
        m = re.search(r"\[pc(?:, #(-?0x[0-9a-f]+|-?\d+))?\]", ins.op_str)
        if arch != "mips" and ins.mnemonic.startswith("ldr") and m:
            pc = (ins.address + 4) & ~3 if arch == "thumb" else ins.address + 8
            lit = pc + int(m[1] or "0", 0) - base
            if 0 <= lit <= len(data) - 4:
                note = "  ; =%08X" % struct.unpack_from("<I", data, lit)[0]
        out.append("%08X %06X  %-8s %-30s%s" % (ins.address, ins.address - base, ins.mnemonic, ins.op_str, note))
        if len(out) >= count:
            break
    return out


def xref_arm(data, base, target):
    hits = []
    for i in range(0, len(data) - 3, 2):
        w = struct.unpack_from("<I", data, i)[0]
        pc = base + i
        if i % 4 == 0:
            if w in (target, target | 1):
                hits.append(("ptr", i))
            if (w >> 25 & 7) == 5 and (w >> 28 == 0xF or w & 0x01000000):  # BL (any condition) / BLX imm
                off = (w & 0xFFFFFF) - ((w & 0x800000) << 1)
                dest = pc + 8 + off * 4 + ((w >> 23 & 2) if w >> 28 == 0xF else 0)
                if dest == target:
                    hits.append(("bl", i))
        hi, lo = w & 0xFFFF, w >> 16
        if hi >> 11 == 0x1E and lo >> 11 in (0x1F, 0x1D):  # Thumb BL / BLX pair
            off = (hi & 0x7FF) << 12 | (lo & 0x7FF) << 1
            off -= (off & 0x400000) << 1
            dest = pc + 4 + off
            if lo >> 11 == 0x1D:
                dest &= ~3
            if dest == target & ~1:
                hits.append(("thumb bl", i))
    return hits


LOADSTORE = (0x09, 0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2B)  # addiu, lb lh lw lbu lhu, sb sh sw


def xref_mips(data, base, target):
    hits = []
    hi_add, hi_or, lo = (target + 0x8000) >> 16 & 0xFFFF, target >> 16, target & 0xFFFF
    jal = 0x0C000000 | (target >> 2 & 0x3FFFFFF)
    for o in range(0, len(data) - 3, 4):
        w = struct.unpack_from("<I", data, o)[0]
        if w == target:
            hits.append(("ptr", o))
        elif w == jal:
            hits.append(("jal", o))
        elif w >> 26 == 0x0F and w & 0xFFFF in (hi_add, hi_or):  # lui rt, hi
            rt = w >> 16 & 31
            for k in range(1, 17):
                if o + 4 * k + 4 > len(data):
                    break
                w2 = struct.unpack_from("<I", data, o + 4 * k)[0]
                op = w2 >> 26
                want = hi_or if op == 0x0D else hi_add  # ori does not sign-extend
                if w2 >> 21 & 31 == rt and w2 & 0xFFFF == lo and w & 0xFFFF == want and (op in LOADSTORE or op == 0x0D):
                    hits.append(("lui pair (lo at %06X)" % (o + 4 * k), o))
                    break
    return hits


def selftest():
    base = 0x80010000
    code = struct.pack("<IIII", 0x3C048002, 0x24848000 | 0, 0x0C000000 | (0x80020000 >> 2 & 0x3FFFFFF), 0x80018000)
    # lui a0,0x8002 ; addiu a0,a0,-0x8000 -> 0x80018000
    hits = xref_mips(code, base, 0x80018000)
    assert ("lui pair (lo at 000004)", 0) in hits and ("ptr", 12) in hits, hits
    assert xref_mips(code, base, 0x80020000) == [("jal", 8)]
    thumb = bytes.fromhex("0148 7047 0000 0000 4523 0108")  # ldr r0,[pc,#4] ; bx lr ; pad ; .word 0x08012345
    lines = dis(thumb, 0x08000000, "thumb", 0x08000000, 2)
    assert lines[0].endswith("; =08012345"), lines
    assert ("ptr", 8) in xref_arm(thumb, 0x08000000, 0x08012344)  # Thumb pointer = target | 1
    bl = bytes.fromhex("00F0 02F8")  # bl +4 -> 0x08000008
    assert xref_arm(bl + bytes(8), 0x08000000, 0x08000008) == [("thumb bl", 0)]
    print("selftest ok")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["dis", "xref"])
    ap.add_argument("file")
    ap.add_argument("addr", type=lambda s: int(s, 16))
    ap.add_argument("count", nargs="?", type=int, default=40)
    ap.add_argument("--arch", choices=MODES)
    ap.add_argument("--base", type=lambda s: int(s, 16))
    a = ap.parse_args()
    data, base, arch = load(a.file, a.base, a.arch)
    if a.cmd == "dis":
        print("\n".join(dis(data, base, arch, a.addr, a.count)))
        return
    target = a.addr if a.addr >= base else a.addr + base
    hits = xref_mips(data, base, target) if arch == "mips" else xref_arm(data, base, target)
    for kind, off in hits:
        print("%-28s file %06X  addr %08X" % (kind, off, base + off))
    print(f"{len(hits)} references to {target:08X}")


if __name__ == "__main__":
    main()
