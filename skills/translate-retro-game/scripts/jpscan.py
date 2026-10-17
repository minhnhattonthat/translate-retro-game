"""Find Japanese text runs in a binary: Shift-JIS (cp932), UTF-8 and UTF-16LE (several encodings can coexist in one binary).
usage: jpscan.py FILE [min_chars=3] [base_addr]   (offsets print as base_addr + file offset; most hits in code are noise,
real strings read as sentences). No hits does not mean no text: many games use their own encoding (relsearch.py)."""
import re

def sjis_runs(d, n=3):
    rx = re.compile(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e]){%d,}' % (2 * n))
    for m in rx.finditer(d):
        try: s = m.group().decode('cp932')
        except UnicodeDecodeError: continue
        if sum(1 for c in s if ord(c) > 0x2FFF) >= n: yield m.start(), s

def utf8_runs(d, n=3):
    rx = re.compile(rb'(?:[\xe3-\xe9][\x80-\xbf][\x80-\xbf]|[\x20-\x7e\n]){%d,}' % (n + 1))
    for m in rx.finditer(d):
        try: s = m.group().decode('utf-8')
        except UnicodeDecodeError: continue
        if sum(1 for c in s if ord(c) > 0x2FFF) >= n: yield m.start(), s

def utf16_runs(d, n=3):
    rx = re.compile(rb'(?:[\x00-\xff][\x30-\x9f]|[\x20-\x7e]\x00){%d,}' % n)
    for m in rx.finditer(d):
        s = m.group()
        if len(s) % 2 or m.start() % 2: continue
        try: t = s.decode('utf-16le')
        except UnicodeDecodeError: continue
        if sum(1 for c in t if 0x3040 <= ord(c) <= 0x9FFF) >= n: yield m.start(), t

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file')
    ap.add_argument('min_chars', nargs='?', type=int, default=3)
    ap.add_argument('base_addr', nargs='?', type=lambda s: int(s, 0), default=0)
    a = ap.parse_args()
    d = open(a.file, 'rb').read()
    for kind, fn in (('sjis ', sjis_runs), ('utf8 ', utf8_runs), ('utf16', utf16_runs)):
        for o, s in fn(d, a.min_chars): print(f'{kind} {a.base_addr + o:#x} {s!r}')
