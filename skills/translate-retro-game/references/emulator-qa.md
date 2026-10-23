# Emulator QA reference

`scripts/emu.py` boots a ROM headless, plays a scripted route, takes screenshots and exits with a real code. Use it so the user doesn't have to play the build first. It covers SNES (MesenCE/Mesen2), GBA (Mesen), NDS (DeSmuME), PS1 (PCSX-Redux) and PSP (PPSSPP).

## QA order (cheapest first)

1. **Text side:** the lint and leftover-Japanese regex in the build check. These are free and catch most overflow before any emulator run.
2. **Smoke:** `emu.py build/game.sfc --out work/qa/smoke --route tools/routes/boot.txt --smoke`. This fails on a flat-colour final frame (black screen, hang). Run it after every build you hand over.
3. **Targeted routes:** one route per changed scene or menu. Start from a savestate near the scene (made by the debug tool, below), shoot every 30–120 frames, add `--sheet`, then read the **one** sheet PNG.
4. **Broad tour:** only after layout/wrap/engine changes. Keep a baseline (page counts or band-diff hashes per scene) and compare against it. Without a baseline, a wrap change that broke 76 scenes was found only by a full re-tour (~1 h per tour).
5. **Agent playtest:** a playtester subagent plays a stretch turn by turn and reports what a player trips over (§Agent playtest).
6. **The user's playtest** comes last, and only for feel and pacing.

## Debug tool (phase 2, one per game)

Neither you nor the user should play through the game to reach a scene. Before translating, build `tools/debug/` for this game: one entry point that boots cold and lands on any scene, menu, shop, battle or ending by name.

```
python -X utf8 $SKILL/scripts/emu.py rom/game.sfc --out work/qa/warp --script tools/debug/warp.lua --var "SCENE='ch3_castle'" --frames 900 --sheet
```

- **`tools/debug/scenes.*`:** the scene list: name → the RAM writes that put the game there (map/room id, position, chapter and story flags, party, inventory, money, event id), plus how to trigger the load (a door, menu exit, death, a soft reset). Cover every chapter, every menu, every shop and battle type, every ending and the credits. Grow it whenever a bug report names a place it can't reach. Chapter entries must enter the way the game does (story select, or setting the flags then finishing the previous chapter's last event), so the chapter card and intro play. A warp that swaps in the chapter's first script skips the card, and QA then never sees it.
- **`tools/debug/warp.lua`:** reads `SCENE`, waits for a safe screen (title or field, tested by a RAM flag, not a frame count), applies the writes from `L.on_frame` and triggers the load. Same file, opt-in globals: `GOD` (pin HP or a timer every frame so `--mash` routes survive fights), `NOENC` (no random encounters), `FAST` (instant text, max stats, all items).
- **Find the values** with recon tools: `ramsearch.py` over `ramdump.lua` dumps for ids and flags (change rooms, note what changes), `watch.lua` to see who reads them, the disassembly for the event-flag array. Check GameFAQs/cheat databases first (never tcrf.net: see SKILL.md ground rules): many Japanese games keep a debug menu, level select or sound test, and existing cheat codes often are the RAM addresses you need. A debug menu re-enabled by a ROM patch goes in a debug build only, never the release.
- **No Lua (PPSSPP):** the same scene list drives a Python script that imports `psp.py` and pokes RAM over its WebSocket (`memory.write`), or writes CWCheat codes to `memstick/PSP/Cheats/<GAME_ID>.ini` with cheats enabled.
- **Save the results:** after each warp, `--state-out work/states/<scene>.<ext>`; regenerate the whole library from the scene list after engine, font or graphics changes (`tools/debug/` should have a one-command "regen all states"). Each regenerated state asserts a scene RAM flag before saving: a title menu whose default depends on existing saves sent one new-game route to "Continue → No data", and every state from it was silently wrong.
- **Done when** every scene-list entry reaches its scene from a cold boot with a shot to prove it. List the command in the instructions file so a fresh session uses it instead of asking the user for saves.

User saves, memory cards and savestates still help (ask once at project start), and `--state-every N` drops a state every N frames along a long route. Neither replaces the debug tool.

## Screen tour (the debug tool plus a text check)

