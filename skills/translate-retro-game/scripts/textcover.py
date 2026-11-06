"""Text coverage: which strings a warp or tour run reached, so a release can't ship text nobody displayed.

    python -X utf8 textcover.py LOGDIR STRINGS.tsv [--waive docs/text_unshown.tsv] [--mask 0x7FFFFF]

STRINGS.tsv  one "id<TAB>hex address" per string, written by the build from its own layout (the address the game
             reads the string's first byte from, so it follows relocation).
LOGDIR       searched for log.txt files holding "TEXT <hex address>" lines: lua/probes/textcover.lua on Mesen, or
             the same line logged from the project's own text hook on other emulators.
--waive      "id<TAB>reason" lines: strings accepted as unreachable. A line with no reason doesn't count.
--mask       AND applied to both sides, for bank mirrors ($03 and $83 on SNES: 0x7FFFFF).

Prints each string never shown; exit 1 if any isn't waived. A string counts as shown when the game read its first
byte, which proves it was reached, not that it drew correctly: that stays with visual QA.
"""
import argparse, glob, os, re, sys

TEXT = re.compile(r"^TEXT ([0-9A-Fa-f]+)", re.M)


def shown(logdir, mask):
    out = set()
    for log in glob.glob(os.path.join(logdir, "**", "log.txt"), recursive=True):
        with open(log, encoding="utf-8", errors="replace") as f:
            out.update(int(a, 16) & mask for a in TEXT.findall(f.read()))
    return out


def read_rows(path):
    """Non-comment lines of a TSV, split into cells."""
    with open(path, encoding="utf-8-sig") as f:
        return [r for r in (line.rstrip("\n").split("\t") for line in f) if r[0] and not r[0].startswith("#")]


def report(logdir, strings, waive=None, mask=0xFFFFFFFF):
    table = {r[0]: int(r[1], 16) & mask for r in read_rows(strings)}
    waived = {r[0]: r[1].strip() for r in read_rows(waive) if len(r) > 1 and r[1].strip()} if waive else {}
    seen = shown(logdir, mask)
    missing = [i for i, a in table.items() if a not in seen]
    bad = [i for i in missing if i not in waived]
    for i in bad:
        print(f"NEVER SHOWN  {i}  {table[i]:X}")
    print(f"{len(table) - len(missing)}/{len(table)} strings shown, {len(missing) - len(bad)} waived, {len(bad)} failing")
    if not table:
        print("no strings listed: check STRINGS.tsv")
        return 1
    return 1 if bad else 0


def _selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        logs, tsv, wv = os.path.join(d, "cover", "s1"), os.path.join(d, "s.tsv"), os.path.join(d, "w.tsv")
        os.makedirs(logs)
        with open(os.path.join(logs, "log.txt"), "w") as f:
            f.write("TEXT 83AA38 f10\nnoise\nTEXT 03BB00 f20\n")
        with open(tsv, "w") as f:
            f.write("# id\taddr\na\t83AA38\nb\t83BB00\nc\t83CC00\n")
        cover = os.path.join(d, "cover")
        assert report(cover, tsv) == 1  # b is only reached through the mirror, c never
        assert report(cover, tsv, mask=0x7FFFFF) == 1  # c still missing
        with open(wv, "w") as f:
            f.write("c\t\n")
        assert report(cover, tsv, wv, 0x7FFFFF) == 1  # a waiver with no reason doesn't count
        with open(wv, "w") as f:
            f.write("c\tdebug-only string\n")
        assert report(cover, tsv, wv, 0x7FFFFF) == 0
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logdir")
    ap.add_argument("strings")
    ap.add_argument("--waive")
    ap.add_argument("--mask", type=lambda s: int(s, 0), default=0xFFFFFFFF)
    a = ap.parse_args()
    return report(a.logdir, a.strings, a.waive, a.mask)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit(main())
