"""Draw English text into a transparent RGBA canvas for replacing Japanese text images.
Library: text_image(w, h, text, ...) -> PIL RGBA;  fit(...) picks the largest size that fits;  FONTS = name -> path
Style knobs: font, size (None = fit), fill, stroke (width, colour), shadow, xscale (horizontal squeeze for condensed styles),
align (l/c/r), valign (t/m/b), spacing (line gap), tracking."""
import os
from PIL import Image, ImageDraw, ImageFont

WIN = 'C:/Windows/Fonts/'
FONTS = {
    'serif-b': WIN + 'timesbd.ttf', 'serif': WIN + 'times.ttf', 'georgia-b': WIN + 'georgiab.ttf', 'cambria-b': WIN + 'cambriab.ttf',
    'book-b': WIN + 'BOOKOSB.TTF', 'sans-cond-b': WIN + 'ARIALNB.TTF', 'sans-cond': WIN + 'ARIALN.TTF', 'sans': WIN + 'arial.ttf',
    'sans-b': WIN + 'arialbd.ttf', 'bahn': WIN + 'bahnschrift.ttf', 'mono-b': WIN + 'courbd.ttf', 'segoe': WIN + 'segoeui.ttf',
    'segoe-b': WIN + 'segoeuib.ttf', 'impact': WIN + 'impact.ttf',
}
_cache = {}
def font(name, size):
    k = (name, size)
    if k not in _cache: _cache[k] = ImageFont.truetype(FONTS.get(name, name), size)
    return _cache[k]

def _measure(lines, f, spacing, tracking):
    ws = []
    for ln in lines:
        w = sum(f.getlength(c) + tracking for c in ln) - tracking if tracking else f.getlength(ln)
        ws.append(w)
    asc, desc = f.getmetrics(); lh = asc + desc + spacing
    return ws, lh

def text_image(w, h, text, font_name='serif-b', size=None, fill=(255, 255, 255, 255), stroke=None, shadow=None, xscale=1.0,
               align='c', valign='m', spacing=0, tracking=0, pad=1, min_size=6, max_size=96, canvas=None, box=None):
    """Render into a w x h RGBA image (or draw onto canvas inside box=(x, y, bw, bh)). Returns the image."""
    img = canvas if canvas is not None else Image.new('RGBA', (w, h), (0, 0, 0, 0))
    bx, by, bw, bh = box if box else (0, 0, w, h)
    lines = text.split('\n')
    sw = stroke[0] if stroke else 0
    def layout(sz):
        f = font(font_name, sz); ws, lh = _measure(lines, f, spacing, tracking)
        return f, ws, lh, max(ws) * xscale + 2 * sw + (abs(shadow[0]) if shadow else 0), lh * len(lines) + 2 * sw + (abs(shadow[1]) if shadow else 0)
    if size is None:
        size = max_size
        while size > min_size:
            f, ws, lh, tw, th = layout(size)
            if tw <= bw - 2 * pad and th <= bh - 2 * pad: break
            size -= 1
    f, ws, lh, tw, th = layout(size)
    layer = Image.new('RGBA', (int(max(ws) + 2 * sw + 4), int(lh * len(lines) + 2 * sw + 4)), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    for i, ln in enumerate(lines):
        x0 = {'l': 0, 'c': (max(ws) - ws[i]) / 2, 'r': max(ws) - ws[i]}[align] + sw + 2
        y0 = i * lh + sw + 2
        if tracking:
            x = x0
            for c in ln:
                d.text((x, y0), c, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke[1] if stroke else None); x += f.getlength(c) + tracking
        else: d.text((x0, y0), ln, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke[1] if stroke else None)
    if xscale != 1.0: layer = layer.resize((max(1, int(layer.width * xscale)), layer.height), Image.LANCZOS)
    x = bx + {'l': pad, 'c': (bw - layer.width) // 2, 'r': bw - layer.width - pad}[align]
    y = by + {'t': pad, 'm': (bh - layer.height) // 2, 'b': bh - layer.height - pad}[valign]
    if shadow:
        sh = Image.new('RGBA', layer.size, (0, 0, 0, 0)); sh.paste(Image.new('RGBA', layer.size, shadow[2]), mask=layer.split()[3])
        img.alpha_composite(sh, (max(x + shadow[0], 0), max(y + shadow[1], 0)))
    cx, cy = max(-x, 0), max(-y, 0)          # clip what falls outside the canvas on the left/top
    if cx < layer.width and cy < layer.height: img.alpha_composite(layer.crop((cx, cy, layer.width, layer.height)), (x + cx, y + cy))
    return img

def wrap(text, font_name, size, width, xscale=1.0, tracking=0):
    """Greedy word wrap of text (existing \n are kept) to pixel width."""
    f = font(font_name, size); out = []
    for para in text.split('\n'):
        cur = ''
        for word in para.split(' '):
            t = (cur + ' ' + word).strip()
            if cur and f.getlength(t) * xscale + tracking * len(t) > width: out.append(cur); cur = word
            else: cur = t
        out.append(cur)
    return '\n'.join(out)

def dominant(img, min_alpha=200):
    """Most common opaque colour of an RGBA image (to match the original text colour)."""
    from collections import Counter
    c = Counter(px[:3] for px in img.getdata() if px[3] >= min_alpha)
    return c.most_common(1)[0][0] if c else (255, 255, 255)


def inpaint(img, box, white_min=170, iters=60):
    """Remove near-white lettering inside box by diffusing the surrounding colours into it (for text drawn over art)."""
    import numpy as np
    a = np.array(img.convert('RGBA')).astype(float); x0, y0, x1, y1 = box
    reg = a[y0:y1, x0:x1]
    mask = (reg[..., :3].min(axis=2) > white_min) & (reg[..., 3] > 60)
    for _ in range(2):   # grow over the anti-aliased halo
        m = mask.copy(); m[1:] |= mask[:-1]; m[:-1] |= mask[1:]; m[:, 1:] |= mask[:, :-1]; m[:, :-1] |= mask[:, 1:]; mask = m
    known = ~mask; cur = reg.copy(); cur[mask] = 0
    for _ in range(iters):
        wsum = np.zeros(mask.shape); acc = np.zeros(reg.shape)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            k = np.roll(known, (dy, dx), (0, 1)); v = np.roll(cur, (dy, dx), (0, 1))
            wsum += k; acc += v * k[..., None]
        fill = mask & ~known & (wsum > 0)
        cur[fill] = acc[fill] / wsum[fill][:, None]; known = known | fill
    a[y0:y1, x0:x1] = cur
    return Image.fromarray(a.clip(0, 255).astype('uint8'))
