"""romdiff.py ORIG NEW [HEX | HEX-HEX ...] [--writes FILE]   (allowed offsets / inclusive ranges)
Exit 0 if NEW == ORIG except at allowed offsets; extra bytes in NEW must be 0xFF unless allowed.
Exit 1 on unexpected differences, 2 on bad input.

Catches edits that land outside the regions you meant to touch (pointer tables, text banks, free space): the bug
class where a patch overwrites flag bytes or graphics and every unit test still passes. Keep the allowed ranges in
a file (one range + comment per line), not a single long Makefile line.

--writes FILE: the build logs every write it makes, one per line: `OFFSET ORIG_HEX NEW_HEX [writer name]`
(hex offset, `#` comments). On top of the range check this fails when
  - ORIG does not hold ORIG_HEX at OFFSET (wrong revision, stale address, a write planned against a patched buffer);
  - NEW does not hold NEW_HEX (a later write overwrote this one);
  - two writes overlap;
  - a changed byte is covered by neither a write nor an allowed range.
Bytes past the end of ORIG count as 0xFF.

python -X utf8 romdiff.py --selftest"""
import sys

def load_writes(path):
	writes = []
	for n, line in enumerate(open(path, encoding="utf-8"), 1):
		parts = line.split("#")[0].split(None, 3)
		if not parts:
			continue
		if len(parts) < 3 or len(parts[1]) != len(parts[2]):
			sys.exit("%s:%d: want OFFSET ORIG_HEX NEW_HEX [writer], same length hex" % (path, n))
		writer = parts[3].strip() if len(parts) > 3 else "%s:%d" % (path, n)
		writes.append((int(parts[0], 16), bytes.fromhex(parts[1]), bytes.fromhex(parts[2]), writer))
	return writes

def check(orig, new, allowed, writes):
	"""Returns a list of error lines and the count of allowed diffs."""
	errs = []
	if len(new) < len(orig):
		return ["NEW is shorter than ORIG (%d < %d)" % (len(new), len(orig))], 0
	padded = orig + b"\xff" * (len(new) - len(orig))
	covered = set(allowed)
	last_end, last_by = -1, None
	for off, want_orig, want_new, by in sorted(writes):
		end = off + len(want_orig)
		if off < last_end:
			errs.append("0x%06X: %s overlaps %s" % (off, by, last_by))
		if end > last_end:
			last_end, last_by = end, by
		if padded[off:end] != want_orig:
			errs.append("0x%06X: %s expects orig %s, ORIG has %s" % (off, by, want_orig.hex(), padded[off:end].hex()))
		if new[off:end] != want_new:
			errs.append("0x%06X: %s wrote %s, NEW has %s (overwritten later?)" % (off, by, want_new.hex(), new[off:end].hex()))
		covered.update(range(off, end))
	bad, ok = [], 0
	for i in range(len(new)):
		if padded[i] == new[i]:
			continue
		if i in covered:
			ok += 1
		else:
			bad.append(i)
	for i in bad[:50]:
		o = ("%02X" % orig[i]) if i < len(orig) else "--"
		errs.append("0x%06X: orig=%s new=%02X" % (i, o, new[i]))
	if bad:
		errs.append("%d differing bytes outside writes and allowed ranges" % len(bad))
	return errs, ok

def selftest():
	orig = bytes(range(16))
	new = bytearray(orig); new[2:4] = b"\xaa\xbb"; new[10] = 0x99
	w = [(2, b"\x02\x03", b"\xaa\xbb", "text")]
	assert check(orig, bytes(new), {10}, w)[0] == []
	assert check(orig, bytes(new), set(), w)[0][-1].startswith("1 differing")          # 0x0A not covered
	assert "expects orig" in check(orig, bytes(new), {10}, [(2, b"\x00\x00", b"\xaa\xbb", "t")])[0][0]
	assert "overwritten" in check(orig, bytes(new), {10}, [(2, b"\x02\x03", b"\xaa\xcc", "t")])[0][0]
	assert "overlaps" in check(orig, bytes(new), {10}, w + [(3, b"\x03", b"\xbb", "ptr")])[0][0]
	assert check(orig, bytes(new) + b"\xff", {10}, w)[0] == []                        # 0xFF tail is unchanged
	print("selftest ok")

def main(argv):
	if argv[1:] == ["--selftest"]:
		return selftest()
	args, writes = argv[1:], []
	if "--writes" in args:
		i = args.index("--writes")
		writes = load_writes(args[i + 1])
		del args[i:i + 2]
	if len(args) < 2:
		sys.exit(__doc__)
	orig, new = (open(p, "rb").read() for p in args[:2])
	allowed = set()
	for arg in args[2:]:                       # "FFD7" or "200000-20FFFF" (inclusive, hex)
		lo, _, hi = arg.partition("-")
		lo = int(lo, 16); hi = int(hi, 16) if hi else lo
		allowed.update(range(lo, hi + 1))
	errs, ok = check(orig, new, allowed, writes)
	for e in errs:
		print(e)
	if errs:
		sys.exit(1)
	print("identical (%d bytes, %d allowed diffs, %d writes)" % (len(new), ok, len(writes)))

if __name__ == "__main__":
	main(sys.argv)
