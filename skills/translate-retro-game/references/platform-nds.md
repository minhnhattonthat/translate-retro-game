# NDS notes

- **Filesystem:** NitroFS. ndspy (`pip install ndspy`) reads and replaces files and rebuilds the ROM. Prove the identity rebuild first, including any nested archive (PAK/NARC) parser, byte-identical before any edit.
- **Compression:** LZ10/LZ11. Literal-only encoding is a valid first step (bigger but always correct). Write the real compressor when space demands it. Check archive size fields: a compact PAK format may not hold files over 0xFFFF bytes.
- **Code:** arm9.bin and overlays. Check whether overlays are compressed before patching.
- **Fonts (NFTR):**
  - If the renderer ignores advance widths, English can use digraph glyphs: two 6 px letters per 12 px cell, placed on unused JIS level-2 codes.
  - New codes must sit inside the owning CMAP block.
- **Text hooks:** game strings can use plain ASCII letters as control codes, even when no font maps them. A hook that rewrites strings (on the Shift-JIS→UTF-16 converter, say) must touch only what you put there: mark your own runs with a byte the game never uses (0x7F) and leave other ASCII alone. In Tokyo Majin, folding every ASCII letter into letter-pair codes froze the game right after New Game.
- **Emulator:** `emu.py game.nds` drives DeSmuME through Lua: the QA fork headless (no window, parallel runs, exec hooks under JIT), or stock DeSmuME with `lua51.dll` beside the exe; see `setup.md` and `emulator-qa.md` §DeSmuME. Routes take `t128,96` for touch. melonDS with synthetic key presses needs window focus; avoid it for scripted QA, though users often playtest in it.
- **Release:** xdelta.
