"""Headless emulator runs for translation QA: boot a ROM, play a route, screenshot, exit with a real code.

    python emu.py ROM --out DIR [--route FILE | --route-str "900 -;4 start;300 -"] [--frames N]
                  [--shot-every N] [--shots 120,600] [--state-in S] [--state-out S] [--state-every N]
                  [--sav FILE] [--mash N] [--mash-key KEY] [--script hooks.lua].. [--var NAME=LUA]..
                  [--emu EXE] [--bios BIN] [--debugger] [--timeout SEC] [--sheet] [--smoke]

System from the ROM extension:
  .sfc/.smc          -> Mesen (MesenCE or Mesen2; --testRunner, no window)
  .gba               -> Mesen when <Mesen dir>/Firmware/gba_bios.bin exists (no window; exec hooks; Lua states),
                        else mGBA (HLE BIOS; Qt window opens). --emu picks either.
  .nds               -> DeSmuME. QA fork (has --headless): no window, own ini per run, PNG shots, path states,
                        exec hooks under JIT. Stock: window opens, Lua via lua51.dll beside the exe, shared
                        desmume.ini edited then restored, slot states, --debugger needed for exec hooks
  .iso/.cso with /PSP_GAME -> PPSSPP via psp.py (window hidden, WebSocket debugger; Windows; --state-in/--state-out are
                        PPSSPP .ppst states, extra flags: --clean-saves --fast --show, see psp.py --help)
  .cue/.bin/.iso/.chd -> PCSX-Redux (-no-ui; SPU muted, 8x speed; --bios or env PSX_BIOS, else OpenBIOS)
Route: one step per line, "FRAMES BUTTONS" with BUTTONS "-" (none) or "a+start+up"; "#" starts a comment.
NDS adds "t128,96" (touch the bottom screen at x,y). PS1 buttons: cross circle square triangle l1 r1 l2 r2 ...
The run stops after --frames frames, or when the route ends. Writes DIR/f000120.png..., DIR/final.png, DIR/log.txt.
--smoke fails (exit 3) when final.png is a single flat colour: the black-screen boot check.
--sav copies a battery save (.srm/.sav/.dsv) or PS1 memory card (.mcd) into the run fresh each time; the original
is never written. --state-every N writes DIR/s<frame>.<ext> every N frames (not NDS).
--script (repeatable) appends Lua after the driver; --var NAME=LUA sets a global first (--var WATCH_LO=0x7E1000).
Lua API: L.on_frame(fn(n)), L.log(s), L.shot(name), L.on_exec(..), L.on_read/L.on_write(lo, hi, fn), L.pc(),
L.dump_ppu(prefix), L.dump_ram(path), plus the emulator's own API. Ready-made probes: scripts/lua/probes/.

Exit codes: 0 ok, 2 Lua error (message printed), 3 smoke failed, 124 timeout, other = emulator failure.
Emulator lookup: --emu, then env MESEN / MGBA / DESMUME / PCSX_REDUX / PPSSPP, then tools/**/<exe> under the current repo
and its sibling repos.
"""
import argparse, configparser, glob, json, os, shutil, struct, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sheet as sheetmod  # noqa: E402

SYSTEMS = {".sfc": "snes", ".smc": "snes", ".gba": "gba", ".nds": "nds",
           ".cue": "psx", ".bin": "psx", ".iso": "psx", ".chd": "psx", ".cso": "psp"}
EXE = {"snes": ("MESEN", "Mesen.exe"), "gba": ("MGBA", "mGBA.exe"), "nds": ("DESMUME", "DeSmuME*.exe"),
       "psx": ("PCSX_REDUX", "pcsx-redux.exe")}
LIB = {"snes": "mesen_lib.lua", "gba": "mgba_lib.lua", "nds": "desmume_lib.lua", "psx": "pcsx_lib.lua"}
MASH_KEY = {"psx": "cross"}
MESEN_SETTINGS = '{"Debug": {"ScriptWindow": {"AllowIoOsAccess": true}}}'
DS_SLOT_IN, DS_SLOT_OUT = 9, 8


def find_emu(system, required=True):
    env, name = EXE[system]
    if os.environ.get(env):
        return os.environ[env]
    for pattern in (os.path.join("tools", "**", name), os.path.join("..", "*", "tools", "**", name)):
        hits = sorted(glob.glob(pattern, recursive=True))
        if hits:
            return os.path.abspath(hits[0])
    if required:
        sys.exit(f"{name} not found: pass --emu or set {env}")


