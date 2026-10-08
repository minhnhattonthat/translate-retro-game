# Emulator QA reference

`scripts/emu.py` boots a ROM headless, plays a scripted route, takes screenshots and exits with a real code. Use it so the user doesn't have to play the build first. It covers SNES (Mesen2), GBA (mGBA), NDS (DeSmuME) and PS1 (PCSX-Redux).

## QA order (cheapest first)

1. **Text side:** the lint and leftover-Japanese regex in the build check. These are free and catch most overflow before any emulator run.
2. **Smoke:** `emu.py build/game.sfc --out work/qa/smoke --route tools/routes/boot.txt --smoke`. This fails on a flat-colour final frame (black screen, hang). Run it after every build you hand over.
3. **Targeted routes:** one route per changed scene or menu. Start from a savestate near the scene, shoot every 30–120 frames, add `--sheet`, then read the **one** sheet PNG.
4. **Broad tour:** only after layout/wrap/engine changes. Keep a baseline (page counts or band-diff hashes per scene) and compare against it. Without a baseline, a wrap change that broke 76 scenes was found only by a full re-tour (~1 h per tour).
5. **The user's playtest** comes last, and only for feel and pacing.

## emu.py

```
python -X utf8 $SKILL/scripts/emu.py ROM --out DIR [--route FILE | --route-str "900 -;4 start;300 -"]
       [--frames N] [--shot-every N] [--shots 120,600] [--state-in S] [--state-out S]
       [--mash N --mash-key a] [--script hooks.lua] [--bios BIN] [--debugger] [--timeout SEC] [--sheet] [--smoke]
```

- **Route file:** one step per line, `FRAMES BUTTONS`. Buttons are `-` (none) or `a+start+up`. `#` starts a comment. SNES buttons: a b x y l r start select up down left right. GBA: a b l r start select up down left right. NDS: a b x y l r start select up down left right lid, plus `t128,96` (touch the bottom screen at x,y). PS1: cross circle square triangle l1 r1 l2 r2 start select up down left right.
  - Hold a press 4–6 frames; a 1-frame tap is often missed.
  - Wait on the screen you need, not on a frame count you hope is right. Mesen randomises SRAM per ROM, so fixed frame counts drift.
- The run stops after `--frames` frames, or at the end of the route. Output: `f000300.png...`, `final.png`, `log.txt`, `_run.lua`.
- `--mash N` presses `--mash-key` for 6 frames every N frames after the route ends, to click through dialogue. It needs `--frames`. Some games advance on B, not A. PS1 defaults to cross.
- **Savestates:** `--state-out` at the end of a route, `--state-in` to start there.
  - Build a library: `work/states/<scene>.mss`, made from cold-boot routes so they can be regenerated after engine changes.
  - **States keep the old VRAM and code:** after font, graphics or code edits, regenerate them from a cold boot.
  - User-made states (e.g. `bug_menu.mss`) are the fastest reproduction. Ask for them when the user reports a bug.
- **Exit codes:** 0 ok, 2 Lua error (message printed), 3 smoke failed, 124 timeout. Both emulators swallow Lua errors silently; the harness pcall-wraps every callback to surface them.
- **Emulator lookup:** `--emu`, then env `MESEN`/`MGBA`/`DESMUME`/`PCSX_REDUX`, then `tools/**/` in this repo or a sibling repo. Where to get each emulator: `setup.md`.

## Hooks (`--script`)

The user script is appended after the driver. Available:
- `L.on_frame(fn(n))`, `L.log(s)`, `L.shot("name.png")`, `L.frame`;
- Mesen only: `L.on_exec(lo, hi, fn)`, `L.on_write(lo, hi, fn)`, `L.rom_off(cpu_addr)` (LoROM; for HiROM use `a & 0x3FFFFF`), `L.save_state(path, done)`, `L.load_state(path, done)`;
- DeSmuME: `L.on_exec(addr, fn)` (wraps `memory.registerexec`); own API `memory.readbyte/readdword(addr)`, `memory.registerwrite(addr, size, fn)`;
- PCSX-Redux: `L.on_exec(addr, fn)` (needs `--debugger`: debugger + interpreter, slower), `L.save_state(path)`; RAM via `PCSX.getMemPtr()[addr & 0x1FFFFF]`, registers via `PCSX.getRegisters()`;
- plus the emulator's own API (`emu.read`, `emu.getState`, `emu.addMemoryCallback`; mGBA `emu.memory[...]`, `emu:read8`).

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

