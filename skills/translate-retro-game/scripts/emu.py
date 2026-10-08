"""Headless emulator runs for translation QA: boot a ROM, play a route, screenshot, exit with a real code.

    python emu.py ROM --out DIR [--route FILE | --route-str "900 -;4 start;300 -"] [--frames N]
                  [--shot-every N] [--shots 120,600] [--state-in S] [--state-out S] [--mash N] [--mash-key KEY]
                  [--script hooks.lua] [--emu EXE] [--bios BIN] [--debugger] [--timeout SEC] [--sheet] [--smoke]

System from the ROM extension:
  .sfc/.smc          -> Mesen2 (--testRunner, no window)
  .gba               -> mGBA (Qt window opens; unavoidable)
  .nds               -> DeSmuME (window opens; Lua via lua51.dll beside the exe; desmume.ini restored after)
  .cue/.bin/.iso/.chd -> PCSX-Redux (-no-ui; runs at real speed, ~60 fps; --bios or env PSX_BIOS, else OpenBIOS)
Route: one step per line, "FRAMES BUTTONS" with BUTTONS "-" (none) or "a+start+up"; "#" starts a comment.
NDS adds "t128,96" (touch the bottom screen at x,y). PS1 buttons: cross circle square triangle l1 r1 l2 r2 ...
The run stops after --frames frames, or when the route ends. Writes DIR/f000120.png..., DIR/final.png, DIR/log.txt.
--smoke fails (exit 3) when final.png is a single flat colour: the black-screen boot check.
--script appends your Lua after the driver; use L.on_frame(fn(n)), L.log(s), L.shot(name), L.on_exec(...)
and the emulator's own API for hooks such as logging the game's string-draw routine.

Exit codes: 0 ok, 2 Lua error (message printed), 3 smoke failed, 124 timeout, other = emulator failure.
Emulator lookup: --emu, then env MESEN / MGBA / DESMUME / PCSX_REDUX, then tools/**/<exe> under the current repo
and its sibling repos.
"""
import argparse, configparser, glob, json, os, shutil, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sheet as sheetmod  # noqa: E402

SYSTEMS = {".sfc": "snes", ".smc": "snes", ".gba": "gba", ".nds": "nds",
           ".cue": "psx", ".bin": "psx", ".iso": "psx", ".chd": "psx"}
EXE = {"snes": ("MESEN", "Mesen.exe"), "gba": ("MGBA", "mGBA.exe"), "nds": ("DESMUME", "DeSmuME*.exe"),
       "psx": ("PCSX_REDUX", "pcsx-redux.exe")}
LIB = {"snes": "mesen_lib.lua", "gba": "mgba_lib.lua", "nds": "desmume_lib.lua", "psx": "pcsx_lib.lua"}
MASH_KEY = {"psx": "cross"}
MESEN_SETTINGS = '{"Debug": {"ScriptWindow": {"AllowIoOsAccess": true}}}'
DS_SLOT_IN, DS_SLOT_OUT = 9, 8


def find_emu(system, explicit):
    if explicit:
        return explicit
    env, name = EXE[system]
    if os.environ.get(env):
        return os.environ[env]
    for pattern in (os.path.join("tools", "**", name), os.path.join("..", "*", "tools", "**", name)):
        hits = sorted(glob.glob(pattern, recursive=True))
        if hits:
            return os.path.abspath(hits[0])
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


def desmume_ini(exe, out):
    """DeSmuME has no Lua CLI flag: with [Scripting] AutoLoad=1 it runs <[PathSettings] Lua>/<rom name>.lua when the
    ROM loads. Point Lua and StateSlots at the run dir, keep emulating when unfocused. Returns the old ini bytes."""
    if not os.path.exists(os.path.join(os.path.dirname(exe), "lua51.dll")):
        sys.exit("lua51.dll must sit beside the DeSmuME exe: LuaBinaries lua-5.1.5_Win64_dll17_lib.zip, "
                 "rename lua5.1.dll to lua51.dll (references/setup.md)")
    path = os.path.join(os.path.dirname(exe), "desmume.ini")
    old = open(path, "rb").read() if os.path.exists(path) else None
    c = configparser.RawConfigParser(strict=False)
    c.optionxform = str
    if old:
        c.read_string(old.decode("utf-16"))
    for sec, key, val in [("Scripting", "AutoLoad", "1"), ("PathSettings", "Lua", out),
                          ("PathSettings", "StateSlots", out), ("Main", "BackgroundPause", "0")]:
        if not c.has_section(sec):
            c.add_section(sec)
        c.set(sec, key, val)
    with open(path, "w", encoding="utf-16") as f:
        c.write(f, space_around_delimiters=False)
    return path, old


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


