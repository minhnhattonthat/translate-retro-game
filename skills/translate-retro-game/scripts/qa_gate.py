"""Visual-QA gate: every contact sheet in the QA tour gets a verdict from a read-only reviewer before release.

    python qa_gate.py init  work/qa/manifest.tsv work/qa/tour [more dirs..] [--glob "*sheet*.png"] [--build build/game.sfc]
    python qa_gate.py todo  work/qa/manifest.tsv work/qa/verdicts [--size 30] [--out-dir work/qa/chunks]
    python qa_gate.py check work/qa/manifest.tsv work/qa/verdicts
    python qa_gate.py waive work/qa/manifest.tsv "why this build needs no new tour"

init   adds every matching PNG under the dirs to the manifest, one "id<TAB>path<TAB>sha1<TAB>changed" line (id = path
       relative to the first dir, without extension), and re-hashes the sheets already in it. Re-run it after every
       tour: a sheet whose pixels changed gets a new "changed" time, and verdicts written before that no longer
       count. Unchanged sheets keep theirs. --build records the hash of the ROM the tour ran on (MANIFEST.build).
todo   lists the sheets with no current verdict, in chunks of --size: one chunk = one visual-QA subagent. Prints them,
       or with --out-dir writes one chunk_NNN.txt per chunk (paths only) and prints the file names. The count goes
       to stderr.
check  exit 1 unless every manifest id has a current verdict "ok" or "fixed", and no sheet changed since init; and,
       when init recorded a build, unless that file still has the recorded hash. Sheets alone can't show this: with no
       new tour they stay unchanged, and their verdicts pass on a build nobody looked at.
       A verdict file is TSV "id<TAB>ok|issue|fixed<TAB>note"; every *.tsv under the verdicts dir is read, oldest file
       first, so a later line for the same id (a re-check after a fix) overrides an earlier "issue".
waive  accepts the current build without a new tour, for a hotfix whose scenes were re-checked some other way. The
       reason is recorded in MANIFEST.waive and holds for this exact build only.
Each visual-QA subagent writes its own verdicts/<chunk>.tsv with its file-write tool, so parallel reviewers never
share a file. references/emulator-qa.md §Visual QA has the dispatch; assets/visual-qa-brief.md is the brief.
"""
import argparse, glob, hashlib, os, sys, time

GOOD = {"ok", "fixed"}


def sha1(path):
    if not os.path.exists(path):
        return "missing"
    h = hashlib.sha1()
    with open(path, "rb") as f:  # in chunks: a disc image can be over 1 GB
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def recorded_build(manifest):
    """(sha1, absolute path) from MANIFEST.build, or None. The path is stored relative to the manifest."""
    try:
        with open(manifest + ".build", encoding="utf-8") as f:
            digest, rel = f.read().rstrip("\n").split("\t", 1)
    except OSError:
        return None
    return digest, os.path.join(os.path.dirname(os.path.abspath(manifest)), rel)


def stale_build(manifest):
    """Why the sheets don't show the current build, or None. Prints an accepted waiver."""
    rec = recorded_build(manifest)
    if rec is None:
        return None
    digest, path = rec
    now = sha1(path)
    if now == digest:
        return None
    try:
        with open(manifest + ".waive", encoding="utf-8") as f:
            waived, reason = f.read().rstrip("\n").split("\t", 1)
    except (OSError, ValueError):
        waived, reason = "", ""
    if waived == now and reason.strip():
        print(f"WAIVED      build {now[:8]} has no tour: {reason}")
        return None
    return (f"STALE       the tour ran on build {digest[:8]}, but {path} is now {now[:8]}: re-run the tour and "
            f'init --build, or for a hotfix: qa_gate.py waive {manifest} "<reason>"')


def waive(manifest, reason):
    rec = recorded_build(manifest)
    if rec is None or not reason.strip():
        print("waive needs a reason and a manifest whose init recorded --build")
        return 1
    now = sha1(rec[1])
    with open(manifest + ".waive", "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{now}\t{reason.strip()}\n")
    print(f"waived for build {now[:8]}")
    return 0


