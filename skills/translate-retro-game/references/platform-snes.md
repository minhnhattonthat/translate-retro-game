# SNES notes

- **Mapping:** LoROM (file offset = `((addr & 0x7F0000) >> 1) | (addr & 0x7FFF)`) or HiROM (`addr & 0x3FFFFF`, banks `$C0+`). Mesen memory callbacks report CPU addresses, so convert them before comparing to file offsets.
- **ExHiROM (>4 MB):** banks `$C0–$FF` hold the first 4 MB (`addr & 0x3FFFFF`), `$40–$7D` the rest (`addr & 0x7FFFFF`); the header sits at `$40FFC0`. Set the assembler's `exhirom` mode and test an address from each half.
- **Expanding the ROM:**
  - 2 → 4 MB: set the header size byte (`$7FD7`/`$FFD7` = `$0C`) and fix the checksum at release (`bps.py snes-checksum`).
  - Expanded banks are filled with 0xFF. `romdiff.py` treats extra 0xFF bytes as unchanged.
- **Pointers:**
  - 16-bit pointer pools must stay inside one 32 KB bank (LoROM).
  - The allocator must never cross a bank, and must stop before `$7E/$7F` (WRAM) mirrors.
  - Recompressed blocks that no longer fit go to the expanded area, still never crossing a bank.
- **Assemblers:**
  - asar (most patches), xkas-plus, or WLA-DX for disassembly-based builds.
  - asar: pass `--fix-checksum=off` (the release step owns the checksum), force operand size (`lda.w`) where it matters, and parenthesise expressions explicitly; asar's precedence surprised past patches.
  - With a disassembler that emits WLA source, emit the header as data, never `.SNESHEADER`/`.BASE`, so the identity build stays exact.
  - Point Makefile tool variables (`WLA ?=`) at the in-repo `tools/` copy, not at a path from someone else's machine.
- **Fonts:**
  - VWF on the kanji dynamic-tile path is the usual route.
  - A tiny 3×7 font, 2 letters per tile, works for names and long descriptions in small boxes.
  - The VWF tile buffer gets wiped by window clears and map scroll (a black bar in-game), so test scrolling and menu reopening.
- **Text engines** often jump (`F2`/`F3`-style goto/call codes) into shared fragments. The extractor must follow jumps, and the encoder must keep fragment addresses valid, or one review fix breaks every jump (seen as "intro stuck at black screen").
- **Checksum:** complement at `+0x2C`, sum at `+0x2E` of the header (`$FFDC/$FFDE` HiROM, `$7FDC/$7FDE` LoROM). Do it only in the release step.
- **Emulator:** MesenCE (or Mesen2) via `emu.py` (`.sfc`/`.smc`); see `setup.md`.
- **Release:** BPS.

## Engine patching (what a full VWF patch needs)

- **Hook pattern:** overwrite the first instructions of the game's routine with `JML new` (4 bytes; pad a cut-in-half instruction with NOPs). `new` runs the displaced instructions, does the work, then `JML`s to the address after the hook. Return through the `$80+` mirror of the bank so execution stays FastROM. Keep one hook list (`org` + label + why) in `docs/re/`; a full patch has ~100 (items, save menu, title, text engine, ending).
- **FastROM:** set the map-mode byte `$FFD5` to `$30`; hook reset to write `$01` to `$420D` (MEMSEL) and clear `$4200/$420B/$420C` before jumping back; hook the NMI and IRQ entries the same way. Only `$80+` banks run fast. Do it when a VWF renderer eats frame time, and boot cold to check.
- **VRAM uploads go through the game's own NMI DMA dispatcher** (find it with `snes_dmalog.lua`: caller PC of the DMA). Hook it and add command ids that run queued `(src, size, vram, bank)` slots in WRAM. Writing VRAM outside vblank gives glitches that look random.
- **A NMI wrapper in expanded ROM** can gate the original NMI (return early in a custom mode, else `JML` into the original body after the pushes). Good for a title or intro screen you redraw yourself.
- **VWF data:** one advance-width byte per table code, in `.tbl` order, beside the font data. The renderer shifts each glyph by `cursor & 7` px into a WRAM tile buffer and DMAs the tiles. Make the lint parse the width rows from the asm source, so lint and engine never disagree.
- **Marks as an overlay layer (tall-glyph languages):** when the game's cell or line buffer is too short for tone marks, draw each accented letter as two glyphs ORed into a taller line buffer: the base letter (own width row) and the mark (separate font bank, own width row, offset above the x-height). The script keeps one precomposed code per letter; a table maps code → (base glyph, mark glyph). This needs ~26 bases plus ~15 marks instead of ~130 full glyphs. Every text path (dialogue, menus, battle, name entry) has its own draw routine and line buffer: find them all by logging the game's draw calls and hook each one, or some screens stay clipped.
- **Glyph-slot indirection:** if the game maps text code → glyph slot through a table, remap that table instead of rewriting script bytes.
- **Several tables, one font:** dialogue, intro/ending crawl and item or menu text often use the same glyphs but different control codes (`<line> <scroll> <pause> <text_spd>+arg <name> <num>+arg <end> <force_end>`). Keep one `.tbl` per script type, with the shared glyph rows generated from one source.
- **Cutscene command streams are not text:** an ending script of `<move><n> <wait> <dialogue id> <palette> <fade>` bytes is a small VM. Extract it as data, translate nothing in it, but re-check its timing and dialogue ids when text length changes.
- **Debug build:** a `debug.asm` applied only to the debug build (start inventory/sword byte, NOP the damage and MP decrements) works in every emulator without Lua. Keep it out of the release asm; a `//`-commented cheat in the main patch is one keystroke from shipping.
