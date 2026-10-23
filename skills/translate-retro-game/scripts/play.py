"""Turn-by-turn play for an agent playtester: each call resumes the last savestate, presses, waits, shoots, saves.

    python play.py SESSION --rom ROM [--sav FILE] [--bios FILE] [--wait 600]   new session: cold boot, wait, shoot
    python play.py SESSION a down a "right*40" "a+b" [--gap 20] [--wait 60]
    python play.py SESSION --wait 300                             no presses: just wait
    python play.py SESSION --back N                               undo the last N steps
    python play.py SESSION --export REPORT.md [--bugs docs/bugs.md] [--to DIR]   file the playtester's report
    python play.py SESSION --route [N]                            the presses of steps 0..N as one emu.py --route-str

A press is BUTTONS[*FRAMES]: "a", "a+up", "-" for none, held FRAMES frames. Buttons: SNES/GBA a b (x y) l r start
select up down left right; NDS adds lid, t<x>,<y>; PS1 cross circle square triangle l1 r1 l2 r2 ...;
(default 6), then --gap idle frames before the next press; --wait idle frames after the last one.
Prints the new step's screenshot (screens up to 480 px wide upscaled x2): read it, decide, call again.
PS1: --bios (else emu.py's env PSX_BIOS / tools/bios lookup) is kept in SESSION/bios.txt for every later call;
--sav is copied to SESSION/card.mcd, which every step boots with and keeps the game's writes in (the card is not
part of a savestate).
PSP: SESSION/memstick is the session's own memstick: empty (a new console) unless --sav seeds it on the new session.
SESSION holds rom.txt, NNNN.<state>, NNNN.png and log.tsv (step, presses), so a report can cite steps.
--every N also shoots every N frames during the step and prints contact sheets of 12 frames each first
(typed text, fades), each path followed by its frame numbers; no frame is dropped.
--export appends the report's "- [ ] step NNNN - ..." lines to --bugs under a dated heading (ROM sha1, evidence
dir) and copies the cited steps' shots, sheets and states to --to (default work/playtest/<session name>, or
work/playtest/<session name>-bugs when the session itself lives there). Ranges
"step 0038-0050" copy both ends. Run it from the game repo.
--route replays a session on another build (the fixed ROM, or the original to tell a translation bug from the
game's own): emu.py OTHER_ROM --out D --route-str "<output>" with the session's start (--sav/--state), shooting
at the end; on a build with other text lengths a press can land on another page, so check the shots line up.
Exit codes as emu.py.
"""
import argparse, datetime, glob, hashlib, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import emu, sheet  # noqa: E402

STATE_EXT = {"snes": "mss", "gba": "mss", "nds": "dst", "psx": "sstate", "psp": "ppst"}


def route(presses, gap, wait):
    steps = []
    for p in presses:
        btn, _, n = p.partition("*")
        steps += [f"{int(n or 6)} {btn}", f"{gap} -"]
    steps[-1] = f"{wait} -"  # the last gap becomes the final wait
    return ";".join(s for s in steps if not s.startswith("0 "))


def last_step(sess):
    nums = [int(m.group(1)) for f in os.listdir(sess) if (m := re.fullmatch(r"(\d{4})\.png", f))]
    return max(nums, default=-1)