def read_manifest(path):
    """id -> [path, sha1, changed]; older two-column manifests read with no hash and changed 0."""
    if not os.path.exists(path):
        return {}
    out = {}
    for line in open(path, encoding="utf-8"):
        r = line.rstrip("\n").split("\t")
        if len(r) >= 2 and r[0]:
            out[r[0]] = [r[1], r[2] if len(r) > 2 else "", float(r[3]) if len(r) > 3 else 0.0]
    return out


def read_verdicts(vdir):
    """id -> (verdict, note, file, file mtime); files read oldest first, so later lines win."""
    out = {}
    files = sorted(glob.glob(os.path.join(vdir, "**", "*.tsv"), recursive=True), key=lambda f: (os.path.getmtime(f), f))
    for f in files:
        mt = os.path.getmtime(f)
        for n, line in enumerate(open(f, encoding="utf-8-sig"), 1):
            r = [c.strip() for c in line.rstrip("\n").split("\t")]
            if len(r) < 2 or not r[0] or r[0].startswith("#"):
                continue
            out[r[0]] = (r[1].lower(), r[2] if len(r) > 2 else "", f"{f}:{n}", mt)
    return out


def init(manifest, dirs, pattern, build=None):
    known = read_manifest(manifest)
    base, now = dirs[0], time.time()
    new = changed = 0
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "**", pattern), recursive=True)):
            i = os.path.splitext(os.path.relpath(p, base))[0].replace("\\", "/")
            if i not in known:
                known[i] = [p, "", 0.0]
                new += 1
    for i, row in known.items():
        h = sha1(row[0])
        if h != row[1]:
            changed += bool(row[1])  # a first hash (new sheet, old manifest) is not a change
            row[1:] = [h, now if row[1] else row[2]]
    os.makedirs(os.path.dirname(manifest) or ".", exist_ok=True)
    with open(manifest, "w", encoding="utf-8", newline="\n") as f:
        for i, (p, h, t) in known.items():
            f.write(f"{i}\t{p}\t{h}\t{t:.3f}\n")
    if build:
        if not os.path.exists(build):
            print(f"--build: {build} does not exist")
            return 1
        rel = os.path.relpath(os.path.abspath(build), os.path.dirname(os.path.abspath(manifest)))
        with open(manifest + ".build", "w", encoding="utf-8", newline="\n") as f:
            f.write(f"{sha1(build)}\t{rel}\n")
    print(f"{new} sheets added, {changed} changed since their verdicts, {len(known)} in manifest")
    if not new and not known:
        pngs = sum(len(glob.glob(os.path.join(d, "**", "*.png"), recursive=True)) for d in dirs)
        print(f"warning: no file matched --glob {pattern!r}" + (f" ({pngs} PNGs there: pass --glob)" if pngs else ""))
    return 0


def problems(manifest, vdir):
    """manifest, ids with no current verdict, (id, verdict) not ok, ids whose sheet changed after init."""
    m, v = read_manifest(manifest), read_verdicts(vdir)
    missing = [i for i in m if i not in v or v[i][3] < m[i][2]]
    bad = [(i, v[i]) for i in m if i not in missing and v[i][0] not in GOOD]
    moved = [i for i in m if m[i][1] and sha1(m[i][0]) != m[i][1]]
    return m, missing, bad, moved


def todo(manifest, vdir, size, out_dir=None):
    m, missing, _, moved = problems(manifest, vdir)
    chunks = [missing[k:k + size] for k in range(0, len(missing), size)]
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        for old in glob.glob(os.path.join(out_dir, "chunk_*.txt")):
            os.remove(old)
    for n, part in enumerate(chunks):
        if out_dir:
            path = os.path.join(out_dir, f"chunk_{n:03d}.txt").replace("\\", "/")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(f"{i}\t{m[i][0]}\n".replace("\\", "/") for i in part))
            print(path)
        else:
            print(f"# chunk {n:03d}")
            for i in part:
                print(f"{i}\t{m[i][0]}")
    print(f"{len(missing)} of {len(m)} sheets without a current verdict", file=sys.stderr)
    if moved:
        print(f"warning: {len(moved)} sheets changed since init; re-run init first", file=sys.stderr)
    return 0


