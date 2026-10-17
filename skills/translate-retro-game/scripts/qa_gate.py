"""Visual-QA gate: every contact sheet in the QA tour gets a verdict from a read-only reviewer before release.

    python qa_gate.py init  work/qa/manifest.tsv work/qa/tour [more dirs..] [--glob "*sheet*.png"]
    python qa_gate.py todo  work/qa/manifest.tsv work/qa/verdicts [--size 30]
    python qa_gate.py check work/qa/manifest.tsv work/qa/verdicts

init   adds every matching PNG under the dirs to the manifest, one "id<TAB>path" line (id = path relative to the
       first dir, without extension). Existing lines are kept, so re-running after a new tour only appends.
todo   prints the sheets with no verdict yet, in chunks of --size: one chunk = one visual-QA subagent.
check  exit 1 unless every manifest id has a final verdict "ok" or "fixed". A verdict file is TSV
       "id<TAB>ok|issue|fixed<TAB>note"; every *.tsv under the verdicts dir is read, oldest file first, so a
       later line for the same id (a re-check after a fix) overrides an earlier "issue".
Each visual-QA subagent writes its own verdicts/<chunk>.tsv with its file-write tool, so parallel reviewers never
share a file. references/emulator-qa.md §Visual QA has the dispatch.
"""
import argparse, glob, os, sys

GOOD = {"ok", "fixed"}


def read_manifest(path):
    if not os.path.exists(path):
        return {}
    rows = (line.rstrip("\n").split("\t") for line in open(path, encoding="utf-8"))
    return {r[0]: r[1] for r in rows if len(r) >= 2 and r[0]}


def read_verdicts(vdir):
    """id -> (verdict, note, file); files read oldest first, so later lines win."""
    out = {}
    files = sorted(glob.glob(os.path.join(vdir, "**", "*.tsv"), recursive=True), key=lambda f: (os.path.getmtime(f), f))
    for f in files:
        for n, line in enumerate(open(f, encoding="utf-8-sig"), 1):
            r = [c.strip() for c in line.rstrip("\n").split("\t")]
            if len(r) < 2 or not r[0] or r[0].startswith("#"):
                continue
            out[r[0]] = (r[1].lower(), r[2] if len(r) > 2 else "", f"{f}:{n}")
    return out


def init(manifest, dirs, pattern):
    known = read_manifest(manifest)
    base = dirs[0]
    new = []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "**", pattern), recursive=True)):
            i = os.path.splitext(os.path.relpath(p, base))[0].replace("\\", "/")
            if i not in known:
                known[i] = p
                new.append((i, p))
    os.makedirs(os.path.dirname(manifest) or ".", exist_ok=True)
    with open(manifest, "a", encoding="utf-8") as f:
        for i, p in new:
            f.write(f"{i}\t{p}\n")
    print(f"{len(new)} sheets added, {len(known)} in manifest")
    return 0


def problems(manifest, vdir):
    m, v = read_manifest(manifest), read_verdicts(vdir)
    missing = [i for i in m if i not in v]
    bad = [(i, v[i]) for i in m if i in v and v[i][0] not in GOOD]
    return m, missing, bad


def todo(manifest, vdir, size):
    m, missing, _ = problems(manifest, vdir)
    for k in range(0, len(missing), size):
        print(f"# chunk {k // size:03d}")
        for i in missing[k:k + size]:
            print(f"{i}\t{m[i]}")
    print(f"{len(missing)} of {len(m)} sheets without a verdict")
    return 0


def check(manifest, vdir):
    m, missing, bad = problems(manifest, vdir)
    if not m:
        print("manifest empty: run init after the QA tour")
        return 1
    for i in missing[:50]:
        print(f"NO VERDICT  {i}  {m[i]}")
    for i, (verdict, note, where) in bad:
        print(f"{verdict.upper():10s}  {i}  {note}  ({where})")
    print(f"{len(m)} sheets: {len(missing)} without verdict, {len(bad)} not ok")
    return 1 if missing or bad else 0


def _selftest():
    import tempfile, time
    with tempfile.TemporaryDirectory() as d:
        tour, vd = os.path.join(d, "tour"), os.path.join(d, "verdicts")
        os.makedirs(os.path.join(tour, "s01"))
        os.makedirs(vd)
        for n in ("s01/sheet", "s02_sheet"):
            open(os.path.join(tour, n + ".png"), "wb").close()
        man = os.path.join(d, "manifest.tsv")
        init(man, [tour], "*sheet*.png")
        init(man, [tour], "*sheet*.png")
        assert sorted(read_manifest(man)) == ["s01/sheet", "s02_sheet"]
        assert check(man, vd) == 1
        open(os.path.join(vd, "c000.tsv"), "w", encoding="utf-8").write("s01/sheet\tok\t\ns02_sheet\tissue\toverflow\n")
        assert check(man, vd) == 1
        time.sleep(0.05)
        open(os.path.join(vd, "recheck.tsv"), "w", encoding="utf-8").write("s02_sheet\tfixed\tre-wrapped\n")
        assert check(man, vd) == 0
    print("selftest ok")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["init", "todo", "check"])
    ap.add_argument("manifest")
    ap.add_argument("paths", nargs="+", help="init: tour dirs; todo/check: the verdicts dir")
    ap.add_argument("--glob", default="*sheet*.png")
    ap.add_argument("--size", type=int, default=30)
    a = ap.parse_args(argv)
    if a.cmd == "init":
        return init(a.manifest, a.paths, a.glob)
    if a.cmd == "todo":
        return todo(a.manifest, a.paths[0], a.size)
    return check(a.manifest, a.paths[0])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit(main())
