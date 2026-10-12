# GBA notes

- **Pointers:** u32 `0x08000000 | offset`, 4-byte aligned. **Repoint only inside known pointer tables.** A whole-ROM scan for matching values once hit compressed graphics and corrupted a resource. Never patch words that merely equal an offset; decode the structure that owns them.
- **Compression:** BIOS LZ77 (type 0x10) and 4-bit Huffman. Implement both directions and test the roundtrip on real blocks. EWRAM scene buffers can be too small for English; one project ran scripts uncompressed straight from ROM via a loader patch.
- **Size:**
  - Stay ≤16 MiB when the game uses EEPROM saves and you ship IPS.
  - Going to 32 MiB means xdelta, and you must check the save type still works.
- **Text** is often Shift-JIS, so `jp_left.py --sjis` works directly. Tables of kana in code order (font maps) and kinsoku (line-break rule) tables decode as "text"; exclude them.
- **Older fan patches** sometimes left pointers aimed mid-line into old Japanese or at blank slots. `jp_left.py --gba-ptrs` (without `--orig`) finds them; fix them in a repair table written by the insert step.
- **Assembling:** armips, or keystone from Python. keystone mis-encodes conditional `bl`; check the bytes.
- **Fonts:** a VWF hook plus a width table in the wrap code (e.g. box 2×224 px, choices ≤45 chars).
- **Emulator:** `emu.py game.gba` uses Mesen when the user has put their GBA BIOS dump at `<Mesen dir>/Firmware/gba_bios.bin` (windowless, exec hooks, Lua savestates), else mGBA. Ask for the dump once; see `setup.md`.
- **Release:** IPS ≤16 MiB (building on an earlier IPS patch means shipping a combined patch or documenting the order). Otherwise xdelta. BPS also works for ≤16 MiB.