def run(a):
    ext = os.path.splitext(a.rom)[1].lower()
    system = SYSTEMS.get(ext)
    if not system:
        sys.exit(f"unsupported ROM type {ext}")
    if not (a.route or a.route_str or a.frames):
        sys.exit("give --route, --route-str or --frames")
    exe = find_emu(system, a.emu)
    out = os.path.abspath(a.out)
    rom = os.path.abspath(a.rom)
    stem = os.path.splitext(os.path.basename(rom))[0]
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "f[0-9]*.*")) + [os.path.join(out, n) for n in ("final.png", "lua_error.txt")]:
        if os.path.exists(old):
            os.remove(old)
    route = a.route and os.path.abspath(a.route)
    if a.route_str:
        route = os.path.join(out, "route.txt")
        with open(route, "w") as f:
            f.write("\n".join(s.strip() for s in a.route_str.split(";")) + "\n")
    err = os.path.join(out, "lua_error.txt")
    g = {"OUT": out + "/", "ERRFILE": err, "FRAMES": a.frames, "SHOT_EVERY": a.shot_every,
         "SHOTS": [int(x) for x in a.shots.split(",")] if a.shots else None, "MASH": a.mash,
         "MASH_KEY": a.mash_key or MASH_KEY.get(system, "a")}
    if system == "psx":  # LuaJIT inside PCSX-Redux: pass the route inline rather than relying on io
        g["ROUTE_STEPS"] = route and read_route(route)
    else:
        g["ROUTE"] = route
    if system in ("snes", "psx"):
        g["STATE_IN"] = a.state_in and os.path.abspath(a.state_in)
    if system == "nds":  # DeSmuME saves/loads numbered slots only: <out>/<rom name>.ds<N>
        if a.state_in:
            shutil.copy(a.state_in, os.path.join(out, f"{stem}.ds{DS_SLOT_IN}"))
            g["STATE_IN_SLOT"] = DS_SLOT_IN
        if a.state_out:
            g["STATE_OUT_SLOT"] = DS_SLOT_OUT
    else:
        g["STATE_OUT"] = a.state_out and os.path.abspath(a.state_out)
    head = "\n".join(f"{k} = {lua_value(v)}" for k, v in g.items() if v is not None)
    parts = [head, open(os.path.join(HERE, "lua", LIB[system]), encoding="utf-8").read()]
    if a.script:
        parts.append(open(a.script, encoding="utf-8").read())
    lua = os.path.join(out, f"{stem}.lua" if system == "nds" else "_run.lua")
    with open(lua, "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")

    restore = None
    cwd = None
    if system == "snes":
        mesen_portable(exe)
        cmd = [exe, "--testRunner", f"--timeout={a.timeout}", rom, lua]
    elif system == "gba":
        cmd = [exe, "-C", "fpsTarget=3000", "-C", "audioSync=0", "-C", "videoSync=0", "-C", "volume=0",
               "--script", lua]
        if a.state_in:
            cmd += ["-t", os.path.abspath(a.state_in)]  # mGBA: loading a state from Lua wedges the game
        cmd.append(rom)
    elif system == "nds":
        restore = desmume_ini(exe, out)
        cmd, cwd = [exe, "--disable-sound", rom], os.path.dirname(exe)
    else:
        bios = a.bios or os.environ.get("PSX_BIOS")
        cmd = [exe, "-portable", "-noupdate", "-no-ui", "-run", "-fastboot", "-loadiso", rom, "-dofile", lua]
        cmd += ["-debugger", "-interpreter"] if a.debugger else ["-no-debugger", "-dynarec"]
        if bios:
            cmd += ["-bios", os.path.abspath(bios)]
        cwd = os.path.dirname(exe)  # -portable keeps settings and memory cards beside the exe
    t0 = time.time()
    stdout = ""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=a.timeout + 30, cwd=cwd)
        rc, stdout = p.returncode, p.stdout
    except subprocess.TimeoutExpired:  # subprocess.run kills and reaps the child, so the next run can start
        rc = 124
    finally:
        if restore:
            time.sleep(0.5)
            path, old = restore
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
    if system == "nds" and a.state_out:
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
    ap.add_argument("--mash", type=int, default=0, help="press --mash-key for 6 frames every N frames once the route ends")
    ap.add_argument("--mash-key", help="default a (cross on PS1)")
    ap.add_argument("--script")
    ap.add_argument("--emu")
    ap.add_argument("--bios", help="PS1 BIOS image (else env PSX_BIOS, else PCSX-Redux's OpenBIOS)")
    ap.add_argument("--debugger", action="store_true", help="PS1: debugger + interpreter, needed for L.on_exec")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    sys.exit(run(ap.parse_args()))
