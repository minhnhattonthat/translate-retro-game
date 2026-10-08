"""romdiff.py ORIG NEW [HEX | HEX-HEX ...]   (allowed offsets / inclusive ranges)
Exit 0 if NEW == ORIG except at allowed offsets; extra bytes in NEW must be 0xFF unless allowed.
Exit 1 on unexpected differences, 2 on bad input.

Catches edits that land outside the regions you meant to touch (pointer tables, text banks, free space): the bug
class where a patch overwrites flag bytes or graphics and every unit test still passes. Keep the allowed ranges in
a file (one range + comment per line), not a single long Makefile line."""
import sys

def main(argv):
	if len(argv) < 3:
		sys.exit(__doc__)
	orig, new = (open(p, "rb").read() for p in argv[1:3])
	allowed = set()
	for arg in argv[3:]:                       # "FFD7" or "200000-20FFFF" (inclusive, hex)
		lo, _, hi = arg.partition("-")
		lo = int(lo, 16); hi = int(hi, 16) if hi else lo
		allowed.update(range(lo, hi + 1))
	if len(new) < len(orig):
		print("NEW is shorter than ORIG (%d < %d)" % (len(new), len(orig)))
		sys.exit(1)
	bad, ok = [], 0
	for i in range(len(new)):
		differs = orig[i] != new[i] if i < len(orig) else new[i] != 0xFF
		if not differs:
			continue
		if i in allowed:
			ok += 1
		else:
			bad.append(i)
	for i in bad[:50]:
		o = ("%02X" % orig[i]) if i < len(orig) else "--"
		print("0x%06X: orig=%s new=%02X" % (i, o, new[i]))
	if bad:
		print("%d differing bytes" % len(bad))
		sys.exit(1)
	print("identical (%d bytes, %d allowed diffs)" % (len(new), ok))

if __name__ == "__main__":
	main(sys.argv)
