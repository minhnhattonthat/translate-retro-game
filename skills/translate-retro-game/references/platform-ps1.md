# PS1 notes

- **Disc rebuild:**
  - `dumpsxiso -x tree -s layout.xml disc.cue`, patch files in `tree/`, then `mkpsxiso -y layout.xml` with the working directory set to `tree/`.
  - Identity test: the rebuilt image's sha1 equals the original's.
- **Close the user's emulator before building.** DuckStation holds the .bin open: "Cannot open or create output image".
- **Archives** (`*.DAT`) use a game-specific LZ; reimplement it and roundtrip-test it.
  - Fixed load buffers cap text size. Enforce them in the build, or overflow shows garbage in-game.
  - Field widths in data records hide flag bytes: zero-filling a whole field wiped flags and gave a black boot, while every test passed. Write only the string bytes. `romdiff`-style checks per file catch this.
- **EXE and overlays:** armips for hooks.
  - Patch strings in place where possible, never touch the tails of code overlays, and remap `lui`/`addiu` pairs when moving strings.
  - Keep a committed `tools/re.py` (capstone disassembly, xref of `lui/addiu` pairs, savestate RAM read) instead of re-importing capstone inline in throwaway scripts.
- **Text:** Shift-JIS, so use `jp_left.py --sjis`. Half-width ASCII may need a font/renderer patch.
- **Windows:** check the box size (e.g. 30 chars × 3 lines). Give agents the soft limit; if the build splits overflow into a second window, pacing breaks.
- **FMV subtitles (STR):** burn ASS subtitles with ffmpeg and re-insert with jPSXdec `-replaceframes`. For timing with faster-whisper, turn VAD **off**; with it on, lines went missing.
- **Names stored in save files** need fixing on load, or old saves show old names.
- **Emulator:** `emu.py game.cue --bios <console BIOS dump>` drives PCSX-Redux headless (see `setup.md` and `emulator-qa.md` §PCSX-Redux; SPU muted at 8x speed, take savestates on quiet screens, `--sav card.mcd` for a memory card). DuckStation savestates (for user-sent bug states) are a header plus zstd frames.
- **Release:** xdelta against the **.bin** only. No .cue in the zip; PATCHING.txt tells the player to keep their own cue.