The Gundam repo's `tools/tour.py` + `tools/lua/debug_screen.lua` are the model: force every screen of every case, then **read the text back from video memory** instead of trusting screenshots.
- **Force, don't play.** An `on_exec` hook at the point where the game picks its string writes the selector (team and mission, ending flags) first. Each case is its own cold-boot run, so cases run in parallel (`--jobs 3`) and none depends on another.
- **Dump when the text is complete.** Typed, scrolled or faded text is never fully on screen at one frame. Dump VRAM and PPU registers (`L.dump_ppu`) when the writer finishes or a fixed number of frames after it, and read the tilemap: tile index = entry & 0x3FF, chr and tilemap base and map height from the `.ppu.txt` of that scene (they differ per scene: one scene used chr word `0x4000` and a double-height map).
- **Check each line:** the count of non-blank tile columns in the line's tile rows must equal the string's non-space characters. That catches lost characters, a wrap into the next row and stray tiles below, in every language, with no OCR. Also assert that every text id was shown at least once (the coverage line of the report).
- **Which string was shown:** log the writer's pointer register at its entry (Mesen2 state keys `cpu.dbr`, `cpu.x`, `cpu.y`; a pointer kept in a task slot lives at slot-base + offset, so prefer the register) and map it to an id from the build's own layout.
- **Sheets for the eye:** render the full text from the dump (not the screenshot) into a contact sheet per group; keep the screenshots in each case folder.
- Exit non-zero on any failed case so the release gate can use it.

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
- **Emulator lookup:** `--emu`, then `tools/**/` in this repo (each project builds its own, `setup.md`), then env `MESEN`/`DESMUME`/`PCSX_REDUX`/`PPSSPP_HEADLESS`. Other repos are never searched.

## Hooks (`--script`)

Scripts (`--script`, repeatable) are appended after the driver; `--var NAME=LUA` sets a global before them (`--var WATCH_LO=0x7E1000`, strings as `--var "MODE='read'"`). Available everywhere:
- `L.on_frame(fn(n))`, `L.log(s)`, `L.shot("name.png")`, `L.frame`;
- `L.on_read(lo, hi, fn)`, `L.on_write(lo, hi, fn)`: `fn(addr, ...)`, the rest is per emulator (Mesen: value); PS1 needs `--debugger`; DeSmuME passes (addr, size) and fires for DMA as well as CPU accesses;
- `L.pc()`: the current program counter, for "who touched this" logs;
- `L.dump_ppu(prefix)`: `<prefix>.vram.bin`, `.pal.bin`, `.oam.bin` (+ `.ppu.txt` PPU registers on SNES, `.io.bin` LCD registers on GBA/NDS; PS1 writes only `.vram.bin`, palettes live in it). A relative prefix lands in `--out`. File layouts: the comment above `L.dump_ppu` in each `lua/*_lib.lua`;
- `L.dump_ram(path)`: SNES WRAM 128 KB, GBA EWRAM+IWRAM, NDS 4 MB / PS1 2 MB main RAM.

Per emulator:
- Mesen: `L.on_exec(lo, hi, fn)`, `L.rom_off(cpu_addr)` (LoROM; for HiROM use `a & 0x3FFFFF`), `L.save_state(path, done)`, `L.load_state(path, done)`. SNES code runs in either bank mirror (`$00-$3F`/`$80-$BF`), so `on_exec`/`on_read`/`on_write` hook both; a hook on one mirror alone silently misses. A read/write range inside `$7E0000-$7FFFFF` is hooked as work RAM, so it also catches low WRAM accessed as `$00:0000-1FFF`.
- DeSmuME: `L.on_exec(addr, fn)` (stock DeSmuME needs `--debugger`; the QA fork fires under JIT but can miss, see §DeSmuME), registers via `memory.getregister("arm9.r0")` / `setregister`, Lua 5.1 (no `//`, no `goto`); QA fork only: `L.save_state(path)`, `L.load_state(path)` from `L.on_frame`; own API `memory.readbyte/readdword(addr)`.
- PCSX-Redux: `L.on_exec(addr, fn)` (needs `--debugger`: debugger + interpreter, slower), `L.save_state(path)`; RAM via `PCSX.getMemPtr()[addr & 0x1FFFFF]`, registers via `PCSX.getRegisters()`.
- plus the emulator's own API (`emu.read`, `emu.getState`, `emu.addMemoryCallback`).

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