**Mesen2 (SNES; also NES/GB/PCE):**
- `Mesen.exe --testRunner --timeout=N rom script.lua`. `--timeout` is undocumented and defaults to 100 s, which is why the old "~100 s wall limit" chain scripts existed. On timeout it exits 127 or -1.
- `settings.json` beside the exe means portable mode (no first-run wizard hang). It needs `"AllowIoOsAccess": true` or Lua `io` is nil; emu.py bootstraps this.
- Set input in the `inputPolled` event.
- Savestate create/load only works inside an exec memory callback; the driver queues them.
- Runs at ~150 fps headless, so 900 frames take ~6 s.
- Parallel runs need separate `--out` dirs.

**mGBA (GBA):**
- A Qt window opens, which is unavoidable.
- Flags: `-C fpsTarget=3000 -C audioSync=0 -C videoSync=0 -C volume=0 --script s.lua [-t state] rom`.
- Set keys in the `keysRead` callback; setting them in `frame` races Qt polling.
- Load savestates via `-t`; loading from Lua wedges the game.
- `os.exit(n)` returns n. The previous instance must fully exit before the next starts (emu.py waits for it).
- Use fixed-width frame names: `f0*` globs missed frames ≥10000.

**DeSmuME 0.9.13 (NDS):**
- Needs the 64-bit `lua51.dll` beside the exe (`setup.md`). There is no Lua CLI flag: emu.py turns on `[Scripting] AutoLoad=1` and points `[PathSettings] Lua` and `StateSlots` at `--out` in `desmume.ini`, so DeSmuME runs `<out>/<rom name>.lua` when the ROM loads. The ini is restored after the run.
- A window opens; `BackgroundPause=0` keeps it running unfocused. `emu.speedmode("maximum")`: 600 frames take ~10 s.
- Screenshots are both screens stacked (256×384). On-screen messages ("Loaded from 9 slot") land in the shots for ~2 s.
- Savestates are slot files only: emu.py copies `--state-in` to slot 9 and moves slot 8 to `--state-out`. Loading must happen at a frame boundary (the driver does it on the first frame); the first shot after a load is grey.
- Only one instance at a time (shared ini). `os.exit(n)` returns n.
- Fallback without Lua: a `.dsm` input movie (`--play-movie`); every frame line needs the mic field `|0|RLDUTSBAYXWEG xxx yyy t 000|` or parsing drifts.

**PCSX-Redux (PS1):**
- `pcsx-redux.exe -portable -no-ui -run -fastboot -loadiso x.cue -dofile run.lua`. Without a window, `PCSX.quit(n)` returns n. Download: `setup.md`.
- Runs at real speed (~60 fps; no unthrottle setting), so 3600 frames take about a minute. Size `--frames` and `--timeout` to match.
- BIOS: `--bios` or env `PSX_BIOS`, a dump of the user's console BIOS (SCPH-5500 or similar for Japanese games). Without one, the bundled OpenBIOS is used, which is fine for a smoke test, but use the real BIOS when checking a scene.
- Screenshots: the resolution changes with the game mode (320×240, 640×480); while the display is off, the shot is 0×0 (stored as one black pixel). `sheet.py` handles mixed sizes.
- Savestates are uncompressed (~21 MB). **Take them on a quiet screen** (title, field, menu). A state taken during boot or an FMV loaded but then hung on black after the next input.
- Settings and memory cards live beside the exe (`-portable`), so saves persist between runs (a title menu may open on LOAD GAME).
