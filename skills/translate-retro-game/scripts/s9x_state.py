"""Unpack a RetroArch/Snes9x savestate (RZIP or raw) into dumps that lua/probes/s9x_load.lua injects into Mesen.

python s9x_state.py STATE OUT_PREFIX -> OUT_PREFIX.{RAM,VRA,SRA} (raw) + OUT_PREFIX.lua (CPU regs)
"""
import re
import struct
import sys
import zlib


def load(path):
    d = open(path, 'rb').read()
    if d[:8] == b'#RZIPv\x01#':  # RetroArch: u32 chunk size, u64 total, then (u32 len + zlib) chunks
        out, p = bytearray(), 20
        while p < len(d):
            n = struct.unpack_from('<I', d, p)[0]
            out += zlib.decompress(d[p + 4:p + 4 + n])
            p += 4 + n
        d = bytes(out)
    return d


def blocks(d):
    """Snes9x snapshot blocks 'NAM:000123:<data>' after the '#!s9xsnp' header line."""
    res, p = {}, d.index(b'#!s9xsnp')
    p = d.index(b'\n', p) + 1
    while (m := re.match(rb'([A-Z0-9]{3}):(\d{6}):', d[p:p + 11])):
        n = int(m.group(2))
        res.setdefault(m.group(1).decode(), d[p + 11:p + 11 + n])
        p += 11 + n
    return res


def regs(reg):
    """REG block, big-endian: PB DB P A D S X Y PC."""
    pb, db, p, a, d, s, x, y, pc = struct.unpack('>BBHHHHHHH', reg)
    return dict(k=pb, dbr=db, ps=p & 0xFF, a=a, d=d, sp=s, x=x, y=y, pc=pc)


if __name__ == '__main__':
    src, out = sys.argv[1:3]
    b = blocks(load(src))
    for k in ('RAM', 'VRA', 'SRA'):
        open(f'{out}.{k}', 'wb').write(b[k])
    r = regs(b['REG'])
    lua = 'S9X_REGS = {' + ', '.join(f'["cpu.{k}"] = {v}' for k, v in r.items()) + '}\n'
    lua += f'S9X_PREFIX = [[{out}]]\n'
    open(f'{out}.lua', 'w').write(lua)
    print(f'PC {r["k"]:02X}:{r["pc"]:04X} SP {r["sp"]:04X} P {r["ps"]:02X} ->', out)
