# Pipeline reference

Distilled from eight finished fan translations across SNES, GBA, NDS and PS1. Read only the section you are in.

## Contents
- Repo layout and text format
- Recon
- Identity build
- Extract
- Marker build and engine spike (incl. the width gate)
- Checks
- Pitfalls that reached a user's playtest
- Building on an earlier patch
- Release

## Repo layout and text format

- Gitignore `rom/`, `build/`, `work/`, `dist/`/`release/`, `tools/` binaries (assemblers, emulators, disc tools) and savestates.
- Keep in git:
  - `tbl/` (jp and en tables)
  - `asm/` or `patch/`
  - `docs/re/` or `notes/` for reverse-engineering findings
  - `glossary.md` at the root
  - `tools/` for the Python code
- One entry point: `build.py <cmd>` or `make build|check|release`. Use a single command per job, not a sequence the agent has to remember.
- **Text format:** JSON, one file per bank/block/scene, `indent=1`, `ensure_ascii=False`.
  - Fields: `id` (stable, address-based), `ptr`/`slots`, `jp`, `en`, `max` (bytes or px), `box`/`speaker`, `status`, `notes`.
  - Keeping `jp` beside `en` makes diffs reviewable.
  - CSV works too, but watch for a UTF-8 BOM: read with `utf-8-sig`.
- **Dump never clobbers English.** `dump` writes only missing files, or refuses without `--force`. Three projects added this rule after losing work.
- **Dedupe repeated strings:** use a translation memory keyed by line id, with per-id overrides. Keying by the JP string merged short fragments like 「この / の across scenes and needed a repair pass.

## Recon

1. **Look for prior work first:**
   - an older fan patch (diff it against the original to map text and code regions, or build on it);
   - community tools for the game or engine (decompressors, table files, disassemblies);
   - partial or foreign-language patches and their notes (a Korean or Spanish patch often documents formats).
2. **Header and map:** mapping mode, size, checksum, free space (runs of 0x00/0xFF at bank ends).
3. **Compression:** look for game LZ variants and BIOS LZ77/Huffman (GBA). Write a decompressor plus a recompressor, and test the pair byte-for-byte on real blocks.
4. **Text encoding:**
   - find a known on-screen string by relative search (the difference pattern between kana);
   - or log the string-draw routine in the emulator (`references/emulator-qa.md` §Hooks);
   - build `tbl/jp.tbl`;
   - list control codes with their argument counts. A wrong argument count desyncs everything after it.
   - **Confirm the font by hooking the draw call**, not by how glyphs look: games carry several fonts and tables. A table built by eye needs a cross-check against a decoded known string; after fixing it, regenerate every `jp` field from the ROM.
   - Note the text orientation: vertical text, or a handheld game played sideways, changes the whole font and box plan.
5. **Pointers:** find the tables and the format (16-bit + bank, 24-bit, GBA `0x08000000|off`). Note which code reads them.
6. **Graphics text:** survey tile-drawn Japanese (`references/graphics.md` §Survey).
7. Record everything in `docs/re/*.md`, one file per subsystem, with an index line in AGENTS.md/CLAUDE.md.
8. RE helpers in `$SKILL/scripts/`: `relsearch.py` (relative search), `dis65816.py` (SNES), `disasm.py` (ARM/THUMB/MIPS via capstone), and the Lua probes for ROM-read, DMA and memory watches (`emulator-qa.md` §Hooks). Copy one into `tools/` once you start adapting it.

## Identity build

Unpack → repack with no edits → compare bytes. Make this the first test in the repo and keep it green forever. It proves the compressor, the pointer writer and the image rebuilder before any English exists. Typical forms: an ISO sha1 test for a disc, a byte-identical archive (PAK/NARC) repack, `make verify` printing "identical", a `roundtrip` command over every text block.

## Extract

- Decode every string through the table codec (`scripts/tbl.py`). Unknown bytes become `[XX]` so they roundtrip.
- **Roundtrip test:** `encode(decode(bytes)) == bytes` for every string.
- **Coverage test, run against the ORIGINAL ROM:** the text ranges are fully covered, with no unexplained gaps. A gap is usually text you missed, or data you are about to corrupt.
  - Dump every pointer target, including strings referenced from the EXE, arm9/overlays or code banks, not only the script banks.
  - An unknown control code must not end a string: decode it as `[XX]` and keep going, then check the next bytes still decode. Strings silently cut at the first unknown code left the rest Japanese.
- **Space-padded fixed-length strings** (names, item fields) get re-padded to their length on insert; the game may compare or centre them by length.
- **Mark non-text explicitly.** Data that decodes as text, translated by mistake, has broken games repeatedly:
  - portrait data dumped as "text" gave miscoloured portraits;
  - a kinsoku (line-break rule) table;
  - font-map runs;
  - magic and signature strings (save-file headers, file IDs) that code compares byte for byte.
  - One project ended up flagging 354 entries as `data`; expect a few hundred.

## Marker build and engine spike

- **Marker build:** replace every untranslated line with `[id] The quick brown fox...` at full box width.
  - Boot it and tour the game with `emu.py`. Every box shows its id, overflow and paging show up at once, and anything still Japanese is text you haven't extracted.
  - Lines whose marker shows up somewhere odd (or nowhere) are non-text or reused buffers.
- **Engine spike:** decide the font early and prove it in-game. Options:
  - half-width;
  - VWF;
  - tiny 2-letters-per-tile font;
  - digraph glyphs when the renderer ignores advance widths.
- Try paths in order of cost and boot each one. A black-screen-after-logo bug once came from a font patch that was never booted.
- Users usually prefer engine work to abbreviation, so budget for the bigger change: widen boxes, add lines or pages, move to free space.

### Width gate (before any translator dispatch)