def lua_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_value(x) for x in v) + "}"
    return json.dumps(str(v).replace("\\", "/"))  # JSON string escapes are valid Lua


def read_route(path):
    steps = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if line:
            n, spec = line.split()
            steps.append([int(n), spec])
    return steps


def mesen_portable(exe):
    """settings.json beside Mesen.exe = portable mode (no first-run wizard) and Lua io access for screenshots."""
    path = os.path.join(os.path.dirname(exe), "settings.json")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(MESEN_SETTINGS)
    elif '"AllowIoOsAccess": true' not in open(path, encoding="utf-8", errors="replace").read():
        print(f"warning: {path} lacks AllowIoOsAccess=true; screenshots will fail", file=sys.stderr)


def mesen_state(exe, state, out):
    """Mesen loads a state black when its header version ("MSS" + u32 at byte 3) differs from its own, e.g. one
    from the user's newer Mesen. Return the state, or a copy in out/ stamped with this exe's version."""
    d = open(state, "rb").read()
    exe_bytes = open(exe, "rb").read()
    i = exe_bytes.rfind(struct.pack("<I", 0xFEEF04BD))  # VS_FIXEDFILEINFO: FileVersion
    if d[:3] != b"MSS" or i < 0:
        return state
    ms, ls = struct.unpack("<II", exe_bytes[i + 8:i + 16])
    ver = struct.pack("<I", (ms >> 16) << 16 | (ms & 0xFFFF) << 8 | ls >> 16)
    if d[3:7] == ver:
        return state
    print(f"warning: {os.path.basename(state)} is from Mesen {d[5]}.{d[4]}.{d[3]}, this one is "
          f"{ver[2]}.{ver[1]}.{ver[0]}: loading a re-stamped copy; if it still loads black, pass that Mesen "
          "with --emu", file=sys.stderr)
    fixed = os.path.join(out, "_state_in.mss")
    open(fixed, "wb").write(d[:3] + ver + d[7:])
    return fixed


def desmume_ini(exe, out, battery):
    """DeSmuME has no Lua CLI flag: with [Scripting] AutoLoad=1 it runs <[PathSettings] Lua>/<rom name>.lua when the
    ROM loads. Point Lua and StateSlots (and Battery for --sav) at the run dir, keep emulating when unfocused, and
    run unthrottled (Lua speedmode alone stays at 60 fps). Returns the ini path and its old bytes."""
    if not os.path.exists(os.path.join(os.path.dirname(exe), "lua51.dll")):
        sys.exit("lua51.dll must sit beside the DeSmuME exe: LuaBinaries lua-5.1.5_Win64_dll17_lib.zip, "
                 "rename lua5.1.dll to lua51.dll (references/setup.md)")
    path = os.path.join(os.path.dirname(exe), "desmume.ini")
    old = open(path, "rb").read() if os.path.exists(path) else None
    c = configparser.RawConfigParser(strict=False)
    c.optionxform = str
    if old:
        c.read_string(old.decode("utf-16"))
    sets = [("Scripting", "AutoLoad", "1"), ("PathSettings", "Lua", out), ("PathSettings", "StateSlots", out),
            ("Main", "BackgroundPause", "0"), ("FrameLimit", "FrameLimit", "0")]
    for sec, key, val in sets + ([("PathSettings", "Battery", out)] if battery else []):
        if not c.has_section(sec):
            c.add_section(sec)
        c.set(sec, key, val)
    with open(path, "w", encoding="utf-16") as f:
        c.write(f, space_around_delimiters=False)
    return path, old


