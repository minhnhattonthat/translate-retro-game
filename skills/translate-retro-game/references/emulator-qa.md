# Emulator QA reference

`scripts/emu.py` boots a ROM headless, plays a scripted route, takes screenshots and exits with a real code. Use it so the user doesn't have to play the build first. It covers SNES (MesenCE/Mesen2), GBA (Mesen with a BIOS dump, else mGBA), NDS (DeSmuME), PS1 (PCSX-Redux) and PSP (PPSSPP).

## QA order (cheapest first)

1. **Text side:** the lint and leftover-Japanese regex in the build check. These are free and catch most overflow before any emulator run.
2. **Smoke:** `emu.py build/game.sfc --out work/qa/smoke --route tools/routes/boot.txt --smoke`. This fails on a flat-colour final frame (black screen, hang). Run it after every build you hand over.
3. **Targeted routes:** one route per changed scene or menu. Start from a savestate near the scene, shoot every 30–120 frames, add `--sheet`, then read the **one** sheet PNG.
4. **Broad tour:** only after layout/wrap/engine changes. Keep a baseline (page counts or band-diff hashes per scene) and compare against it. Without a baseline, a wrap change that broke 76 scenes was found only by a full re-tour (~1 h per tour).
5. **The user's playtest** comes last, and only for feel and pacing.

**Reach late scenes cheaply.** At project start, ask the user once for battery saves, memory cards and savestates near late scenes; replaying hours of game from a cold boot is the slowest route. Without them:
- **Warp by RAM poke:** find the map/scene id with `ramsearch.py`, then write it from an `L.on_frame` hook and trigger a reload (door, menu exit).
- **God mode** for action games: pin HP (or a timer) every frame from Lua so `--mash` routes survive fights.
- `--state-every N` drops a state every N frames along a long route, so a later run starts from the nearest one.

## emu.py

```
python -X utf8 $SKILL/scripts/emu.py ROM --out DIR [--route FILE | --route-str "900 -;4 start;300 -"]
       [--frames N] [--shot-every N] [--shots 120,600] [--state-in S] [--state-out S] [--state-every N]
       [--sav FILE] [--mash N --mash-key a] [--script hooks.lua].. [--var NAME=LUA]..
       [--bios BIN] [--debugger] [--timeout SEC] [--sheet] [--smoke]
```

- **Route file:** one step per line, `FRAMES BUTTONS`. Buttons are `-` (none) or `a+start+up`. `#` starts a comment. SNES buttons: a b x y l r start select up down left right. GBA: a b l r start select up down left right. NDS: a b x y l r start select up down left right lid, plus `t128,96` (touch the bottom screen at x,y). PS1: cross circle square triangle l1 r1 l2 r2 start select up down left right.
  - Hold a press 4–6 frames; a 1-frame tap is often missed.
  - Wait on the screen you need, not on a frame count you hope is right. Mesen randomises SRAM per ROM, so fixed frame counts drift. Bisecting a bug the same way: test a screen condition (a pixel, a RAM flag) at each step, not a frame number.
- The run stops after `--frames` frames, or at the end of the route. Output: `f000300.png...`, `final.png`, `log.txt`, `_run.lua`. `--shots` past the end of the run get a warning, not a shot.
- **Fades and scrolls:** after a scroll or tile change, shoot every 1–2 frames through the transition (`--shots` list or a short `--shot-every`); a 60-frame cadence skips the frames where a half-drawn box or wrong tile shows.
- `--mash N` presses `--mash-key` for 6 frames every N frames after the route ends, to click through dialogue. It needs `--frames`. Some games advance on B, not A. PS1 defaults to cross.
- `--sav FILE` boots with a battery save (`.srm`/`.sav`/`.dsv`) or PS1 memory card (`.mcd`); each run gets a fresh copy, and the user's file is never written. `--memcard` is the same flag.
- **Savestates:** `--state-out` at the end of a route (its directory is created), `--state-in` to start there, `--state-every N` for `s<frame>.<ext>` along the way (not NDS).
  - Build a library: `work/states/<scene>.mss`, made from cold-boot routes so they can be regenerated after engine changes.
  - **States keep the old VRAM and code:** after font, graphics or code edits, regenerate them from a cold boot. On games that load from a file table (disc, NDS filesystem), a state can also hang after a rebuild moves files; regenerate it rather than debugging the build.
  - User-made states (e.g. `bug_menu.mss`) are the fastest reproduction. Ask for them when the user reports a bug.
- **Exit codes:** 0 ok, 2 Lua error (message printed), 3 smoke failed, 124 timeout. Both emulators swallow Lua errors silently; the harness pcall-wraps every callback to surface them.
- **Emulator lookup:** `--emu`, then env `MESEN`/`MGBA`/`DESMUME`/`PCSX_REDUX`, then `tools/**/` in this repo or a sibling repo. Where to get each emulator: `setup.md`.