Translators write to the limits you give them; a guessed limit means a re-fit pass over every batch. Measure each box variant in-game with the marker build or a stress build (`--qa ID=text`-style override of single lines), and record px/chars and lines per variant in the project's window data:
- portrait box vs no-portrait box;
- name tag (also try the longest glossary name);
- narration;
- choices;
- the last line, where the page-wait arrow takes space;
- menus, labels, item and skill names.

Then boot a **glyph torture line**: all printable ASCII plus double spaces, so missing glyphs and wrong widths show at once. When the marker build hangs, bisect by tables (half the lines marked, half original) until one entry is left.

Measure every game fresh; limits from another game, even the same engine, have been wrong. The lint warns on any line whose box variant has no measured budget yet.

**Done when** every variant has a measured budget and the torture line renders correctly.

## Checks

Wire all of these into the one-command check (Step 0) so the pre-commit hook runs them.

- **Text lint**, per line:
  - pixel width from the font's width table (VWF) or byte budget;
  - lines per page;
  - control-code multiset JP == EN;
  - ASCII/encodable;
  - glossary terms (JP term present ⇒ EN form required; an "Avoid" column for banned spellings);
  - no ordinal suffix after a variable.
- **Keep output quiet.** Print errors and a count, and roll known-OK warnings into one summary line. A check that printed 2,476 warnings got grepped away by the agent, real ones included.
- **ROM-level checks:**
  - `scripts/romdiff.py` with an allowed-ranges file: nothing written outside text banks, pointer slots and free space. This catches writes that wipe flag bytes or graphics.
  - Free-space overflow raises an error instead of silently wrapping.
  - Graphics chunks stay inside the windows the code can reach.
- **Leftover Japanese:**
  - text side: regex `[぀-ヿ一-鿿]` over every `en`;
  - ROM side: `scripts/jp_left.py`. Best: `--slots FILE` listing every pointer slot your insert step writes, so only text a pointer reaches is reported (on one game 185 `--gba-ptrs` hits became 0 real ones); `--known FILE` lists intended-Japanese offsets to skip. On GBA without a slot list, run `--gba-ptrs` **without** `--orig`. Relocation leaves the old Japanese unreferenced, and broken pointers can land mid-line in it; `--orig` hides that case, because the bytes the pointer lands on differ from what was at that offset originally. Add `--halfwidth` for debug and system text, then triage, since it is noisier;
  - runtime side: the draw-hook scan (`emulator-qa.md`).
  - A text-side check alone once passed with 3 Japanese lines still reachable behind a pointer table.
- **Release gate:** lint → roundtrip → build → tests → smoke → `jp_left.py`, stop at the first failure.

## Pitfalls that reached a user's playtest

Check for these before handing a build over:
- A menu froze when a description hit the wrap column.
- The VWF buffer was wiped by a window clear or map scroll, giving a black bar.
- A second copy of a string sat glued to a data table and showed garbage like "zb". **Search all copies of a string.**
- Text overflowed a fixed load buffer and showed garbage like "j)". Enforce buffer sizes in the build.
- Names stored in save files showed the old names on old saves. Fix on load.
- Timed cutscenes cleared the page before English (2× the glyphs) finished typing. Measure display time per page, then halve the waits or speed up typing.
- Greedy wrap left one-word widows. Use balanced wrap.
- A fix applied to only one of two duplicate justify routines ("Sa ve").
- A moved string kept one stale pointer: strings can have several (MIPS `lui`/`addiu` pairs, ARM literal pools, a second table). Find all before relocating.
- A player-entered or renamed name broke after save → reload. Test the round trip for any name the game saves.
- Headers and labels sat off-centre, and grey-out (disabled item) spans covered the wrong letters: both come from per-label tables sized for Japanese. Re-centre and regenerate the span tables from the English widths.
- Timers, counters and other digits the code draws were "translated". Keep native digits the code writes; translate only the text around them.

Tool-side pitfalls:
- JSON written on Windows got CRLF and churned every diff: open writers with `newline='\n'`.
- Pillow text rendering differs between machines: use `layout_engine=ImageFont.Layout.BASIC`.
- Windows-reserved file names (`CON`, `AUX`, `NUL`, `PRN`, `COM1`) as scene or file ids break checkout; prefix them.

## Building on an earlier patch

When an older fan patch exists and the user wants to build on it:
- Apply the old patch to a clean original and use that as the base ROM; record both hashes. The identity test runs against the patched base.
- Diff base vs original (`romdiff.py`) to map what the old patch touched: text, relocated blocks, code hooks.
- Relocated text leaves its old Japanese orphaned. Once no pointer reaches it (`jp_left.py --gba-ptrs`-style check, or your pointer dump), that space is free for reuse.
- Ship one combined patch against the clean original, or document the apply order; credit the earlier authors.

## Release

- **Patch only, no ROM data:**
  - BPS for SNES (`scripts/bps.py make`, which re-applies and verifies);
  - xdelta3 for disc images, NDS and >16 MiB GBA;
  - IPS only for ≤16 MiB legacy.
- Fix the SNES checksum in the release step (`bps.py snes-checksum`), not in the build, so the identity build stays byte-identical.
- **Apply the finished patch to a clean original and compare** before shipping.
- **README:**
  - base ROM name, size, CRC32/MD5/SHA-1 (No-Intro name for carts, Redump link for discs);
  - patched CRC32;
  - which emulator it was tested in;
  - a cold-boot note;
  - known issues, credits (respect prior patch authors), AI-assistance disclosure;
  - "unofficial, no pre-patched ROMs".
- Zip = patch(es) + README/PATCHING.txt only, with no .cue. Name it `Game_EN_vX.Y.bps`. Use ZIP_STORED for xdelta.
- Release dirs stay local and gitignored. Publishing is the user's call.