def kill_tree(p):
    """A timeout kills only the child; PCSX-Redux's launcher leaves pcsx-redux.main running."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    p.kill()


def to_png(path):
    """DeSmuME .gd (big-endian header, ARGB) and the PCSX driver's .psx (w, h, bpp + 15/24-bit pixels) -> .png."""
    d = open(path, "rb").read()
    if path.endswith(".gd"):
        w, h = struct.unpack(">HH", d[2:6])
        rows = []
        for y in range(h):
            src, rgb = d[11 + y * w * 4:11 + (y + 1) * w * 4], bytearray(w * 3)
            rgb[0::3], rgb[1::3], rgb[2::3] = src[1::4], src[2::4], src[3::4]
            rows.append(bytes(rgb))
    else:
        w, h, bpp = struct.unpack("<HHB", d[:5])
        px = d[5:]
        if not w or not h:  # display off (PCSX returns 0x0): store one black pixel so --smoke reads it as blank
            w, h, rows = 1, 1, [b"\0\0\0"]
        elif bpp:
            rows = [px[y * w * 3:(y + 1) * w * 3] for y in range(h)]
        else:
            lut = [bytes(((v & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v >> 10 & 31) * 255 // 31))
                   for v in range(32768)]
            vals = struct.unpack(f"<{w * h}H", px[:w * h * 2])
            rows = [b"".join(lut[v & 0x7FFF] for v in vals[y * w:(y + 1) * w]) for y in range(h)]
    sheetmod.write_png(os.path.splitext(path)[0] + ".png", w, h, rows)
    os.remove(path)


def is_psp(path):
    """A PSP UMD image: ISO9660 whose root directory names PSP_GAME (CSO is compressed: go by the extension)."""
    if path.lower().endswith(".cso"):
        return True
    with open(path, "rb") as f:
        f.seek(16 * 2048)
        return b"PSP_GAME" in f.read(64 * 2048)


def run_psp(a):
    import psp
    argv = [a.rom, "--out", a.out, "--timeout", str(a.timeout)]
    for flag, val in (("--route", a.route), ("--route-str", a.route_str), ("--frames", a.frames), ("--shots", a.shots),
                      ("--shot-every", a.shot_every or None), ("--state", a.state_in), ("--save-state", a.state_out),
                      ("--emu", a.emu)):
        if val:
            argv += [flag, str(val)]
    for flag, on in (("--smoke", a.smoke), ("--sound", a.sound), ("--fast", a.fast), ("--show", a.show), ("--clean-saves", a.clean_saves)):
        if on:
            argv.append(flag)
    try:
        psp.main(argv)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 2
    else:
        code = 0
    if a.sheet and code in (0, 3) and glob.glob(os.path.join(a.out, "f[0-9]*.png")):
        sheetmod.make(a.out, changed=0.02)
    return code


def run(a):
    ext = os.path.splitext(a.rom)[1].lower()
    if ext in (".iso", ".cso") and is_psp(a.rom):
        return run_psp(a)
    system = SYSTEMS.get(ext)
    if not system:
        sys.exit(f"unsupported ROM type {ext}")
    if not (a.route or a.route_str or a.frames):
        sys.exit("give --route, --route-str or --frames")
    exe = a.emu
    if system == "gba" and not exe:  # Mesen first (no window, exec hooks, Lua savestates) if it has the BIOS
        m = find_emu("snes", required=False)
        exe = m if m and os.path.exists(os.path.join(os.path.dirname(m), "Firmware", "gba_bios.bin")) else None
    exe = exe or find_emu(system)
    mesen = os.path.basename(exe).lower().startswith("mesen")
    if mesen and system == "gba" and not os.path.exists(os.path.join(os.path.dirname(exe), "Firmware", "gba_bios.bin")):
        sys.exit("Mesen has no built-in GBA BIOS (games boot black): put the user's console dump at "
                 f"{os.path.join(os.path.dirname(exe), 'Firmware', 'gba_bios.bin')}, or pass --emu mGBA.exe")
    # the QA fork of DeSmuME (references/setup.md) adds --headless/--ini/--lua, path savestates, PNG shots, JIT exec hooks
    dsfork = system == "nds" and b"--headless" in open(exe, "rb").read()
    if a.state_every and system == "nds" and not dsfork:
        sys.exit("--state-every: stock DeSmuME saves numbered slots only; use the QA fork or --state-out per route")
    out = os.path.abspath(a.out)
    rom = os.path.abspath(a.rom)
    stem = os.path.splitext(os.path.basename(rom))[0]
    os.makedirs(out, exist_ok=True)
    if a.state_out:
        os.makedirs(os.path.dirname(os.path.abspath(a.state_out)), exist_ok=True)
    for old in glob.glob(os.path.join(out, "f[0-9]*.*")) + [os.path.join(out, n) for n in ("final.png", "lua_error.txt")]:
        if os.path.exists(old):
            os.remove(old)
    route = a.route and os.path.abspath(a.route)
    if a.route_str:
        route = os.path.join(out, "route.txt")
        with open(route, "w") as f:
            f.write("\n".join(s.strip() for s in a.route_str.split(";")) + "\n")
    shots = [int(x) for x in a.shots.split(",")] if a.shots else None
    end = a.frames or (route and sum(n for n, _ in read_route(route)))
    if shots and end and max(shots) > end:
        print(f"warning: --shots past the end of the run (frame {end}): {[s for s in shots if s > end]}",
              file=sys.stderr)
    err = os.path.join(out, "lua_error.txt")
    g = {"OUT": out + "/", "ERRFILE": err, "FRAMES": a.frames, "SHOT_EVERY": a.shot_every, "SHOTS": shots,
         "MASH": a.mash, "MASH_KEY": a.mash_key or MASH_KEY.get(system, "a"), "STATE_EVERY": a.state_every,
         "SYSTEM": system}
    if system == "psx":  # LuaJIT inside PCSX-Redux: pass the route inline rather than relying on io
        g["ROUTE_STEPS"] = route and read_route(route)
    else:
        g["ROUTE"] = route
    if mesen and a.state_in:
        g["STATE_IN"] = mesen_state(exe, os.path.abspath(a.state_in), out)
    if system == "psx" or dsfork:
        g["STATE_IN"] = a.state_in and os.path.abspath(a.state_in)
    if system == "nds" and not dsfork:  # stock DeSmuME saves/loads numbered slots only: <out>/<rom name>.ds<N>
        if a.state_in:
            shutil.copy(a.state_in, os.path.join(out, f"{stem}.ds{DS_SLOT_IN}"))
            g["STATE_IN_SLOT"] = DS_SLOT_IN
        if a.state_out:
            g["STATE_OUT_SLOT"] = DS_SLOT_OUT
    else:
        g["STATE_OUT"] = a.state_out and os.path.abspath(a.state_out)
    head = "\n".join(f"{k} = {lua_value(v)}" for k, v in g.items() if v is not None)
    head += "".join(f"\n{kv.split('=', 1)[0].strip()} = {kv.split('=', 1)[1]}" for kv in a.var or [])
    parts = [head, open(os.path.join(HERE, "lua", LIB["snes" if mesen else system]), encoding="utf-8").read()]
    for s in a.script or []:  # wrapped so a top-level error (e.g. a probe's assert) exits 2 instead of vanishing
        parts.append("L.safe(function()\n" + open(s, encoding="utf-8").read() + "\nend)()")
    lua = os.path.join(out, f"{stem}.lua" if system == "nds" and not dsfork else "_run.lua")
    with open(lua, "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")

    restore = []  # (path, old bytes or None): files outside --out that this run changes
    cwd = None
    sav = None
    if a.sav:  # fresh copy per run: the game writes to the copy, never to the user's file
        dest = {"gba": os.path.join(out, stem + ".sav"), "nds": os.path.join(out, stem + ".dsv"),
                "psx": os.path.join(out, "memcard1.mcd")}.get(system)
        if mesen:  # Mesen (portable) reads <exe dir>/Saves/<rom name>.srm (.sav on GBA); put back what was there
            dest = os.path.join(os.path.dirname(exe), "Saves", stem + (".sav" if system == "gba" else ".srm"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            restore.append((dest, open(dest, "rb").read() if os.path.exists(dest) else None))
            if restore[-1][1] is not None:  # on-disk copy survives even if this run is killed before restoring
                shutil.copy(dest, os.path.join(out, "_saves_backup" + os.path.splitext(dest)[1]))
        shutil.copy(a.sav, dest)
        sav = dest
    if mesen:
        mesen_portable(exe)
        cmd = [exe, "--testRunner", f"--timeout={a.timeout}", rom, lua]
    elif system == "gba":
        if os.path.normcase(rom).startswith(os.path.normcase(tempfile.gettempdir())):
            print("warning: mGBA can open a modal 'Temporary file loaded' box for ROMs under the temp dir, and the "
                  "run hangs; copy the ROM elsewhere", file=sys.stderr)
        cmd = [exe, "-C", "fpsTarget=3000", "-C", "audioSync=0", "-C", "videoSync=0", "-C", "volume=0",
               "--script", lua]
        if sav:
            cmd += ["-C", f"savegamePath={out}"]
        if a.state_in:
            cmd += ["-t", os.path.abspath(a.state_in)]  # mGBA: loading a state from Lua wedges the game
        cmd.append(rom)
    elif dsfork:  # own ini per run: nothing shared to restore, parallel runs are fine
        ini = os.path.join(out, "desmume.ini")
        with open(ini, "w") as f:
            f.write(f"[PathSettings]\nBattery={out}\n" if sav else "")
        jit = [] if a.debugger else ["--jit-enable"]
        cmd = [exe, "--ini", ini, "--headless", "--disable-limiter", "--disable-sound", *jit, "--lua", lua, rom]
        cwd = os.path.dirname(exe)
    elif system == "nds":
        restore.append(desmume_ini(exe, out, bool(sav)))
        jit = [] if a.debugger else ["--jit-enable"]  # ~1.5x; stock exec hooks (L.on_exec) need the interpreter
        cmd, cwd = [exe, "--disable-sound", *jit, rom], os.path.dirname(exe)
    else:
        bios = a.bios or os.environ.get("PSX_BIOS")
        cmd = [exe, "-portable", "-noupdate", "-no-ui", "-run", "-fastboot", "-loadiso", rom, "-dofile", lua]
        cmd += ["-debugger", "-interpreter"] if a.debugger else ["-no-debugger", "-dynarec"]
        if bios:
            cmd += ["-bios", os.path.abspath(bios)]
        if sav:
            cmd += ["-memcard1", sav]
        cwd = os.path.dirname(exe)  # -portable keeps settings and (without --sav) memory cards beside the exe
    t0 = time.time()
    stdout = ""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", cwd=cwd)  # stderr=DEVNULL made mGBA runs ~4x slower
    try:
        stdout, rc = p.communicate(timeout=a.timeout + 30)[0], p.returncode
    except subprocess.TimeoutExpired:  # kill the whole tree and reap it, so the next run can start
        kill_tree(p)
        p.communicate()
        rc = 124
    finally:
        if restore:
            time.sleep(0.5)
        for path, old in restore:
            if old is None:
                os.remove(path)
            else:
                open(path, "wb").write(old)
    if rc not in (0, 2) and time.time() - t0 >= a.timeout:  # Mesen's own --timeout exits 127 or -1
        rc = 124
    if os.path.exists(err):
        print("Lua error:", open(err, encoding="utf-8").read().strip())
        rc = 2
    elif rc not in (0, 124) and stdout.strip():
        print("\n".join(stdout.strip().splitlines()[-10:]))
    for raw in glob.glob(os.path.join(out, "*.gd")) + glob.glob(os.path.join(out, "*.psx")):
        to_png(raw)
    if system == "nds" and not dsfork and a.state_out:
        slot = os.path.join(out, f"{stem}.ds{DS_SLOT_OUT}")
        if os.path.exists(slot):
            shutil.move(slot, os.path.abspath(a.state_out))
    shots = sorted(glob.glob(os.path.join(out, "f[0-9]*.png")))
    final = os.path.join(out, "final.png")
    print(f"exit {rc}  shots {len(shots)}  final {'yes' if os.path.exists(final) else 'NO'}  dir {out}")
    if rc == 124:
        print("timeout: raise --timeout, shorten the route, or check the route reaches its end")
    if rc == 0 and a.smoke:
        if not os.path.exists(final) or sheetmod.is_blank(sheetmod.read_png(final)):
            print("SMOKE FAIL: final frame is one flat colour (black screen / hang)")
            rc = 3
        else:
            print("smoke ok: final frame has content")
    if a.sheet and shots:
        sheetmod.make(out, changed=0.02)
    return rc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("--out", required=True)
    ap.add_argument("--route")
    ap.add_argument("--route-str")
    ap.add_argument("--frames", type=int)
    ap.add_argument("--shot-every", type=int, default=0)
    ap.add_argument("--shots")
    ap.add_argument("--state-in")
    ap.add_argument("--state-out")
    ap.add_argument("--state-every", type=int, default=0, help="save DIR/s<frame>.<ext> every N frames (not NDS)")
    ap.add_argument("--sav", "--memcard", help="battery save or PS1 memory card; a fresh copy is used each run")
    ap.add_argument("--mash", type=int, default=0, help="press --mash-key for 6 frames every N frames once the route ends")
    ap.add_argument("--mash-key", help="default a (cross on PS1)")
    ap.add_argument("--script", action="append", help="Lua appended after the driver (repeatable)")
    ap.add_argument("--var", action="append", help="NAME=LUA global set before the scripts (repeatable)")
    ap.add_argument("--emu")
    ap.add_argument("--bios", help="PS1 BIOS image (else env PSX_BIOS, else PCSX-Redux's OpenBIOS)")
    ap.add_argument("--debugger", action="store_true",
                    help="PS1/NDS: interpreter, no JIT. Needed for PS1 hooks and stock-DeSmuME L.on_exec (not the QA fork)")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--fast", action="store_true", help="PSP: hold PPSSPP's fast-forward (needs the window focused)")
    ap.add_argument("--sound", action="store_true", help="PSP: keep audio on (muted by default)")
    ap.add_argument("--show", action="store_true", help="PSP: leave the PPSSPP window visible")
    ap.add_argument("--clean-saves", action="store_true", help="PSP: empty the memstick SAVEDATA first")
    sys.exit(run(ap.parse_args()))