## Hooks (`--script`)

Scripts (`--script`, repeatable) are appended after the driver; `--var NAME=LUA` sets a global before them (`--var WATCH_LO=0x7E1000`, strings as `--var "MODE='read'"`). Available everywhere:
- `L.on_frame(fn(n))`, `L.log(s)`, `L.shot("name.png")`, `L.frame`;
- `L.on_read(lo, hi, fn)`, `L.on_write(lo, hi, fn)`: `fn(addr, ...)`, the rest is per emulator (Mesen/mGBA: value). mGBA needs 0.11+ (dev build); PS1 needs `--debugger`; DeSmuME passes (addr, size) and fires for DMA as well as CPU accesses;
- `L.pc()`: the current program counter, for "who touched this" logs;
- `L.dump_ppu(prefix)`: `<prefix>.vram.bin`, `.pal.bin`, `.oam.bin` (+ `.ppu.txt` PPU registers on SNES, `.io.bin` LCD registers on GBA/NDS; PS1 writes only `.vram.bin`, palettes live in it). A relative prefix lands in `--out`. File layouts: the comment above `L.dump_ppu` in each `lua/*_lib.lua`;
- `L.dump_ram(path)`: SNES WRAM 128 KB, GBA EWRAM+IWRAM, NDS 4 MB / PS1 2 MB main RAM.

Per emulator:
- Mesen: `L.on_exec(lo, hi, fn)`, `L.rom_off(cpu_addr)` (LoROM; for HiROM use `a & 0x3FFFFF`), `L.save_state(path, done)`, `L.load_state(path, done)`. SNES code runs in either bank mirror (`$00-$3F`/`$80-$BF`), so `on_exec`/`on_read`/`on_write` hook both; a hook on one mirror alone silently misses. A read/write range inside `$7E0000-$7FFFFF` is hooked as work RAM, so it also catches low WRAM accessed as `$00:0000-1FFF`.
- DeSmuME: `L.on_exec(addr, fn)` (fires under JIT on the QA fork; stock DeSmuME needs `--debugger`); QA fork only: `L.save_state(path)`, `L.load_state(path)` from `L.on_frame`; own API `memory.readbyte/readdword(addr)`.
- PCSX-Redux: `L.on_exec(addr, fn)` (needs `--debugger`: debugger + interpreter, slower), `L.save_state(path)`; RAM via `PCSX.getMemPtr()[addr & 0x1FFFFF]`, registers via `PCSX.getRegisters()`.
- plus the emulator's own API (`emu.read`, `emu.getState`, `emu.addMemoryCallback`; mGBA `emu:read8`, `emu:readRange`).

