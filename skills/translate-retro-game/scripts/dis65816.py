"""Linear 65816 (SNES) disassembler. Tracks M/X width through REP/SEP only (no flow analysis).

    python -X utf8 dis65816.py ROM C21E51 [COUNT] [--map lorom|hirom|exhirom] [--m8] [--x8]
    python -X utf8 dis65816.py --selftest

ADDR is the CPU address (hex). M/X start 16-bit; pass --m8/--x8 when the code runs after SEP #$20/#$10.
A 512-byte copier header is skipped automatically. Width tracking is linear: after a branch target or a
JSR into code with other flags, restart at that address with the right --m8/--x8.
"""
import argparse
import sys

FMT = {"imp": "", "acc": "A", "imm8": "#${:02X}", "dp": "${:02X}", "dpx": "${:02X},x", "dpy": "${:02X},y",
       "idp": "(${:02X})", "idpx": "(${:02X},x)", "idpy": "(${:02X}),y", "ildp": "[${:02X}]", "ildpy": "[${:02X}],y",
       "sr": "${:02X},s", "sry": "(${:02X},s),y", "abs": "${:04X}", "absx": "${:04X},x", "absy": "${:04X},y",
       "iabs": "(${:04X})", "iabsx": "(${:04X},x)", "ilabs": "[${:04X}]", "long": "${:06X}", "longx": "${:06X},x"}
SIZE = {"imp": 1, "acc": 1, "abs": 3, "absx": 3, "absy": 3, "iabs": 3, "iabsx": 3, "ilabs": 3, "rell": 3, "bm": 3,
        "long": 4, "longx": 4}

OPS = {}
for i, mn in enumerate(["ORA", "AND", "EOR", "ADC", "STA", "LDA", "CMP", "SBC"]):
    for off, mode in [(1, "idpx"), (3, "sr"), (5, "dp"), (7, "ildp"), (9, "immM"), (0xD, "abs"), (0xF, "long"),
                      (0x11, "idpy"), (0x12, "idp"), (0x13, "sry"), (0x15, "dpx"), (0x17, "ildpy"), (0x19, "absy"),
                      (0x1D, "absx"), (0x1F, "longx")]:
        OPS[i * 0x20 + off] = (mn, mode)
OPS[0x89] = ("BIT", "immM")
for spec in """00 BRK imm8|02 COP imm8|04 TSB dp|06 ASL dp|08 PHP imp|0A ASL acc|0B PHD imp|0C TSB abs|0E ASL abs
10 BPL rel|14 TRB dp|16 ASL dpx|18 CLC imp|1A INC acc|1B TCS imp|1C TRB abs|1E ASL absx
20 JSR abs|22 JSL long|24 BIT dp|26 ROL dp|28 PLP imp|2A ROL acc|2B PLD imp|2C BIT abs|2E ROL abs
30 BMI rel|34 BIT dpx|36 ROL dpx|38 SEC imp|3A DEC acc|3B TSC imp|3C BIT absx|3E ROL absx
40 RTI imp|42 WDM imm8|44 MVP bm|46 LSR dp|48 PHA imp|4A LSR acc|4B PHK imp|4C JMP abs|4E LSR abs
50 BVC rel|54 MVN bm|56 LSR dpx|58 CLI imp|5A PHY imp|5B TCD imp|5C JML long|5E LSR absx
60 RTS imp|62 PER rell|64 STZ dp|66 ROR dp|68 PLA imp|6A ROR acc|6B RTL imp|6C JMP iabs|6E ROR abs
70 BVS rel|74 STZ dpx|76 ROR dpx|78 SEI imp|7A PLY imp|7B TDC imp|7C JMP iabsx|7E ROR absx
80 BRA rel|82 BRL rell|84 STY dp|86 STX dp|88 DEY imp|8A TXA imp|8B PHB imp|8C STY abs|8E STX abs
90 BCC rel|94 STY dpx|96 STX dpy|98 TYA imp|9A TXS imp|9B TXY imp|9C STZ abs|9E STZ absx
A0 LDY immX|A2 LDX immX|A4 LDY dp|A6 LDX dp|A8 TAY imp|AA TAX imp|AB PLB imp|AC LDY abs|AE LDX abs
B0 BCS rel|B4 LDY dpx|B6 LDX dpy|B8 CLV imp|BA TSX imp|BB TYX imp|BC LDY absx|BE LDX absy
C0 CPY immX|C2 REP imm8|C4 CPY dp|C6 DEC dp|C8 INY imp|CA DEX imp|CB WAI imp|CC CPY abs|CE DEC abs
D0 BNE rel|D4 PEI idp|D6 DEC dpx|D8 CLD imp|DA PHX imp|DB STP imp|DC JML ilabs|DE DEC absx
E0 CPX immX|E2 SEP imm8|E4 CPX dp|E6 INC dp|E8 INX imp|EA NOP imp|EB XBA imp|EC CPX abs|EE INC abs
F0 BEQ rel|F4 PEA abs|F6 INC dpx|F8 SED imp|FA PLX imp|FB XCE imp|FC JSR iabsx|FE INC absx""".replace("\n", "|").split("|"):
    op, mn, mode = spec.split()
    OPS[int(op, 16)] = (mn, mode)
