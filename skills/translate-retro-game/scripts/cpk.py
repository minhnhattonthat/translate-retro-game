"""CRI CPK archive reader/rebuilder (header, TOC and ETOC are patched in place, file data is re-laid out).
usage: cpk.py list CPK | cpk.py info CPK | cpk.py rebuild CPK OUT NAME=FILE [NAME=FILE ...]   (NAME = file name inside the CPK)
Library: open_cpk(path) -> (info, [Entry]);  rebuild(cpk_path, {name: bytes}) -> bytes"""
import struct, sys
from collections import namedtuple

Entry = namedtuple('Entry', 'dir name off size csize id')
SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 4, 9: 8, 0xA: 4, 0xB: 8}

class Utf:
    """@UTF table. rows[i][col] = value; pos[i][col] = absolute file offset of the row cell (for in-place patching)."""
    def __init__(self, b, base=0):
        assert b[base:base + 4] == b'@UTF', b[base:base + 4]
        self.base = base; t = base + 8
        size, rows_off, str_off, data_off, name_off, ncols, rowlen, nrows = struct.unpack_from('>IIIIIHHI', b, base + 4)
        self.t = t; self.rows_off = rows_off; self.rowlen = rowlen
        strs = b[t + str_off:t + data_off]
        self.s = lambda o: strs[o:strs.index(b'\0', o)].decode('utf-8', 'replace')
        p = base + 32; self.cols = []
        for _ in range(ncols):
            flag = b[p]; p += 1
            nm = self.s(struct.unpack_from('>I', b, p)[0]); p += 4
            ty, st = flag & 0xF, flag & 0xF0
            const = None
            if st == 0x30: const, p = self.val(b, p, ty, data_off)
            self.cols.append((nm, ty, st, const))
        self.rows, self.pos = [], []
        for r in range(nrows):
            q = t + rows_off + r * rowlen; row, pos = {}, {}
            for nm, ty, st, const in self.cols:
                if st == 0x30: row[nm] = const
                elif st == 0x50:
                    pos[nm] = q; row[nm], q = self.val(b, q, ty, data_off)
                else: row[nm] = None
            self.rows.append(row); self.pos.append(pos)
        self.types = {nm: ty for nm, ty, st, c in self.cols}

    def val(self, b, p, ty, data_off):
        if ty in (0, 1): return b[p], p + 1
        if ty in (2, 3): return struct.unpack_from('>H', b, p)[0], p + 2
        if ty in (4, 5): return struct.unpack_from('>I', b, p)[0], p + 4
        if ty in (6, 7): return struct.unpack_from('>Q', b, p)[0], p + 8
        if ty == 8: return struct.unpack_from('>f', b, p)[0], p + 4
        if ty == 0xA: return self.s(struct.unpack_from('>I', b, p)[0]), p + 4
        if ty == 0xB:
            o, n = struct.unpack_from('>II', b, p); return ('data', self.t + data_off + o, n), p + 8
        raise ValueError(ty)

    def set(self, buf, i, col, v):
        """Patch row i's cell in bytearray buf (only row-stored numeric columns)."""
        ty = self.types[col]; p = self.pos[i][col]
        buf[p:p + SIZES[ty]] = v.to_bytes(SIZES[ty], 'big')

def utf_table(b, base=0): return Utf(b, base).rows

def parse(h, f):
    """-> info Utf, toc Utf|None, entries"""
    info = Utf(h, 16); r = info.rows[0]
    toc = None; ents = []
    if r['TocOffset']:
        f.seek(r['TocOffset']); tb = f.read(r['TocSize']); assert tb[:4] == b'TOC '
        toc = Utf(tb, 16)
        content = min(x for x in (r['ContentOffset'], r['TocOffset']) if x)  # FileOffset is relative to the lower of the two
        for t in toc.rows:
            ents.append(Entry(t['DirName'], t['FileName'], content + t['FileOffset'], t['ExtractSize'], t['FileSize'], t.get('ID')))
    return info, toc, ents

def open_cpk(path):
    with open(path, 'rb') as f:
        info, toc, ents = parse(f.read(0x800), f)
    return info.rows[0], ents

def rebuild(path, repl):
    """Return the CPK with files named in repl replaced. Files keep their order and 2048-byte alignment; the TOC offsets and
    size fields are rewritten, everything else (ACB/AWB/PMF data, GTOC, ETOC) is copied."""
    f = open(path, 'rb'); h = bytearray(f.read(0x800))
    info, toc, ents = parse(bytes(h), f)
    r = info.rows[0]; assert 'ItocOffset' not in r or not r['ItocOffset'], 'ITOC-only CPK not supported'
    f.seek(r['TocOffset']); tb = bytearray(f.read(r['TocSize']))
    content = min(r['ContentOffset'], r['TocOffset'])
    order = sorted(range(len(ents)), key=lambda i: ents[i].off)
    out = bytearray(); newoff = {}; pos = r['ContentOffset'] - content   # relative to `content`
    newfiles = {}
    for i in order:
        e = ents[i]
        if e.name in repl: data = repl[e.name]
        else: f.seek(e.off); data = f.read(e.csize)
        newfiles[i] = len(data)
        newoff[i] = pos; out += data
        pad = 0 if i == order[-1] else -len(data) % r['Align']; out += b'\0' * pad; pos += len(data) + pad
    for i, e in enumerate(ents):
        toc.set(tb, i, 'FileOffset', newoff[i]); toc.set(tb, i, 'FileSize', newfiles[i]); toc.set(tb, i, 'ExtractSize', newfiles[i])
    # leading region (header, TOC, GTOC, padding) copied, then the new content
    f.seek(0); head = bytearray(f.read(r['ContentOffset']))
    head[r['TocOffset']:r['TocOffset'] + len(tb)] = tb
    # size fields: keep the original's bookkeeping (padding conventions) and add the change
    f.seek(0, 2); d_content = len(out) - (f.tell() - r['ContentOffset'] - (r.get('EtocSize') or 0))
    d_data = sum(newfiles.values()) - sum(e.csize for e in ents)
    if 'ContentSize' in info.pos[0]: info.set(head, 0, 'ContentSize', r['ContentSize'] + d_content)
    for col in ('EnabledPackedSize', 'EnabledDataSize'):
        if col in info.pos[0]: info.set(head, 0, col, r[col] + d_data)
    tail = b''
    if r.get('EtocOffset'):  # ETOC (timestamps) sits after the content; carry it over unchanged
        f.seek(r['EtocOffset']); tail = f.read(r['EtocSize'])
        newetoc = r['ContentOffset'] + len(out)
        if 'EtocOffset' in info.pos[0]: info.set(head, 0, 'EtocOffset', newetoc)
    f.close()
    return bytes(head) + bytes(out) + tail

if __name__ == '__main__':
    cmd, path = sys.argv[1], sys.argv[2]
    info, ents = open_cpk(path)
    if cmd == 'info':
        for k, v in info.items(): print(k, v)
    elif cmd == 'list':
        for e in ents: print(f'{e.off:10d} {e.csize:9d} {e.size:9d} {e.dir}/{e.name}')
    elif cmd == 'rebuild':
        repl = {a.split('=')[0]: open(a.split('=', 1)[1], 'rb').read() for a in sys.argv[4:]}
        open(sys.argv[3], 'wb').write(rebuild(path, repl))
