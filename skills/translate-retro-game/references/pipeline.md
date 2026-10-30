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
- Publish

## Repo layout and text format

- Gitignore `rom/`, `build/`, `work/`, `dist/`/`release/`, `tools/` binaries (assemblers, emulators, disc tools) and savestates.
- Keep in git:
  - `tbl/` (jp and en tables)
  - `asm/` or `patch/`
  - `docs/re/` or `notes/` for reverse-engineering findings
  - `glossary.md` at the root
  - `tools/` for the Python code
- **Target language is a parameter from day one**, even with only English planned. Per language: the text field (`en`, `vi`), the encoder (a fixed table, or codes allocated from the characters the script uses), the glyph source, `glossary_<lang>.md`, the build output name, the release name and the lint. Hardcoding `en` made the second language touch about 12 files. Font code space is shared between text glyphs and any pre-rendered menu cells, so count both against the engine's limit.
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
   - a patch that ships its source (`.asm`, script, `Data/*.bin`) is a free RE map: `grep -nE '^\s*(org|incbin)'` lists every hook site and replaced graphic, usually labelled. Clone it into a scratch dir and don't run its binaries. Verify each address in the emulator before relying on it (revision and copier-header offsets differ), then copy the useful ones into `docs/re/`.
2. **Header and map:** mapping mode, size, checksum, free-space *candidates* (runs of 0x00/0xFF at bank ends). A run of 0x00 or 0xFF is a candidate, not free space: zero-filled ranges have turned out to hold live tables, and code with no direct calls was reached through a pointer. Before using one, fill it with a trap byte (0xFF, or an opcode that crashes visibly) and tour the game, and search code for addresses that point into it. A tour with no hit covers only the routes it took. Space you add past the original ROM end, in banks the mapper reaches, is free.
3. **Compression:** look for game LZ variants and BIOS LZ77/Huffman (GBA). Write a decompressor plus a recompressor, and test the pair byte-for-byte on real blocks. Blocks stored back to back are found in seconds by chaining "this block's end = next block's start". Any brute-force scan needs a guard against a block whose back-references point at itself, or it loops forever.
4. **Text encoding:**
   - find a known on-screen string by relative search (the difference pattern between kana);
   - or log the string-draw routine in the emulator (`references/emulator-qa.md` §Hooks);
   - build `tbl/jp.tbl`;
   - list control codes with their argument counts. A wrong argument count desyncs everything after it.
   - **Confirm the font by hooking the draw call**, not by how glyphs look: games carry several fonts and tables. A table built by eye needs a cross-check against a decoded known string; after fixing it, regenerate every `jp` field from the ROM, diff the old and new `jp` per id, and re-queue every changed id that already has a translation: those were written from the wrong text.
   - Note the text orientation: vertical text, or a handheld game played sideways, changes the whole font and box plan.
   - **Code = font cell, in no standard order** (no Shift-JIS anywhere, relative search finds nothing): look for a small charset file (a UTF-16 list of kana and ASCII), then read the kanji off the font itself. Template-match each cell against a system font for a first guess (~60% right; for 12×12 fonts MS Gothic's built-in 12 px bitmaps got ~90% of kanji, though kana still needed eyes), have reviewer subagents read zoomed labelled cell sheets with 3 script lines per code (only codes the script uses), then have readers scan the whole decoded script for look-alike swaps (大/太). Duplicate values break `encode(decode())`: two codes read as the same kanji means one is wrong or the font has a real duplicate.
5. **Pointers:** find the tables and the format (16-bit + bank, 24-bit, GBA `0x08000000|off`). Note which code reads them.
6. **Graphics text:** survey tile-drawn Japanese (`references/graphics.md` §Survey).
7. Record everything in `docs/re/*.md`, one file per subsystem, with an index line in AGENTS.md/CLAUDE.md. Mark each finding **verified** (with how: decoded known string, corrupt-and-boot, breakpoint on the draw path, roundtrip test) or **guess** (with why), and promote a guess before code depends on it.
8. RE helpers in `$SKILL/scripts/`: `relsearch.py` (relative search), `dis65816.py` (SNES), `disasm.py` (ARM/THUMB/MIPS via capstone), and the Lua probes for ROM-read, DMA and memory watches (`emulator-qa.md` §Hooks). Copy one into `tools/` once you start adapting it.

## Identity build

Unpack → repack with no edits → compare bytes. Make this the first test in the repo and keep it green forever. It proves the compressor, the pointer writer and the image rebuilder before any English exists. Typical forms: an ISO sha1 test for a disc, a byte-identical archive (PAK/NARC) repack, `make verify` printing "identical", a `roundtrip` command over every text block.

## Extract

- Decode every string through the table codec (`scripts/tbl.py`). Unknown bytes become `[XX]` so they roundtrip.
- **Roundtrip test:** `encode(decode(bytes)) == bytes` for every string.
- **Coverage test, run against the ORIGINAL ROM:** the text ranges are fully covered, with no unexplained gaps. A gap is usually text you missed, or data you are about to corrupt.
  - Dump every pointer target, including strings referenced from the EXE, arm9/overlays or code banks, not only the script banks.
  - An unknown control code must not end a string: decode it as `[XX]` and keep going, then check the next bytes still decode. Strings silently cut at the first unknown code left the rest Japanese.
  - Punctuation-only lines (`……`, `！！！`, `・・・！`) are text: the game draws them in Japanese punctuation. Filters that skip lines starting with punctuation left 170 of them in one game.
  - Don't assume pointer alignment: an extractor that took only 4-aligned pointers skipped event messages at 2-aligned offsets.
  - Code can reach strings with no pointer of their own: base + immediate (`adds rX,#imm`, a literal offset added to a table base), or glyph codes built as instruction immediates (`LDA #tile` / `STA buf,x` chains; `mov rX,#code` before a store). The marker build shows these as the Japanese that stays; grep code for the codes as immediates.
- **Leading and trailing spaces are part of the text.** A fullwidth `　` indent made room for a cursor (the English sat under it), and a trailing space joined "Level rose to " to a number. Parsers must not strip, and the lint checks that EN keeps every leading/trailing blank the JP has.
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
  - digraph glyphs when the renderer ignores advance widths. Each letter gets half the cell, so no letter may be wider than half the cell minus any shadow or outline the game adds (12 px cell + 1 px shadow: 5 px). A wider letter runs into its neighbour (a 7 px M made "Ma" read "Mb"). Assert the width in the encoder self-test. Names and variables the game inserts at runtime have odd lengths too: an odd-length name leaves a half-cell gap after it ("Doggy  defeated!", "Hiyuu -kun"). Give the encoder a half-width pad glyph, or join the halves where strings are concatenated, and put odd-length default names in the marker build.
  - If you build a glyph cache (English cells loaded on demand into a screen's tile area), it must turn itself off whenever a plain (uncached) charset loads at the same tiles. Otherwise a screen redrawn after a cached sub-screen reads its tile indices as glyph codes and shows garbage.
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

Measure the limit from pixels, not from the engine's cell count: in a zoomed shot, find the last column where a glyph still shows. One game's boxes showed one cell less than the width variable said, so the wrap limit was 4 px too wide. Only lines that landed in that 4-px window got clipped, and they first surfaced in a playtest, across every box type. Test with a line that fills each box to the computed limit exactly.

Then boot a **glyph torture line**: all printable ASCII plus double spaces, so missing glyphs and wrong widths show at once. When the marker build hangs, bisect by tables (half the lines marked, half original) until one entry is left.

Measure every game fresh; limits from another game, even the same engine, have been wrong. The lint warns on any line whose box variant has no measured budget yet.

Never derive a limit from the Japanese length. Limits guessed that way (a 16-character name cap, "~57 px like the JP name") shipped overflow in three games, found by players. How to measure:
- **List fields** (items, skills, names in a menu row): the budget is the x of the next thing drawn on the row (count, price, cost, a divider) minus the field's x, read off a shot showing the longest name.
- **One string, several screens:** it takes the smallest budget among them (a name in the menu, the shop and the battle window).
- **Windows the script opens or resizes** (an open-window opcode with a size argument): scan the script for those opcodes and give their lines per-entry limits. A 20-character box once got the default 30.
- **Scrolling and paged views** (encyclopedia, help, logs): scroll the longest marker to its last line. The scroll or page limit is often a separate table sized from the Japanese line counts; one article stopped scrolling before its end.
- Tag each limit in the window data as measured (with the shot) or guess. A LONG line against a guessed limit means measure it, not abbreviate.

**Done when** every variant has a measured budget and the torture line renders correctly.

## Checks

Wire all of these into the one-command check (Step 0) so the pre-commit hook runs them.

- **Text lint**, per line:
  - pixel width from the font's width table (VWF) or byte budget;
  - lines per page;
  - control-code multiset JP == EN;
  - ASCII/encodable;
  - glossary terms (JP term present ⇒ EN form required; an "Avoid" column for banned spellings);
  - no ordinal suffix after a variable;
  - non-empty `jp` with empty `en` fails, unless the id is in a committed keep-list (`script/keep_jp.txt`, one id and reason per line). "Intentional blanks" silently shipped 41 Japanese fields in one game;
  - leading and trailing blanks match the JP (see §Extract).
- **Stub last lines:** fail a multi-line paragraph whose last line is under ~6 characters (one orphaned syllable or word). It is mechanical, so the lint catches it and no reviewer has to.
- **Tests build their own ROM.** Build into a temp path inside the test (a module-scope fixture per language) instead of reading `build/*.sfc`: a stale artifact passes while the source is broken, and a missing one makes the test skip silently.
- **Keep output quiet.** Print errors and a count, and roll known-OK warnings into one summary line. A check that printed 2,476 warnings got grepped away by the agent, real ones included.
- **ROM-level checks:**
  - `scripts/romdiff.py` with an allowed-ranges file: nothing written outside text banks, pointer slots and free space. This catches writes that wipe flag bytes or graphics.
  - **Log every write with the bytes it expects to replace** and pass the log as `romdiff.py ORIG NEW --writes build/writes.txt`. It then also fails when the original doesn't hold the expected bytes (wrong revision, stale address, a shift computed on an already-patched buffer), when a later write overwrote an earlier one, when two writes overlap, and when a changed byte has no write behind it. Route every write through one function, checksum and pointer fixes included:
    ```python
    def put(rom, off, data, by, orig=ORIG, log=WRITES):   # ORIG: the clean original's bytes, never the work buffer
        log.append("%X %s %s %s" % (off, orig[off:off + len(data)].ljust(len(data), b"\xff").hex(), data.hex(), by))
        rom[off:off + len(data)] = data
    ```
    For a fixed hook site, also assert the original bytes before writing (`assert ORIG[off:off+4] == bytes.fromhex("...")`), so a different revision fails at build time rather than in game.
  - **Every repointed pointer lands on a block header.** For each word in the original ROM that points at a moved block (script, string bank), assert the built ROM's word points at that block's magic (`PAC3`, a length header, whatever the format has). Search with flag bits masked: tables often keep flags in the top bits of the pointer (one GBA game's map tables: `0x88xxxxxx` NPC talk, `0x18xxxxxx` door scripts, read as `& 0x0FFFFFFF`), so a repointer that matches exact `0x08xxxxxx` words misses them. Keep the flag bits when writing the new address. There this missed 74 NPC/door events: talking to one NPC gave a permanent black screen, and the script tour never saw it because it starts scripts directly. Search every data range for them, not only the code literal pools; these tables sat just past the range the build scanned.
  - **Every table the build writes, writes all its entries:** assert per table that the count written equals the entries with English. One insert step skipped a whole table (its field was named differently) and only a playtest found it.
  - **A code hook doesn't swallow a branch target.** For each overwritten code span, disassemble ±4 KB around it and fail if any branch or call (B/Bcc/BL, JMP/JSR/BRA, `j`/`jal`/`b*`) lands strictly inside the span: the game still jumps there into your hook's middle. A menu hook over E5A4–E5B1 ate the newline branch's target at E5AA, and every multi-line menu string lost its later lines.
  - **Relocated strings leave no reader behind:** after moving strings, scan the original ROM's code for references to each vacated address (16/24-bit literals, split bank + offset immediates like 65816 `LDA #bank` / `LDY #ptr`, ARM literal pools, MIPS `lui`/`addiu` pairs) and fail on any the build didn't rewrite. A stale `LDA #$85` left one game's Load screen black.
  - Free-space overflow raises an error instead of silently wrapping. Assembler blocks can collide too: with asar, end each free-space block with `warnpc <next block's start>` (a new `org` silently overwrote the VWF width table and froze the game).
  - Graphics chunks stay inside the windows the code can reach.
- **Leftover Japanese:**
  - text side: regex `[぀-ヿ一-鿿]` over every `en`;
  - ROM side: `scripts/jp_left.py`. Best: `--slots FILE` listing every pointer slot your insert step writes, so only text a pointer reaches is reported (on one game 185 `--gba-ptrs` hits became 0 real ones); `--known FILE` lists intended-Japanese offsets to skip. On GBA without a slot list, run `--gba-ptrs` **without** `--orig`. Relocation leaves the old Japanese unreferenced, and broken pointers can land mid-line in it; `--orig` hides that case, because the bytes the pointer lands on differ from what was at that offset originally. Add `--halfwidth` for debug and system text, then triage, since it is noisier. With a one-byte-per-character table, `--tbl` over a whole ROM is all noise (any byte decodes): check only what a pointer, or the code that sets the text pointer, reaches;
  - runtime side: the draw-hook scan (`emulator-qa.md`).
  - A text-side check alone once passed with 3 Japanese lines still reachable behind a pointer table.
  - Run `jp_left.py` on the marker build too (phase 5), not only at release: what it finds there is text the extractor missed, found before translation instead of after.
- **Release gate:** lint → roundtrip → build → tests → smoke → `jp_left.py` → the screen tour (`emulator-qa.md` §Screen tour) → `qa_gate.py check`, stop at the first failure. The release script runs the tour itself (with an opt-out flag for iteration), so a release cannot skip it.

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
- Name entry: the letter grid and the confirmed name can come from different assets (a pre-rendered grid image, the font for the name). Changing one left the other Japanese or mismatched. Check the grid, editing, the confirmed name, its later redisplay in dialogue and menus, and the default name when the player confirms an empty entry.
- Headers and labels sat off-centre, and grey-out (disabled item) spans covered the wrong letters: both come from per-label tables sized for Japanese. Re-centre and regenerate the span tables from the English widths.
- Timers, counters and other digits the code draws were "translated". Keep native digits the code writes; translate only the text around them.
- Code that centres or steps by glyph count × a fixed cell width breaks with VWF or digraph text: choice rows computed `x = box + 40 − 6 × cells` (options off-centre or missing, 3 user reports), and a name-entry cursor moved in 12 px steps over proportional letters. Hook the shared routine to use pixel widths. Keep a fullwidth space the cursor sits in at its original width.
- A format string sized for a Japanese label (`%s    %02d:%02d`, a 3-tile label) shifted the rest of the row: pad the English label to the same tile count, or change the format.

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
  - a "Translation status" table (template has it): each part of the game (dialogue, menus, graphics, name entry, songs/credits) and whether it is translated or left in Japanese, from `jp_left.py` and `docs/status.md`, not memory;
  - base ROM name, size, CRC32/MD5/SHA-1 (No-Intro name for carts, Redump link for discs);
  - patched CRC32;
  - which emulator it was tested in;
  - a cold-boot note;
  - known issues, credits (respect prior patch authors), AI-assistance disclosure;
  - "unofficial, no pre-patched ROMs".
- Zip = patch(es) + README/PATCHING.txt only, with no .cue. Name it `Game_EN_vX.Y.bps`. Use ZIP_STORED for xdelta.
- **`tools/release.py`** runs, stopping at the first failure: build → tests → smoke → `jp_left.py` → `qa_gate.py check` → debug tool off in this build → patch → re-apply to a clean original and compare → zip. It handles `--help` without building, and refuses to overwrite an existing version's files without `--force` (a `--help` call once overwrote a released patch). Keep the playable patched image in `build/` (the user tests from it); the zip holds only the patch.
- Release dirs stay local and gitignored. Publishing is the user's call.

## Publish (only when the user asks)

Each repo re-derived these steps; they are the same every time.
1. Owner: the account the user names. If they named none, use the owner of the sibling game repos (the template's), and confirm before creating anything: one repo was created under the wrong account. Push with that account's token (`GH_TOKEN=$(gh auth token --user <owner>)`, or `git -c credential.helper='!gh auth git-credential' push`) when the SSH key belongs to another account.
2. Repo `<game-slug>-en`, public, with topics (`fan-translation`, `rom-hack`, the platform) and description `English fan translation of <Game title> (<platform>)`: the real game title, never the repo slug (the localization site and its cover bot read the title from it). README, LICENSE and `.github/FUNDING.yml` come from the template.
3. History holds no ROM, save, savestate or disc image: `git log --all --stat` and check the extensions.
4. `git fetch` and rebase before pushing.
5. `gh release create vX.Y <zip> --title ... --notes-file notes.md`, notes with the base ROM hashes and the patch SHA-1. The guard blocks it until `qa_gate.py check` passes. If the user runs it themselves, give the command as one line.