def check(manifest, vdir):
    m, missing, bad, moved = problems(manifest, vdir)
    if not m:
        print("manifest empty: run init after the QA tour")
        return 1
    for i in moved[:50]:
        print(f"CHANGED     {i}  {m[i][0]}  (sheet differs from init: re-run init, then review it)")
    for i in missing[:50]:
        print(f"NO VERDICT  {i}  {m[i][0]}")
    for i, (verdict, note, where, _) in bad:
        print(f"{verdict.upper():10s}  {i}  {note}  ({where})")
    print(f"{len(m)} sheets: {len(missing)} without a current verdict, {len(bad)} not ok, {len(moved)} changed since init")
    stale = stale_build(manifest)
    if stale:
        print(stale)
    return 1 if missing or bad or moved or stale else 0


def _selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tour, vd, man = os.path.join(d, "tour"), os.path.join(d, "verdicts"), os.path.join(d, "manifest.tsv")
        os.makedirs(os.path.join(tour, "s01"))
        os.makedirs(vd)

        def put(name, data, stamp=None):
            open(name, "wb" if isinstance(data, bytes) else "w").write(data)
            if stamp:
                os.utime(name, (stamp, stamp))
        for n in ("s01/sheet", "s02_sheet"):
            put(os.path.join(tour, n + ".png"), b"a")
        assert init(man, [tour], "*sheet*.png") == 0 and init(man, [tour], "*sheet*.png") == 0
        assert sorted(read_manifest(man)) == ["s01/sheet", "s02_sheet"]
        assert check(man, vd) == 1
        t = time.time()  # verdict files stamped in the past, so the re-init below is newer than them
        put(os.path.join(vd, "c000.tsv"), "s01/sheet\tok\t\ns02_sheet\tissue\toverflow\n", t - 20)
        assert check(man, vd) == 1
        put(os.path.join(vd, "recheck.tsv"), "s02_sheet\tfixed\tre-wrapped\n", t - 10)
        assert check(man, vd) == 0
        put(os.path.join(tour, "s01/sheet.png"), b"b")  # a new tour changed one sheet
        assert check(man, vd) == 1  # changed since init
        init(man, [tour], "*sheet*.png")
        assert problems(man, vd)[1] == ["s01/sheet"]  # its old verdict no longer counts; s02's still does
        todo(man, vd, 30, os.path.join(d, "chunks"))
        assert open(os.path.join(d, "chunks", "chunk_000.txt")).read().startswith("s01/sheet\t")
        put(os.path.join(vd, "c001.tsv"), "s01/sheet\tok\t\n", time.time() + 30)
        assert check(man, vd) == 0
        rom = os.path.join(d, "game.sfc")  # a rebuild with no new tour: every sheet unchanged, so only the hash tells
        put(rom, b"build 1")
        assert waive(man, "no build recorded") == 1
        assert init(man, [tour], "*sheet*.png", rom) == 0 and check(man, vd) == 0
        put(rom, b"build 2")
        assert check(man, vd) == 1
        assert waive(man, "  ") == 1 and check(man, vd) == 1
        assert waive(man, "text-only hotfix, route re-checked") == 0 and check(man, vd) == 0
        put(rom, b"build 3")
        assert check(man, vd) == 1  # a waiver holds for one build
        put(rom, b"build 1")
        assert check(man, vd) == 0  # a rebuild from the same source passes
        os.remove(rom)
        assert check(man, vd) == 1
    print("selftest ok")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["init", "todo", "check", "waive"])
    ap.add_argument("manifest")
    ap.add_argument("paths", nargs="+", help="init: tour dirs; todo/check: the verdicts dir; waive: the reason")
    ap.add_argument("--glob", default="*sheet*.png")
    ap.add_argument("--size", type=int, default=30)
    ap.add_argument("--out-dir", help="todo: write chunk_NNN.txt files here instead of printing the chunks")
    ap.add_argument("--build", help="init: the ROM or disc image the tour ran on")
    a = ap.parse_args(argv)
    if a.cmd == "init":
        return init(a.manifest, a.paths, a.glob, a.build)
    if a.cmd == "waive":
        return waive(a.manifest, " ".join(a.paths))
    if a.cmd == "todo":
        return todo(a.manifest, a.paths[0], a.size, a.out_dir)
    return check(a.manifest, a.paths[0])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit(main())
