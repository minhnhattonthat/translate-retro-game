"""Stack GIMs (or their gfx/ replacements) into one PNG for reading/checking.
usage: showgim.py OUT.png ID [ID ...] [--zoom 2] [--cols 1] [--new]
ID = <cpk>/<arc>/<NNN>_<hexoff> (as in work/gim); a glob is allowed (e.g. 'sys/menu_saveload/*'); --new shows gfx/<ID>.png when it exists
(original left, replacement right)."""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import gim
from PIL import Image, ImageDraw

def load(id_):
    d = open(f'work/gim/{id_}.gim', 'rb').read(); im = gim.parse(d)[0]; w, h, rows = gim.to_rgba(d, im)
    return Image.frombytes('RGBA', (w, h), b''.join(rows))

def main():
    a = sys.argv[1:]; out = a.pop(0)
    zoom, cols = 2, 1
    if '--zoom' in a: i = a.index('--zoom'); zoom = int(a[i + 1]); del a[i:i + 2]
    if '--cols' in a: i = a.index('--cols'); cols = int(a[i + 1]); del a[i:i + 2]
    new = '--new' in a
    if new: a.remove('--new')
    ids = []
    for x in a: ids += sorted(os.path.relpath(p, 'work/gim').replace('\\', '/')[:-4] for p in glob.glob(f'work/gim/{x}.gim'))
    cells = []
    for i in ids:
        parts = [load(i)]
        if new and os.path.exists(f'gfx/{i}.png'): parts.append(Image.open(f'gfx/{i}.png').convert('RGBA'))
        w = sum(p.width for p in parts) + 6 * (len(parts) - 1); h = max(p.height for p in parts)
        c = Image.new('RGBA', (w, h), (70, 70, 110, 255)); x = 0
        for p in parts:
            bg = Image.new('RGBA', p.size, (70, 70, 110, 255)); bg.alpha_composite(p); c.paste(bg, (x, 0)); x += p.width + 6
        cells.append((i, c.resize((c.width * zoom, c.height * zoom), Image.NEAREST)))
    cw = max(c.width for _, c in cells) + 8; rh = max(c.height for _, c in cells) + 14
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new('RGB', (cw * cols, rh * rows), (20, 20, 20)); dr = ImageDraw.Draw(sheet)
    for k, (i, c) in enumerate(cells):
        x, y = (k % cols) * cw, (k // cols) * rh; dr.text((x + 2, y), i, fill=(255, 255, 0)); sheet.paste(c.convert('RGB'), (x + 4, y + 14))
    sheet.save(out); print(len(cells), 'images ->', out)

main()
