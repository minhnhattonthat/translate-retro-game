# NDS notes

- **Filesystem:** NitroFS. ndspy (`pip install ndspy`) reads and replaces files and rebuilds the ROM. Prove the identity rebuild first, including any nested archive (PAK/NARC) parser, byte-identical before any edit.
- **Compression:** LZ10/LZ11. Literal-only encoding is a valid first step (bigger but always correct). Write the real compressor when space demands it. Check archive size fields: a compact PAK format may not hold files over 0xFFFF bytes.
- **Code:** arm9.bin and overlays. Check whether overlays are compressed before patching.
- **ndspy `save()` is not byte-exact:** it writes a size word into the zero gap at ROM 0x1000 and doesn't pad back to the cartridge size. Restore both in the build (copy `orig[0x1000:0x1004]`, pad with 0xFF to `len(orig)`) and the identity test passes. Archives can also keep garbage in their alignment padding: keep it per file for the identity repack.
- **Free space for hook code: the ITCM autoload block.** Module params (offset from the `2106C0DE` footer, `ndspy` `arm9PostData`) list the autoload blocks; ITCM (0x01FF8000) is 32 KB, and games often fill less (one game: 0x7B00, so 0x500 bytes free). Insert the code at the end of the ITCM block's source in arm9.bin, grow its size in the autoload list, and shift `autoload_list`/`autoload_list_end` in the module params. Check the tail stays zero at runtime (Lua `memory.readbyte` loop) before using it. BL from arm9 reaches it.
- **Assembling hooks:** keystone (`pip install keystone-engine`) has no numeric local labels (`1:`/`1b`): name every label. Encode B/BL to fixed sites by hand and disassemble the blob with capstone before use.
- **Fonts (NFTR):**
  - If the renderer ignores advance widths, English can use digraph glyphs: two 6 px letters per 12 px cell, placed on unused JIS level-2 codes.
  - New codes must sit inside the owning CMAP block.
- **Text hooks:** game strings can use plain ASCII letters as control codes, even when no font maps them. A hook that rewrites strings (on the Shift-JIS→UTF-16 converter, say) must touch only what you put there: mark your own runs with a byte the game never uses (0x7F) and leave other ASCII alone. In one game, folding every ASCII letter into letter-pair codes froze the game right after New Game.
- **Emulator:** `emu.py game.nds` drives DeSmuME through Lua: the QA fork headless (no window, parallel runs, exec hooks under JIT), or stock DeSmuME with `lua51.dll` beside the exe; see `setup.md` and `emulator-qa.md` §DeSmuME. Routes take `t128,96` for touch. melonDS with synthetic key presses needs window focus; avoid it for scripted QA, though users often playtest in it.
- **Release:** xdelta.
