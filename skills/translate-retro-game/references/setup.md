# Tool setup

What to get for each platform, and where. Never download ROMs: the user supplies their own dump of the game. Console BIOS files come from the retrobios project (github.com/Abdess/retrobios), which `fetch_emu.py` reads and checks by SHA-1.

**Emulators: download the release, one instance per project.** Past projects lost hours to release zips that lacked a QA feature, to settings shared between projects (one project's input map or Lua permissions broke another's), and to an emulator in a sibling repo that changed under a running project. So:
- Run `python -X utf8 $SKILL/scripts/fetch_emu.py mesen|desmume|pcsx|ppsspp` from the repo root. It detects this machine's OS and CPU, picks the matching release asset, and unpacks it into `tools/<emu>/` (gitignored). No compiler or SDK needed. `--dry-run` shows the pick; it exits 1 with the manual download page when no build exists for the OS/CPU. The table below is the same information for doing it by hand. `emu.py` looks in this repo's `tools/**` first and never in other repos. Record the version and download URL in the instructions file.
- Never reuse another project's folder: copy the files, so settings, saves and states stay separate.
- Building from source is a last resort, only for a QA feature no release has (headless mode, a savestate or screenshot flag, a hook). The DeSmuME QA fork came from that. Say so to the user first, since it needs a compiler toolchain.
- **Default settings must work for input and scripts** before any QA. emu.py writes the script-side settings each run (Mesen `settings.json`: Lua `io` access, default key mappings; DeSmuME fork: a fresh ini per run; PPSSPP: sound off). Then check both sides once: a route that presses Start changes the screen, a `--script` probe's `L.log` lands in `log.txt`, and the GUI opened from `tools/<emu>/` responds to the keyboard so the user can play the build in the same instance. Commit the working settings file to `tools/emu-config/` so a fresh clone restores it.

## Everyone

| Tool | Get it | Notes |
|---|---|---|
| Python 3.10+ | python.org | Scripts here are stdlib only, except `disasm.py` (capstone). Run with `-X utf8`. |
| git | git-scm.com | Step 0 installs a pre-commit hook. |
| The user's ROM / disc dump | the user | Put it in `rom/` (gitignored). Check its hash against No-Intro (cartridges) or Redump (discs) and record it for the README. |

## Emulators (headless QA through `emu.py`)

| Platform | Emulator | Download (what `fetch_emu.py` picks on Windows x64) | Notes |
|---|---|---|---|
| SNES, GBA (also NES, GB, PCE, SMS, WonderSwan) | MesenCE 2.2+ (the community-maintained fork of Mesen2, which stopped at 2.1.1) | github.com/nesdev-org/MesenCE Releases: `Mesen_<ver>_Windows.zip` → `tools/mesen/`. | Runs headless with `--testRunner`, no window. emu.py writes `settings.json` beside the exe (portable mode, Lua file access, default key mappings on the GUI's next start). **GBA needs `Firmware/gba_bios.bin`** beside the exe (Mesen has no built-in BIOS; games boot black without it): `fetch_emu.py gba-bios` puts it there. If the GUI shows blank controls, Settings → Input → reset to defaults. |
| NDS | DeSmuME QA fork | github.com/minhnhattonthat/desmume/releases, latest `qa-*` zip → `tools/desmume/` (source: `agent-qa` branch, `QA-FORK.md`) | Upstream DeSmuME plus `--headless`, `--ini`, `--lua`, path savestates, PNG shots, exec hooks under JIT. Lua DLLs included. Keep it outside the system temp dir. Stock DeSmuME (github.com/TASEmulators/desmume Releases) still works through emu.py but needs a 64-bit `lua51.dll` beside the exe and opens a window. |
| PS1 | PCSX-Redux | github.com/grumpycoders/pcsx-redux. Scriptable: fetch `https://distrib.app/storage/manifests/pcsx-redux/dev-win-x64/manifest.json`, take `builds[0].id`, fetch `manifest-<id>.json` from the same folder, download `https://distrib.app` + its `path` (a zip) → `tools/pcsx-redux/` | Runs with `-no-ui`. Ships OpenBIOS, which is enough for a smoke test. For scene checks use a real BIOS: `fetch_emu.py psx-bios` saves SCPH-5500 (Japanese) to `tools/bios/`, which `emu.py` picks up by itself; `--bios` or env `PSX_BIOS` override it. |
| PSP | PPSSPP 1.17+ | ppsspp.org/downloads.html, Windows zip → `tools/ppsspp/` | (`psp.py` creates `memstick/` beside the exe). Needs no BIOS. `emu.py` drives it through its WebSocket debugger (`--debugger PORT`) with the window hidden. Python needs nothing extra for QA; image work (`typeset.py`, `gim.py` PNG export) wants Pillow (+ numpy for `inpaint`).

The user may playtest in a different emulator (bsnes, melonDS, DuckStation...). That's fine; `emu.py` is for your QA, so ask which one they use and test the release there too if it behaves differently.

## Assemblers and ROM tools

| Platform | Tool | Get it |
|---|---|---|
| SNES | asar | github.com/RPGHacker/asar (Releases) |
| SNES | WLA-DX (for disassembly-based builds) | github.com/vhelin/wla-dx |
| GBA, NDS, PS1 | armips | github.com/Kingcom/armips (build or use a release/nightly) |
| GBA | Python `keystone-engine` (alternative to armips) | `pip install keystone-engine`; it mis-encodes conditional `bl`, so check the bytes |
| NDS | ndspy (NitroFS, NARC, LZ10/LZ11) | `pip install ndspy` |
| PS1 | mkpsxiso / dumpsxiso (disc unpack + rebuild) | github.com/Lameguy64/mkpsxiso (Releases) |
| PS1 | jPSXdec (STR video/XA audio) | github.com/m35/jpsxdec (Releases; needs Java) |
| GBA, NDS, PS1 | capstone (needed by `$SKILL/scripts/disasm.py`) | `pip install capstone` |
| any | ffmpeg (subtitles, video) | ffmpeg.org |

## Patching

| Format | Tool | Get it |
|---|---|---|
| BPS (SNES, GBA ≤16 MiB) | `$SKILL/scripts/bps.py` (included) | also Flips: github.com/Alcaro/Flips |
| xdelta3 (discs, NDS, large GBA) | xdelta3 | github.com/jmacd/xdelta-gpl (Releases) |
| IPS (legacy, ≤16 MiB) | Flips | as above |

## Done when

`emu.py` boots the **original** ROM with `--smoke` and exits 0, a Start press changes the screen, a probe's log line appears, and the GUI in `tools/<emu>/` takes keyboard input. That proves the emulator, input, Lua and paths before any edits exist.
