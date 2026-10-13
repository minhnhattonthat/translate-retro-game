"""ISO9660 (PSP UMD) list / extract / replace files in place.
usage: iso9660.py list ISO | iso9660.py x ISO OUTDIR | iso9660.py put ISO OUT /PSP_GAME/USRDIR/x.cpk=localfile [...]
Library: listing(f) -> [(path, lba, size, rec_pos)];  patch(iso_in, iso_out, {path: bytes})
A replacement that fits the old sector count stays in place; a larger one is appended at the end of the image."""
import struct, sys, os, shutil

def read_dir(f, lba, size, path, out):
    f.seek(lba * 2048); data = f.read(size); i = 0
    while i < size:
        n = data[i]
        if n == 0: i = (i // 2048 + 1) * 2048; continue
        rec = data[i:i + n]; pos = lba * 2048 + i; i += n
        loc, ln = struct.unpack_from('<I', rec, 2)[0], struct.unpack_from('<I', rec, 10)[0]
        name = rec[33:33 + rec[32]]
        if name in (b'\x00', b'\x01'): continue
        p = path + '/' + name.decode('latin1').split(';')[0]
        if rec[25] & 2: read_dir(f, loc, ln, p, out)
        else: out.append((p, loc, ln, pos))

def listing(f):
    f.seek(16 * 2048); pvd = f.read(2048); root = pvd[156:190]
    out = []; read_dir(f, struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0], '', out); return out

def both(v): return struct.pack('<I', v) + struct.pack('>I', v)

def patch(iso_in, iso_out, repl):
    if os.path.abspath(iso_in) != os.path.abspath(iso_out): shutil.copyfile(iso_in, iso_out)
    with open(iso_out, 'r+b') as f:
        files = {p: (lba, ln, pos) for p, lba, ln, pos in listing(f)}
        f.seek(0, 2); end = f.tell(); assert end % 2048 == 0
        for p, data in repl.items():
            lba, ln, pos = files[p]
            if -(-len(data) // 2048) <= -(-ln // 2048): new_lba = lba
            else:
                new_lba = end // 2048; f.seek(end); f.write(b'\0' * (-(-len(data) // 2048) * 2048)); end += -(-len(data) // 2048) * 2048
            f.seek(new_lba * 2048); f.write(data)
            old_pad = -(-ln // 2048) * 2048
            if new_lba == lba and len(data) < old_pad:   # clear the tail so stale bytes do not linger
                f.write(b'\0' * (old_pad - len(data)))
            f.seek(pos + 2); f.write(both(new_lba)); f.seek(pos + 10); f.write(both(len(data)))
        f.seek(16 * 2048 + 80); f.write(both(end // 2048))     # volume space size

if __name__ == '__main__':
    cmd, iso = sys.argv[1], sys.argv[2]
    if cmd == 'list':
        with open(iso, 'rb') as f:
            for p, lba, ln, _ in listing(f): print(f'{lba:8d} {ln:11d} {p}')
    elif cmd == 'x':
        with open(iso, 'rb') as f:
            for p, lba, ln, _ in listing(f):
                d = sys.argv[3] + p; os.makedirs(os.path.dirname(d), exist_ok=True); f.seek(lba * 2048); open(d, 'wb').write(f.read(ln))
    elif cmd == 'put':
        patch(iso, sys.argv[3], {a.split('=')[0]: open(a.split('=', 1)[1], 'rb').read() for a in sys.argv[4:]})