def export(sess, rom, report, bugs, to):
    """Copy the cited steps' files to `to` and append the report's checklist lines to `bugs`."""
    items = []
    for ln in open(report, encoding="utf-8").read().splitlines():
        if ln.startswith("- [ ]"):
            items.append(ln)
        elif items and ln.startswith("  ") and items[-1] is not None:  # wrapped continuation of the last item
            items[-1] += "\n" + ln
        elif items:
            items.append(None)
    items = [i for i in items if i]
    if not items:
        sys.exit(f"{report}: no '- [ ] step NNNN - ...' lines")
    steps = {m for ln in items for m in re.findall(r"\b(\d{4})\b", ln)}
    os.makedirs(to, exist_ok=True)
    copied = [f for k in sorted(steps) for f in glob.glob(os.path.join(sess, f"{k}.*"))]
    for f in copied + [os.path.join(sess, "log.tsv")]:
        shutil.copy2(f, to)
    sha = hashlib.sha1(open(rom, "rb").read()).hexdigest()
    new = not os.path.exists(bugs)
    os.makedirs(os.path.dirname(bugs) or ".", exist_ok=True)
    with open(bugs, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("# Bugs\n\nTick `- [x] (fixed in <build>)` once re-checked from the cited state.\n")
        f.write(f"\n## {datetime.date.today()} playtest - {os.path.basename(rom)} sha1 {sha[:12]}\n"
                f"Evidence: `{to.replace(os.sep, '/')}/NNNN.png|.sheetK.png|.<state>`, presses in `log.tsv`.\n\n")
        f.write("\n".join(items) + "\n")
    print(f"{len(items)} bugs -> {bugs}; {len(copied)} files -> {to}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("presses", nargs="*")
    ap.add_argument("--rom", help="start a new session with this ROM")
    ap.add_argument("--sav", help="new session only: boot with a copy of this battery save / memory card / PSP save folder")
    ap.add_argument("--state", help="new session only: start from this savestate instead of a cold boot")
    ap.add_argument("--bios", help="new session only: PS1 BIOS image, reused by every later call")
    ap.add_argument("--gap", type=int, default=20)
    ap.add_argument("--wait", type=int)
    ap.add_argument("--every", type=int, default=0)
    ap.add_argument("--back", type=int, default=0)
    ap.add_argument("--export", metavar="REPORT")
    ap.add_argument("--bugs", default=os.path.join("docs", "bugs.md"))
    ap.add_argument("--to")
    ap.add_argument("--route", nargs="?", const=-1, type=int, metavar="N")
    a = ap.parse_args()
    sess = a.session

    if a.rom:
        if os.path.exists(os.path.join(sess, "rom.txt")):
            sys.exit(f"{sess} already has a session; use another dir or delete it")
        os.makedirs(sess, exist_ok=True)
        open(os.path.join(sess, "rom.txt"), "w").write(os.path.abspath(a.rom))
        if a.bios:
            open(os.path.join(sess, "bios.txt"), "w").write(os.path.abspath(a.bios))
    rom = open(os.path.join(sess, "rom.txt")).read().strip()
    ext = os.path.splitext(rom)[1].lower()
    ext = STATE_EXT["psp" if ext == ".cso" or (ext == ".iso" and emu.is_psp(rom)) else emu.SYSTEMS[ext]]
    n = last_step(sess)

    if a.export:
        to = a.to or os.path.join("work", "playtest", os.path.basename(os.path.normpath(sess)))
        if os.path.abspath(to) == os.path.abspath(sess):  # session already under work/playtest: copying onto itself fails
            to += "-bugs"
        export(sess, rom, a.export, a.bugs, to)
        return

    if a.route is not None:
        rows = [ln.split("\t") for ln in open(os.path.join(sess, "log.tsv"), encoding="utf-8").read().splitlines()]
        print(";".join(r[2] for r in rows if a.route < 0 or int(r[0]) <= a.route))
        return

    if a.back:
        for k in range(max(n - a.back + 1, 1), n + 1):  # step 0000 (the boot) is never dropped
            for f in glob.glob(os.path.join(sess, f"{k:04d}.*")):
                os.remove(f)
        n = last_step(sess)
        print(os.path.normpath(os.path.join(sess, f"{n:04d}.png")))
        return

    new = n + 1
    if new == 0:
        r = route([f"-*{a.wait or 600}"], 0, 0)
    elif a.presses:
        r = route(a.presses, a.gap, 60 if a.wait is None else a.wait)
    else:
        r = f"{a.wait or 60} -"
    # DeSmuME (JIT) shows grey for ~85 frames after a state load: idle through it, keep it out of the sheets
    warm = 90 if ext == "dst" and (new > 0 or a.state) else 0
    if warm:
        r = f"{warm} -;{r}"
    out = os.path.join(sess, "_run")
    shutil.rmtree(out, ignore_errors=True)
    cmd = [sys.executable, "-X", "utf8", os.path.join(HERE, "emu.py"), rom, "--out", out, "--route-str", r,
           "--state-out", os.path.join(sess, f"{new:04d}.{ext}")]
    card = os.path.join(sess, "card.mcd")
    if new == 0 and a.sav and ext == "sstate":
        shutil.copy(a.sav, card)
    if ext == "sstate" and os.path.exists(card):  # PS1: states don't hold the memory card; boot every step with it
        cmd += ["--sav", card]
    elif new == 0 and a.sav:
        cmd += ["--sav", a.sav]
    if new == 0:
        cmd += ["--state-in", a.state] if a.state else []
    else:
        cmd += ["--state-in", os.path.join(sess, f"{n:04d}.{ext}")]
    if ext == "ppst":  # the session's own memstick: in-game saves stay out of the shared one
        cmd += ["--memstick", os.path.join(sess, "memstick")]
    if os.path.exists(os.path.join(sess, "bios.txt")):
        cmd += ["--bios", open(os.path.join(sess, "bios.txt")).read().strip()]
    if a.every:
        cmd += ["--shot-every", str(a.every)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        sys.exit(res.stdout + res.stderr + f"\nemu.py exit {res.returncode}; session unchanged")
    if os.path.exists(os.path.join(out, "memcard1.mcd")):  # the step's in-game saves carry on to the next step
        shutil.copy(os.path.join(out, "memcard1.mcd"), card)

    img = sheet.read_png(os.path.join(out, "final.png"))
    png = os.path.join(sess, f"{new:04d}.png")
    zoom = 2 if img[0] <= 480 else 1  # up to PSP width
    sheet.sheet([sheet.zoom(img, zoom)], 1, png)
    with open(os.path.join(sess, "log.tsv"), "a", encoding="utf-8") as f:
        f.write(f"{new:04d}\t{' '.join(a.presses) or 'wait'}\t{r}\n")
    if a.every:
        shots = [f for f in sorted(glob.glob(os.path.join(out, "f[0-9]*.png")))  # final.png is the step shot already
                 if sheet.frame_no(f) > warm]
        for i in range(0, len(shots), 12):  # 3x4 tiles at x2 stays readable; more per sheet gets downscaled
            part = shots[i:i + 12]
            path = os.path.join(sess, f"{new:04d}.sheet{i // 12 + 1}.png")
            # x2 tiles only up to 320 px: 3 wider ones at x2 get downscaled by the reader anyway
            sheet.sheet([sheet.zoom(sheet.read_png(f), 2 if img[0] <= 320 else 1) for f in part], 3, path)
            print(os.path.normpath(path), " ".join(os.path.basename(f)[:-4] for f in part))
    print(os.path.normpath(png))  # last line: the step's own shot, also with --every


if __name__ == "__main__":
    main()
