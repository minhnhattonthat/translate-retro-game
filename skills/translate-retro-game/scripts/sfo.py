"""PARAM.SFO reader / in-place string editor.  usage: sfo.py FILE [KEY=VALUE ...] [-o OUT]
Library: read(bytes) -> {key: (fmt, len, maxlen, offset, value)};  set_str(bytes, key, text) -> bytes (must fit in max_len)"""
import struct, sys

def read(b):
    assert b[:4] == b'\0PSF'
    kt, dt, n = struct.unpack_from('<III', b, 8); out = {}
    for i in range(n):
        ko, fmt, ln, mx, do = struct.unpack_from('<HHIII', b, 20 + 16 * i)
        key = b[kt + ko:b.index(b'\0', kt + ko)].decode(); raw = b[dt + do:dt + do + ln]
        val = raw.rstrip(b'\0').decode('utf-8') if fmt in (0x0004, 0x0204) else int.from_bytes(raw, 'little')
        out[key] = (fmt, ln, mx, dt + do, val)
    return out

def set_str(b, key, text):
    e = read(b)[key]; fmt, ln, mx, off, _ = e
    data = text.encode('utf-8') + b'\0'
    if len(data) > mx: raise ValueError(f'{key}: {len(data)} bytes > max {mx}')
    b = bytearray(b); b[off:off + mx] = data.ljust(mx, b'\0')
    i = list(read(bytes(b))).index(key); struct.pack_into('<I', b, 20 + 16 * i + 4, len(data))
    return bytes(b)

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read(); args = sys.argv[2:]
    out = args[args.index('-o') + 1] if '-o' in args else None
    for a in args:
        if '=' in a: k, v = a.split('=', 1); d = set_str(d, k, v)
    if out: open(out, 'wb').write(d)
    else:
        for k, (fmt, ln, mx, off, v) in read(d).items(): print(f'{k:20s} {fmt:#06x} len={ln} max={mx} {v!r}')