## Visual QA (phase 8: reviewers read the sheets, a gate counts them)

The implementer has the most context pressure, so it skims: one project looked at 15 of 417 tour sheets and called QA done. Read-only reviewer subagents read the sheets instead, and `qa_gate.py` makes "done" countable.

1. After every tour: `qa_gate.py init work/qa/manifest.tsv work/qa/tour`. It adds new sheets and re-hashes the old ones; a sheet whose pixels changed loses its verdict, so a rebuild never passes on the last build's verdicts, and unchanged sheets keep theirs. Pass `--glob "*.png"` when the tour's sheets aren't named `*sheet*`.
2. Run the same tour on the original ROM into `work/qa/tour_jp` once, so reviewers can tell the game's own behaviour from a translation bug.
3. `qa_gate.py todo work/qa/manifest.tsv work/qa/verdicts --size 30 --out-dir work/qa/chunks` writes `chunk_NNN.txt` files. Dispatch one read-only subagent per chunk, up to 4 at a time, with `$SKILL/assets/visual-qa-brief.md` (copy it to `docs/` and add the game's standing non-bugs as they are found) plus its chunk file and verdict file name.
4. Fix each `issue`, re-run its route, look at the new sheet, and add `id<TAB>fixed<TAB>note` in a newer file (`verdicts/recheck_<n>.tsv`): later files override earlier ones.
5. `qa_gate.py check work/qa/manifest.tsv work/qa/verdicts` exits 0 only when every sheet has a current `ok` or `fixed`. Call it from the repo's release script; the Claude Code guard also blocks `gh release create` while it fails.

## Agent playtest (a subagent plays turn by turn)

Routes and tours check screens you already know about. A playtester subagent finds the rest: a choice whose answer doesn't fit, a menu label that lies, a place a player gets stuck. Dispatch it with `assets/playtester-brief.md` (copy to `docs/playtester-brief.md` and fill in the game's controls as they are learned): ROM, its own session dir, a goal ("title to the end of the first battle"), a turn budget.

```
python -X utf8 $SKILL/scripts/play.py SESSION --rom build/game.gba --wait 900   # cold boot (or --state S / --sav F)
python -X utf8 $SKILL/scripts/play.py SESSION a down "right*40" [--gap 20] [--wait 60] [--every 30]
python -X utf8 $SKILL/scripts/play.py SESSION --back 2                           # undo
```

