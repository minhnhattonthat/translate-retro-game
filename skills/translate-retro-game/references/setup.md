# Tool setup

What to download for each platform, and where to get it. Unzip third-party tools into the repo's `tools/<name>/` and gitignore them; `emu.py` searches `tools/**` in the repo and its sibling repos, or takes `--emu` / an env var. Prefer the newest stable release unless noted. Never download ROMs or BIOS files: the user supplies their own dumps.

## Everyone

| Tool | Get it | Notes |
|---|---|---|
| Python 3.10+ | python.org | Scripts here are stdlib only. Run with `-X utf8`. |
| git | git-scm.com | Step 0 installs a pre-commit hook. |
| The user's ROM / disc dump | the user | Put it in `rom/` (gitignored). Check its hash against No-Intro (cartridges) or Redump (discs) and record it for the README. |

## Emulators (headless QA through `emu.py`)

| Platform | Emulator | Get it | Notes |
|---|---|---|---|
| SNES (also NES, GB, PCE) | Mesen2 | github.com/SourMesen/Mesen2 (Releases, or the latest Actions build) | Runs headless with `--testRunner`. emu.py writes `settings.json` beside the exe (portable mode + Lua file access). Needs .NET 8 on Windows. |
| GBA | mGBA 0.10+ | mgba.io/downloads.html | Lua scripting (`--script`) landed in 0.10. A window opens. |
| NDS | DeSmuME 0.9.13+ (Windows x64) | github.com/TASEmulators/desmume (Releases) | Lua needs **`lua51.dll` beside the exe**: get LuaBinaries `lua-5.1.5_Win64_dll17_lib.zip` (sourceforge.net/projects/luabinaries, 5.1.5 → Windows Libraries → Dynamic) and rename its `lua5.1.dll` to `lua51.dll`. Works with the built-in HLE BIOS; no firmware needed. |
| PS1 | PCSX-Redux | github.com/grumpycoders/pcsx-redux (README "Where" links). Scriptable download: fetch `https://distrib.app/storage/manifests/pcsx-redux/dev-win-x64/manifest.json`, take `builds[0].id`, fetch `manifest-<id>.json` from the same folder, and download `https://distrib.app` + its `path` (a zip). | Runs with `-no-ui`. Ships OpenBIOS, which is enough for a smoke test. For scene checks use a real BIOS **dumped from the user's console** (Japanese games: SCPH-5500 or similar), passed with `--bios` or env `PSX_BIOS`. |

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
| PS1/any | capstone (MIPS/ARM disassembly from Python) | `pip install capstone` |
| any | ffmpeg (subtitles, video) | ffmpeg.org |

## Patching

| Format | Tool | Get it |
|---|---|---|
| BPS (SNES, GBA ≤16 MiB) | `$SKILL/scripts/bps.py` (included) | also Flips: github.com/Alcaro/Flips |
| xdelta3 (discs, NDS, large GBA) | xdelta3 | github.com/jmacd/xdelta-gpl (Releases) |
| IPS (legacy, ≤16 MiB) | Flips | as above |

## Done when

`emu.py` boots the **original** ROM with `--smoke` and exits 0. That proves the emulator, Lua and paths before any edits exist.