assert len(OPS) == 256

MAPS = {
    "lorom": lambda a: ((a & 0x7F0000) >> 1) | (a & 0x7FFF),
    "hirom": lambda a: a & 0x3FFFFF,
    "exhirom": lambda a: (a & 0x3FFFFF) | (0 if a & 0x800000 else 0x400000),
}


def disasm(rom, addr, n, mapping="lorom", m8=False, x8=False):
    """Up to n instructions starting at CPU address `addr`; returns text lines."""
    to_off = MAPS[mapping]
    out = []
    for _ in range(n):
        pc = to_off(addr)
        if pc >= len(rom):
            break
        mn, mode = OPS[rom[pc]]
        if mode in ("immM", "immX"):
            wide = not (m8 if mode == "immM" else x8)
            size, text = (3, "#${:04X}") if wide else (2, "#${:02X}")
        else:
            size, text = SIZE.get(mode, 2), FMT.get(mode, "")
        raw = bytes(rom[pc:pc + size])
        val = int.from_bytes(raw[1:], "little")
        if mode == "rel":
            text = f"${(addr + 2 + (val - 256 if val > 127 else val)) & 0xFFFF:04X}"
        elif mode == "rell":
            text = f"${(addr + 3 + (val - 65536 if val > 32767 else val)) & 0xFFFF:04X}"
        elif mode == "bm":  # bytes are dest bank, src bank; syntax is MVN src,dest
            text = f"${raw[2]:02X},${raw[1]:02X}"
        else:
            text = text.format(val)
        if mn == "REP":
            m8, x8 = m8 and not val & 0x20, x8 and not val & 0x10
        elif mn == "SEP":
            m8, x8 = m8 or bool(val & 0x20), x8 or bool(val & 0x10)
        out.append(f"{addr >> 16:02X}:{addr & 0xFFFF:04X}  {pc:06X}  {raw.hex(' '):12s} {mn} {text}".rstrip())
        addr = (addr & 0xFF0000) | ((addr + size) & 0xFFFF)
    return out


def selftest():
    code = bytes.fromhex("C230 A93412 E220 A912 547E7F 80FE 60")
    rom = bytearray(0x8000) + code
    lines = disasm(rom, 0x018000, 6)
    assert lines[1].endswith("LDA #$1234"), lines[1]
    assert lines[3].endswith("LDA #$12"), lines[3]
    assert lines[4].endswith("MVN $7F,$7E"), lines[4]
    assert lines[5].endswith("BRA $800C"), lines[5]
    assert MAPS["hirom"](0xC12345) == 0x012345 and MAPS["lorom"](0x80D960) == 0x5960
    print("selftest ok")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("addr", type=lambda s: int(s.replace("$", "").replace(":", ""), 16))
    ap.add_argument("count", nargs="?", type=int, default=40)
    ap.add_argument("--map", choices=MAPS, default="lorom")
    ap.add_argument("--m8", action="store_true")
    ap.add_argument("--x8", action="store_true")
    a = ap.parse_args()
    rom = open(a.rom, "rb").read()
    if len(rom) % 1024 == 512:
        rom = rom[512:]
    print("\n".join(disasm(rom, a.addr, a.count, a.map, a.m8, a.x8)))


if __name__ == "__main__":
    main()