- Each call is one emu.py run from the last step's savestate: presses, then waits, then one shot (x2 for screens up to 320 px wide) as `SESSION/NNNN.png`, state `NNNN.<ext>`, presses in `log.tsv`. `--every N` prints sheets of the step instead, 12 frames each at x2 (typed text, fades). ~5 s per call on GBA. Budget: 60 calls covered a prologue and no more in each of three games, so start deeper goals from `--state`. A 60-call budget got one agent from cold boot through a 6,000-frame intro and character setup to the first stage select (Monster Guardians), and found leftover-variable, wrap and font bugs the tours had missed.
- Run it from the game repo (emu.py finds the emulator under `tools/`). One session dir per playtester; parallel playtesters need separate dirs.
- **Savestates go stale when a rebuild moves text.** RAM keeps pointers into ROM text (the message on screen, battle line buffers) and data written by the older build (names saved before a padding fix). Loaded on a newer ROM, they showed garbled, duplicated or Japanese text and a frozen box, which playtesters reported as bugs (Devil Children: 6 of 30 reports). Start playtests from an in-game save (`--sav`, then title > Continue), which holds no ROM pointers, or from states made on the same build. Re-check any bug seen only in an old state on a fresh one before fixing it. Don't rebuild the ROM a playtester is using: build to another path until it reports. One that loaded the ROM mid-build got a half-written image (Japanese text from the unpatched copy).
- **Check each start before dispatch:** one `play.py` call per start state or save, and read the shot. A save that wasn't a Continue save cost one playtester ~23 calls. PS1 sessions keep the memory card in `SESSION/card.mcd` for every step.
- **Reports survive the session:** the brief has the playtester append each issue to `SESSION/report.md` as it finds it, so a usage-limit stop or compaction doesn't lose them (three reports were once rebuilt from `log.tsv`).
- **Replay on another build:** `play.py SESSION --route [N]` prints steps 0..N as one route string. `emu.py OTHER_ROM --out D --route-str "<it>"` (with the session's `--sav`/`--state`) replays it on a fixed build, or on the original ROM to see whether a report is the game's own behaviour; pair the shots with `sheet.py --compare`. Comparing from an English savestate on the Japanese ROM fails (the state carries English VRAM). A press can drift onto another page where text lengths differ, so check the shots line up.
- **Filing:** save the agent's report to a file, then `play.py SESSION --export report.md` (from the game repo): its `- [ ] step NNNN - ...` lines go into `docs/bugs.md` (one rolling checklist per game, under a dated heading with the ROM sha1), and the cited steps' shots and states go to `work/playtest/<session>/` (`<session>-bugs/` when the session already lives there). Each `NNNN.<ext>` is that bug's repro state. Tick `- [x] (fixed in <build>)` after re-checking from it; the next playtester reads `docs/bugs.md` first and skips open bugs. Keep the states of a good run as savestates for routes.
- Tested on GBA, SNES (Mesen), NDS (DeSmuME QA fork; play.py idles 90 frames after each state load, the JIT grey-screen window), PS1 (PCSX-Redux, ~2 s per call) and PSP (PPSSPPHeadless, ~1.5 s per call). PS1: a game that stays black on OpenBIOS needs `--bios` on the new session (kept in `SESSION/bios.txt`). PSP: each session gets its own memstick (`SESSION/memstick`), so in-game saves never touch the shared one.

## Per-emulator facts and gotchas

**Mesen / MesenCE (SNES, GBA):**
- **GBA:** needs `<Mesen dir>/Firmware/gba_bios.bin` (`fetch_emu.py gba-bios`). GBA hooks take plain bus addresses (ROM `0x08000000`, EWRAM `0x02000000`, IWRAM `0x03000000`); `L.rom_off` strips the ROM base. Battery saves are `Saves/<rom name>.sav`.
- `Mesen.exe --testRunner --timeout=N rom script.lua`. `--timeout` is undocumented and defaults to 100 s, which is why the old "~100 s wall limit" chain scripts existed. On timeout it exits 127 or -1.
- `settings.json` beside the exe means portable mode (no first-run wizard hang). It needs `"AllowIoOsAccess": true` or Lua `io` is nil; emu.py bootstraps this.
- Set input in the `inputPolled` event.
- Savestate create/load only works inside an exec memory callback; the driver queues them.
- Runs at ~150 fps headless, so 900 frames take ~6 s.
- Parallel runs need separate `--out` dirs.
- A state from another Mesen version (header bytes 3–6, e.g. the user's 2.2.1 vs a 2.1.1 in `tools/`) loads black. emu.py re-stamps a copy with the local version and warns; if that still fails, run the user's Mesen with `--emu`.
- A savestate carries the battery RAM: with `--state-in`, `--sav` is overridden by the SRAM inside the state (save slots showed empty). To test a save file, boot cold with `--sav` and load it in game, then save a state there.
- `--sav` copies to `<exe dir>/Saves/<rom name>.srm` (`.sav` on GBA) for the run and puts back whatever was there. A file it displaced is also copied to `<out>/_saves_backup.*`, in case the run is killed before it restores.

**DeSmuME (NDS):**
- **QA fork** (preferred; emu.py detects it by its `--headless` flag): emu.py passes `--ini <out>/desmume.ini --headless --disable-limiter --jit-enable --lua <out>/_run.lua`. No window, nothing shared between runs (parallel runs work), PNG shots via `gui.savepng`, savestates by path (`--state-in/--state-out` take any `.dst`, `--state-every` works), exec hooks under JIT. 900 frames take ~4 s. Exec hooks under JIT can still miss: on qa-2 a hook on a function entry (Deltora Quest's string renderer) never fired while hooks inside the same function did. Run hooks that must not miss (text viewers, draw logs) with `--debugger` (interpreter, ~4x slower), and check a hook fires before trusting a "never called".
- **Stock 0.9.13+** (fallback): needs the 64-bit `lua51.dll` beside the exe (`setup.md`). There is no Lua CLI flag: emu.py turns on `[Scripting] AutoLoad=1` and points `[PathSettings] Lua` and `StateSlots` at `--out` in the shared `desmume.ini` (restored after the run), so DeSmuME runs `<out>/<rom name>.lua` when the ROM loads. A window opens; `BackgroundPause=0` keeps it running unfocused, `[FrameLimit] FrameLimit=0` + `--jit-enable` unthrottle it. Savestates are slot files (emu.py copies `--state-in` to slot 9, moves slot 8 to `--state-out`); shots are `.gd`, converted to PNG. One instance at a time.
- Both: screenshots are both screens stacked (256×384). States load at a frame boundary (the driver does it on the first frame). With JIT, some games stay grey after a state load until input or a redraw; the interpreter (`--debugger`) usually renders at once. If a state still shows grey, start the route with a harmless touch and a wait (`8 t2,2;120 -`). On-screen messages ("Loaded from 9 slot") land in stock shots for ~2 s. `os.exit(n)` returns n.
- Never run DeSmuME from the system temp dir: it switches to a per-user settings path there and crashes at start.
- Fallback without Lua: a `.dsm` input movie (`--play-movie`); every frame line needs the mic field `|0|RLDUTSBAYXWEG xxx yyy t 000|` or parsing drifts.

**PCSX-Redux (PS1):**
- `pcsx-redux.main -portable -no-ui -run -fastboot -loadiso x.cue -dofile run.lua`: no window, no console, nothing needs focus; `PCSX.quit(n)` returns n. On Windows emu.py runs `pcsx-redux.main` (beside the exe) directly: `pcsx-redux.exe` is a launcher that drops the stdout pipe, so `-no-ui` opens a console window. Download: `setup.md`.
- Speed is paced by the SPU: the driver sets `PCSX.settings.spu.Mute = true` and `spu.Speed = 8`, so 2,100 frames take ~6 s instead of ~40 s.
- On timeout emu.py kills the whole process tree (through the `pcsx-redux.exe` launcher an orphaned `pcsx-redux.main` blocks the next run).
- BIOS: `--bios`, env `PSX_BIOS`, or `tools/bios/scph*.bin` (`fetch_emu.py psx-bios` saves SCPH-5500, for Japanese games). Without one, the bundled OpenBIOS is used, which is fine for a smoke test, but use the real BIOS when checking a scene.
- Screenshots: the resolution changes with the game mode (320×240, 640×480); while the display is off, the shot is 0×0 (stored as one black pixel). `sheet.py` handles mixed sizes.
- Savestates are uncompressed (~21 MB). **Take them on a quiet screen** (title, field, menu). A state taken during boot or an FMV loaded but then hung on black after the next input.
- Settings and memory cards live beside the exe (`-portable`), so saves persist between runs (a title menu may open on LOAD GAME). `--sav card.mcd` passes a fresh copy as `-memcard1` instead.
- A breakpoint hit pauses the emulator, and an invoker returning `false` deletes the breakpoint after that one hit. `L.on_exec`/`on_read`/`on_write` call `PCSX.resumeEmulator()` and return `true`; do the same in a raw `PCSX.addBreakpoint`.
- `--debugger` (needed for breakpoints) can stall CD loads: a battle hung on "Now Loading" only with it. For a draw log over many scenes, have a debug build's hook append (caller, glyph) to a RAM ring buffer and read it from `L.on_frame` with `getMemPtr`: no debugger, full speed (a 14-scene tour in 82 s found 8-bit strings every static scan missed).
- Japanese games confirm with **circle** and cancel with cross; `--mash` defaults to cross, so pass `--mash-key circle` for them.
- Voiced games can hang headless waiting on the XA/SPU voice (Eithea: `voice_wait`, ~60 calls lost). Build a QA variant with the voice commands stripped instead of tuning SPU settings.
- DuckStation savestates can't be loaded here. Ask the user for the memory card (`.mcd`, works with `--sav`) or a screenshot and the menu path instead.

**PPSSPP (PSP; Windows):**
- `emu.py game.iso` (an ISO containing `PSP_GAME`, or a `.cso`) hands over to `psp.py`, which runs **PPSSPPHeadless** from the QA fork (github.com/minhnhattonthat/ppsspp, branch `agent-qa`, `QA-FORK.md`). **One install per machine**, in `%LOCALAPPDATA%\translate-retro-game\ppsspp-headless\` (`fetch_emu.py ppsspp-headless` puts it there; `--emu` or env `PPSSPP_HEADLESS` override): its debugger listens on a port, and Windows Firewall asks once per exe path, so a copy in each repo's `tools/` would ask again in each. Command: `PPSSPPHeadless --memstick=DIR --debugger=PORT --ppge GAME.iso`. No window, console or dialog, no audio, nothing needs focus; parallel runs work. Its stdout/stderr go to `<out>/ppsspp.log`. The stock release zips have no headless exe, and stock headless draws the PSP system dialogs (save/load prompts) as empty boxes: `--ppge` is the fork's one change.
- Control is PPSSPP's WebSocket API (`ws://127.0.0.1:PORT/debugger`, stdlib client in `psp.py`). Headless stops at the entry point; the driver runs it with `cpu.runUntilTime {us}` to each press edge and shot and waits for `cpu.stepping`, so a route lands on the same frames every run, as fast as the host allows (a 4,952-frame route to a song: 16 s; a play.py step: ~1.5 s). Also used: `input.buttons.send {buttons: {cross: true, ...}}` (names: `cross circle square triangle start select up down left right ltrigger rtrigger`; `l`/`r` are rejected), `gpu.buffer.screenshot` (480x272 PNG, no OSD), `game.state.load/save {path, wait: true}` (`--state-in/--state-out`), `memory.read {address,size}` (base64; user RAM starts at 0x08800000), `hle.module.list`, `cpu.getAllRegs`, breakpoints. These calls need PPSSPP master of 2026-10-19 or later. Software rendering by default; `--emu-arg=--graphics=vulkan` for the GPU path.
- Routes: same format as the other systems. Many Japanese games map OK to **circle**. A route that walks menus is fragile: after the first walk, save a state at the screen you test and start there.
- **In-game saves are per test:** each run gets a fresh memstick in `<out>/memstick` with no saves (a new console), so a route that creates save data creates it every run and no run sees another's saves. `--sav DIR` seeds it with a save folder (`.../PSP/SAVEDATA/<ID>DATA00`) or a whole `SAVEDATA` folder: keep the ones a test needs in the repo (e.g. `tests/saves/after-chapter1/`). `--memstick DIR` keeps one memstick across runs instead (play.py gives each session `SESSION/memstick`, seeded by `--sav` on the new session). A game that offers "create save data?" shows its prompt only while `PSP/SAVEDATA` is empty.
- The windowed app (`PPSSPPWindows64.exe`) is for people: playing, and the EBOOT dump (`platform-psp.md`). Driving it for QA needs its window in the foreground for hotkeys (keys are raw input only), shows OSD toasts in every screenshot and runs in real time.


## Record a playthrough once, replay it after every build (PS1 / PCSX-Redux)

The costly part of QA is a person reaching the late scenes. Record that once:

```
python scripts/record.py game.cue --out work/rec/intro --card save.mcd --state-every 1800 --watch map=0x800A1234:4
python scripts/replay.py work/rec/intro --out work/qa/intro [build.cue] [--shot-every 600] [--sheet]
```

- `record.py` opens PCSX-Redux at real speed; the player plays and closes the window. It reads pad 1 each vsync (`pad.getButton`) and writes `route.txt` (the normal route format: cold boot to the end), the start card, a savestate every N frames and the `--watch` RAM bytes at those frames (pick stable game variables: map id, story flag, party HP; none = no resync check).
- `replay.py` plays it headlessly at 8x on any build (default: the recorded ROM): same route and start card, states at the same frame numbers, and `pcsx_verify.lua` compares the watched bytes at each checkpoint. Exit 4 and `DIVERGED frame N name want got` in log.txt mean the run left the recorded path.
- Replays are deterministic on the same build (tested: 6 of 6 checkpoints match). On a build with different text lengths a press can land on another page and the run drifts; the first DIVERGED frame says where. Re-record from there, or record on the build under test.
- Then run the project's oracles over `<out>/*.sstate` and `<out>/f*.png`: leftover-text scan, overflow/clipping check, patch-code integrity (does the patch's RAM still equal the build: a savestate diff), a shot diff against the replay on the original disc.
- Other emulators: Mesen (.mmo) and DeSmuME (.dsm) record movies natively; this tool is PCSX-Redux only. A `pcsx_lib` script must not assign the global `VSYNC` (the driver's listener owns it).
