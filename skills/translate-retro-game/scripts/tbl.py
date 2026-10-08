"""Thingy-style table codec with control codes, hex escapes and multi-byte keys.

Table lines: `XX=あ`, `XXYY=漢`, control codes `F0={end}`, `F1={wait:1}` (1 argument byte). Unknown bytes decode
as `[XX]` and encode back, so decode -> encode is byte-exact: the basis of the extraction roundtrip test.

    from tbl import Table
    t = Table.load("tbl/jp.tbl"); text, used = t.decode(rom, 0x1234A); assert t.encode(text) == rom[0x1234A:0x1234A + used]
"""
import re
from pathlib import Path

CTRL = re.compile(r"\{(\w+)(?::(\d+))?\}$")
TERMINATORS = {"end", "goto"}  # decoding stops after these (goto = unconditional jump)
TOKEN = re.compile(r"\{(\w+)(?::([0-9A-Fa-f]*))?\}|\[([0-9A-Fa-f]{2})\]")


class Table:
    def __init__(self, lines):
        self.dec, self.ctrl, self.enc, self.ctrl_enc = {}, {}, {}, {}
        for n, line in enumerate(lines, 1):
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            key, sep, val = line.partition("=")
            if not sep or not val:
                raise ValueError(f"table line {n}: bad entry {line!r}")
            code = bytes.fromhex(key)
            m = CTRL.match(val)
            if m:
                argc = int(m[2] or 0)
                self.ctrl[code] = (m[1], argc)
                self.ctrl_enc.setdefault(m[1], (code, argc))
            else:
                self.dec[code] = val
                self.enc.setdefault(val, code)
        self.keylen = max(map(len, (*self.dec, *self.ctrl)), default=1)
        self.vallen = max(map(len, self.enc), default=1)

    @classmethod
    def load(cls, path):
        return cls(Path(path).read_text(encoding="utf-8-sig").splitlines())

    def decode(self, data, pos=0, length=None, maxlen=4096):
        """length=None: decode through {end}/{goto}. Else decode exactly `length` bytes. Returns (text, consumed)."""
        start, out = pos, []
        stop = len(data) if length is None else pos + length
        while pos < stop:
            if length is None and pos - start >= maxlen:
                raise ValueError(f"no {{end}} within {maxlen} bytes of {start:#x}")
            for k in range(min(self.keylen, stop - pos), 0, -1):
                code = bytes(data[pos:pos + k])
                if code in self.ctrl:
                    name, argc = self.ctrl[code]
                    args = bytes(data[pos + k:pos + k + argc])
                    pos += k + argc
                    out.append(f"{{{name}:{args.hex().upper()}}}" if argc else f"{{{name}}}")
                    if name in TERMINATORS and length is None:
                        return "".join(out), pos - start
                    break
                if self.enc.get(self.dec.get(code)) == code:
                    out.append(self.dec[code])
                    pos += k
                    break
            else:
                out.append(f"[{data[pos]:02X}]")
                pos += 1
        if length is None:
            raise ValueError(f"ran off end of data decoding from {start:#x}")
        return "".join(out), pos - start

    def encode(self, text: str) -> bytes:
        out, i = bytearray(), 0
        while i < len(text):
            m = TOKEN.match(text, i)
            if m:
                if m[3]:
                    out.append(int(m[3], 16))
                else:
                    if m[1] not in self.ctrl_enc:
                        raise ValueError(f"unknown control {{{m[1]}}} at {i} in {text!r}")
                    code, argc = self.ctrl_enc[m[1]]
                    args = bytes.fromhex(m[2] or "")
                    if len(args) != argc:
                        raise ValueError(f"{{{m[1]}}} needs {argc} arg bytes at {i} in {text!r}")
                    out += code + args
                i = m.end()
                continue
            for k in range(min(self.vallen, len(text) - i), 0, -1):
                if text[i:i + k] in self.enc:
                    out += self.enc[text[i:i + k]]
                    i += k
                    break
            else:
                raise ValueError(f"unencodable {text[i]!r} at {i} in {text!r}")
        return bytes(out)


if __name__ == "__main__":
    t = Table(["10=あ", "11=い", "8001=漢", "20=A", "F1={wait:1}", "F0={end}"])
    data = b"\x10\x8a\x80\x01\xf1\x05\x20\xf0"
    text, used = t.decode(data)
    assert text == "あ[8A]漢{wait:05}A{end}" and used == len(data), text
    assert t.encode(text) == data
    print("selftest ok")