**Probes** (`$SKILL/scripts/lua/probes/`, pass with `--script`; usage in each file's header):

| Probe | Logs |
|---|---|
| `watch.lua` | each distinct PC that reads or writes `WATCH_LO..WATCH_HI` (all emulators) |
| `ramdump.lua` | `ram_<frame>.bin` every `RAM_EVERY` frames, for `ramsearch.py` |
| `ppudump.lua` | `L.dump_ppu` at `DUMP_AT` (default the last frame) or every `DUMP_EVERY` |
| `snes_romreads.lua` | each distinct (PC, bank) reading ROM in a `FROM..TO` frame window: finds text, font and graphics readers |
| `snes_dmalog.lua` | every DMA: caller PC, source, size, B-bus register, VRAM address. A ROM source means raw tiles; a WRAM source means decompressed first |

**RAM search:** `ramsearch.py ram_000600.bin dec ram_000900.bin =27 ram_000900.bin` narrows addresses the way a cheat search does (`same changed inc dec +N -N =N`). Confirm a hit by poking it from Lua and watching the screen. Use it for warps, god mode and flags.

**Runtime leftover-Japanese scan:** hook the game's string-draw routine, log the pointer and bytes each time it runs, then decode the log with the project table offline and list strings that still hold Japanese codes, with frame numbers.

```lua
-- Mesen, SNES: log every string the draw routine is handed (address from your RE notes)
L.on_exec(0xC21E51, 0xC21E51, function()
  local s = emu.getState()
  local ptr = (s["cpu.dbr"] << 16) | s["cpu.x"]          -- where this game keeps the string pointer
  local t = {}
  for i = 0, 31 do t[#t + 1] = string.format("%02X", emu.read(ptr + i, emu.memType.snesMemory)) end
  L.log(string.format("%d %06X %s", L.frame, ptr, table.concat(t, " ")))
end)
```

Pair it with `--mash` and a long `--frames` to sweep menus and dialogue cheaply.

**Freeze detection** (bugs unit tests missed: a stuck menu cursor, a black bar): load each savestate in `work/states/`, press directions and A, and shoot before and after. `sheet.diff()` near 0 after input means a freeze. `sheet.is_blank()` means a black screen.

## Reading screenshots economically

- Read the contact sheet (`--sheet`, or `sheet.py DIR --changed 0.02 --div 2`), not individual frames. `--changed` drops frames that didn't change, and `--div 1` keeps full size for reading small text.
- Look at a single full-size frame only when a sheet tile shows a problem.
- Generate shots with a script, then open the PNG only **after** that command finished. Opening it in the same parallel batch of tool calls fails when the file doesn't exist yet; this happened about 20 times in one project.

## Per-emulator facts and gotchas

**Mesen / MesenCE (SNES, GBA):**
- **GBA:** emu.py uses Mesen for `.gba` when `<Mesen dir>/Firmware/gba_bios.bin` exists, else mGBA; `--emu` forces either. Mesen gives a windowless run, `L.on_exec`, Lua savestates and `--state-every`, none of which mGBA has. GBA hooks take plain bus addresses (ROM `0x08000000`, EWRAM `0x02000000`, IWRAM `0x03000000`); `L.rom_off` strips the ROM base. Battery saves are `Saves/<rom name>.sav`.
- `Mesen.exe --testRunner --timeout=N rom script.lua`. `--timeout` is undocumented and defaults to 100 s, which is why the old "~100 s wall limit" chain scripts existed. On timeout it exits 127 or -1.
- `settings.json` beside the exe means portable mode (no first-run wizard hang). It needs `"AllowIoOsAccess": true` or Lua `io` is nil; emu.py bootstraps this.
- Set input in the `inputPolled` event.
- Savestate create/load only works inside an exec memory callback; the driver queues them.
- Runs at ~150 fps headless, so 900 frames take ~6 s.
- Parallel runs need separate `--out` dirs.
- A state from another Mesen version (header bytes 3–6, e.g. the user's 2.2.1 vs a 2.1.1 in `tools/`) loads black. emu.py re-stamps a copy with the local version and warns; if that still fails, run the user's Mesen with `--emu`.
- `--sav` copies to `<exe dir>/Saves/<rom name>.srm` (`.sav` on GBA) for the run and puts back whatever was there. A file it displaced is also copied to `<out>/_saves_backup.*`, in case the run is killed before it restores.

**mGBA (GBA fallback):**
- A Qt window opens, which is unavoidable.
- Flags: `-C fpsTarget=3000 -C audioSync=0 -C videoSync=0 -C volume=0 --script s.lua [-t state] rom`.
- Set keys in the `keysRead` callback; setting them in `frame` races Qt polling.
- Load savestates via `-t`; loading from Lua wedges the game.
- `os.exit(n)` returns n. The previous instance must fully exit before the next starts (emu.py waits for it).
- Use fixed-width frame names: `f0*` globs missed frames ≥10000.
- Keep the ROM out of the system temp dir: mGBA can open a modal "Temporary file loaded" box there and the run hangs to timeout (emu.py warns).
- `--sav` passes `-C savegamePath=<out>` with a copy named `<rom name>.sav`; the `.sav` beside the ROM is left alone.
- A watchpoint that fires during the script's own `emu:readRange` or screenshot deadlocks mGBA; `L.dump_*` and `L.shot` lift the `L.on_read`/`on_write` watchpoints meanwhile. Raw `emu:setRangeWatchpoint` calls get no such protection.

**DeSmuME (NDS):**
- **QA fork** (preferred; emu.py detects it by its `--headless` flag): emu.py passes `--ini <out>/desmume.ini --headless --disable-limiter --jit-enable --lua <out>/_run.lua`. No window, nothing shared between runs (parallel runs work), PNG shots via `gui.savepng`, savestates by path (`--state-in/--state-out` take any `.dst`, `--state-every` works), exec hooks under JIT. 900 frames take ~4 s.
- **Stock 0.9.13+** (fallback): needs the 64-bit `lua51.dll` beside the exe (`setup.md`). There is no Lua CLI flag: emu.py turns on `[Scripting] AutoLoad=1` and points `[PathSettings] Lua` and `StateSlots` at `--out` in the shared `desmume.ini` (restored after the run), so DeSmuME runs `<out>/<rom name>.lua` when the ROM loads. A window opens; `BackgroundPause=0` keeps it running unfocused, `[FrameLimit] FrameLimit=0` + `--jit-enable` unthrottle it. Savestates are slot files (emu.py copies `--state-in` to slot 9, moves slot 8 to `--state-out`); shots are `.gd`, converted to PNG. One instance at a time.
- Both: screenshots are both screens stacked (256×384). States load at a frame boundary (the driver does it on the first frame). With JIT, some games stay grey after a state load until input or a redraw; the interpreter (`--debugger`) renders at once. On-screen messages ("Loaded from 9 slot") land in stock shots for ~2 s. `os.exit(n)` returns n.
- Never run DeSmuME from the system temp dir: it switches to a per-user settings path there and crashes at start.
- Fallback without Lua: a `.dsm` input movie (`--play-movie`); every frame line needs the mic field `|0|RLDUTSBAYXWEG xxx yyy t 000|` or parsing drifts.

**PCSX-Redux (PS1):**
- `pcsx-redux.exe -portable -no-ui -run -fastboot -loadiso x.cue -dofile run.lua`. Without a window, `PCSX.quit(n)` returns n. Download: `setup.md`.
- Speed is paced by the SPU: the driver sets `PCSX.settings.spu.Mute = true` and `spu.Speed = 8`, so 2,100 frames take ~6 s instead of ~40 s.
- On timeout emu.py kills the whole process tree: the `pcsx-redux.exe` launcher leaves `pcsx-redux.main` running otherwise, and the orphan blocks the next run.
- BIOS: `--bios` or env `PSX_BIOS`, a dump of the user's console BIOS (SCPH-5500 or similar for Japanese games). Without one, the bundled OpenBIOS is used, which is fine for a smoke test, but use the real BIOS when checking a scene.
- Screenshots: the resolution changes with the game mode (320×240, 640×480); while the display is off, the shot is 0×0 (stored as one black pixel). `sheet.py` handles mixed sizes.
- Savestates are uncompressed (~21 MB). **Take them on a quiet screen** (title, field, menu). A state taken during boot or an FMV loaded but then hung on black after the next input.
- Settings and memory cards live beside the exe (`-portable`), so saves persist between runs (a title menu may open on LOAD GAME). `--sav card.mcd` passes a fresh copy as `-memcard1` instead.
- Breakpoint callbacks must return `false` or the emulator pauses; `L.on_exec`/`on_read`/`on_write` do this for you.

**PPSSPP (PSP; Windows):**
- `emu.py game.iso` (an ISO containing `PSP_GAME`, or a `.cso`) hands over to `psp.py`: it starts `PPSSPPWindows64.exe --memstick=<exe dir>/memstick --debugger=<free port>`, waits for the game, and **hides the window**, with audio off (`[Sound] Enable = False` written to the memstick's `ppsspp.ini` each run; `--sound` keeps it) (`ShowWindow(SW_HIDE)`; the game keeps running and `--emu-arg=-d` adds debug logs to `<out>/ppsspp.log`).
- Control is PPSSPP's WebSocket API (`ws://127.0.0.1:PORT/debugger`, stdlib client in `psp.py`): `cpu.status` (`us` = emulated microseconds, frame = `us / 16667`), `input.buttons.send {buttons: {cross: true, ...}}` (names: `cross circle square triangle start select up down left right ltrigger rtrigger`; `l`/`r` are rejected), `gpu.buffer.screenshot` (needs the CPU stepping: `cpu.stepping` then `cpu.resume`; returns a PNG data URI), `memory.read {address,size}` (base64; user RAM starts at 0x08800000), `hle.module.list`, `cpu.getAllRegs`, breakpoints, `game.reset`. There is **no savestate call**: `--save-state` sends F2 with real key events (needs the window shown for ~2 s; the driver hides it again), `--state-in` is PPSSPP's `--state=FILE`.
- Screenshots are the full window render (1440×816 at the default 3x scale), PNG. A green "Debugger web server running" toast overlays the first seconds and "State saved/loaded" toasts appear for ~2 s: ignore them or start shots later.
- Speed: real time by default (2,000 frames ≈ 35 s). `--fast` holds Tab (≈17x: 16,000 frames in 11 s) with real key events, so it grabs the keyboard focus while it runs. Loading a state at the scene under test skips the boot and menus (a run from a state starts in ~3 s).
- Routes: same format as the other systems. Many Japanese games map OK to **circle**. A route that walks menus is fragile: after the first walk, save a state at the screen you test and start there.
- Saves and settings live in `<exe dir>/memstick/`; a game that offers "create save data?" shows its prompt only while `PSP/SAVEDATA` is empty (`--clean-saves`). `memstick/PSP/SYSTEM/ppsspp.ini` can be edited between runs (the emulator rewrites it on exit).
- Not found, so do not look: a Lua API, a headless build in the standard zip, a savestate/screenshot CLI flag, a way to keep running at speed without focus.

