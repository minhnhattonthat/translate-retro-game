# Cases by symptom

Failures from other translation projects, found by what you see rather than by cause. Scan the **Symptom** column when a bug resists the first fix, or before adding a second special case for the same thing. A case suggests where to look; it doesn't prove the cause in this game. Most come from the Korean-patch skill at github.com/mcpads/create-retro-game-kr-patch (`references/tips/`, MIT), whose files carry the full evidence.

## Space, pointers and text structure

| Symptom | What it turned out to be | Check |
|---|---|---|
| Code or data put in "unused" space crashes on boot, or only on entering one area | Zero-filled space was live: overwritten conversion code; a function with no direct calls was called through a pointer | Fill the candidate with a trap byte (0xFF or a BRK/invalid opcode) and tour; no hit on one route doesn't prove the range is free everywhere |
| Translating one scene garbles the next one | The next pointer is not a string end: several scenes shared one tail and terminator | Take string ends from the terminator the reader stops at, never from the next pointer |
| A pointer lands mid-sentence after relocation | Interior pointer into a translation record; its byte distance from the start no longer holds | Split records at every pointer target, or keep the containing structure in place |
| Moving a string with no pointer changes the neighbouring names | Code reads that string at a fixed address | No pointer found doesn't mean it can move; leave it in place or find the reader |
| Deduplicating identical strings broke another menu | Identical text, different pointer slots with different readers | Keep one slot per source pointer; dedupe only in the translation memory |
| Clearing a zero-length entry makes the game print garbage | Length 0 meant "string supplied at runtime", not empty | Leave such entries alone until you know the reader |
| Text decodes fine up to a control code, then everything after shifts | Token width follows the reader's unit (2-byte codes in a 1-byte-looking stream), or the terminator is a multi-byte sequence | Get argument counts from the reader, not from what the text looks like |
| A fixed-length field hangs, shows a blank page or a bad glyph | Truncation cut a multi-byte token, or the padding byte was read as a character or control | Truncate at a whole token; pad with the value the original uses after the terminator |
| Short lines leave old letters in a scrolling buffer | The reused buffer clears only what is written | Write explicit spaces over the rest of the slot |
| A relocated "jump"/"call" control returns to the wrong text | Its return target was the physical next byte | Rebuild the return target explicitly after moving it |
| An item's name shows but using the item fails | The label's address was also the item's ID for comparisons | Grep code for the old address as a constant before moving labels |
| Only one rare branch corrupts | It reads a table-tail entry the extractor dropped | Extract and rewrite fixed tables whole |
| Several growing regions leave some pointers wrong or adjusted twice | Shifts computed on a partly patched buffer | Plan every shift in original coordinates, apply from the end backward |
| One translated string freezes a later, unrelated screen, or a name comes out cut ("Piyori") | The string is copied into a fixed RAM field or save-data slot sized for the Japanese | Bisect: build with half the entries translated, warp to the screen, repeat; then a per-id byte cap in the lint |
| A Yes/No prompt crashes, or "No" draws past the window | The wrap tool rewrote the line break before the choice (plain newline → indent code) | Keep every control code before a choice exactly as in the JP; lint the line structure in front of choices |
| A label stays Japanese, but no string or pointer for it exists | The code builds it from glyph codes in instruction immediates | Grep code for the codes as immediates (`pipeline.md` §Extract) |

## Compression and assets

| Symptom | What it turned out to be | Check |
|---|---|---|
| A recompressed block breaks in game though your round trip passes | The compressor referenced output bytes not yet produced (zeros); your decompressor allowed it, the game's didn't | Recompress the *unchanged* original block and boot it: fails ⇒ compressor bug, passes ⇒ your edit |
| New glyphs are in the expanded file but stay blank in RAM/VRAM | A separate decompressed-size constant still held the old length | Compare live memory with your decompressed file; find where it stops |
| Adding one asset entry halts before the title, file size unchanged | An internal entry table/count wasn't grown | Parse the container's own index, not just its size |
| A later page of a file fails though the file is aligned | Internal structures have their own alignment | Check each directly loaded structure's alignment |
| Edited bytes match VRAM but the screen is still unreadable / a read breakpoint fires but edits change nothing | The read was RAM reuse or a copy, not the drawing reader | Prove it with a visible edit on screen, not a read hit |
| Only live glyphs are known, source is compressed | — | Decompress every block and search for several runtime glyphs (`vramfind.py`) |
| A font replacement vanishes after character or mode select | That state loads a different font asset | Hook the load after the state change too |
| Name-entry grid changes but the confirmed name doesn't (or the reverse) | The grid was pre-rendered graphics, the name used the font | Change both; test grid, editing, confirm and later redisplay |

## Graphics and VRAM

| Symptom | What it turned out to be | Check |
|---|---|---|
| A patched logo or subtitle appears, then reverts | A later original transfer wrote the same VRAM | Log every write to the range (`snes_dmalog.lua`); patch after the last writer or suppress only that transfer |
| No write appears when the screen opens, label unchanged | Preloaded earlier (OBJ tiles at boot or in an earlier scene) | Start logging from cold boot; a savestate or late breakpoint misses one-time uploads |
| Japanese remains after replacing the background | Another layer or sprite carries the same text | Dump every BG layer and OAM on the screen |
| A translated save/menu screen loses slot names or confirm text | A static tilemap overlay overwrote cells the game updates at runtime | Exclude dynamic cells from the overlay; test empty and full slots, confirm, cancel, re-entry |
| An NMI or post-DMA graphics hook also fires on neighbouring screens | Trigger keyed too broadly | Key the hook on the screen's own state or the asset's identity |
| Outlines or gradients break at tile seams | Each tile rendered separately | Render the whole label, then cut into tiles |
| Changing one glyph or tile damages other labels or digits | The slot has several readers | Find every screen using it before editing in place (`vramfind.py --others`) |
| The selection highlight covers only the first few letters | Highlight width came from the source string's length, not the highlight data alone | Patch the length the code reads, too |
| Glyphs fit their cells but are clipped in game | The renderer draws fewer rows than the cell has | Measure the drawn ink rows; lint glyph height against them |
| A second cursor or old arrow stays on screen | The VWF skips blank pixels, so the blank glyph meant to erase the old arrow draws nothing | Draw blank glyphs opaque (background colour) |
| A symbol (♫) or a save-slot label (持金) draws as garbage after freeing "unused" kanji tiles | Something still drew those tiles: stitched fragments, system messages, labels outside the script | Build the keep-set from every text source (script, code strings, system messages, fragments, labels); test that each glyph in it keeps its tiles |

## Discs and platforms

| Symptom | What it turned out to be | Check |
|---|---|---|
| A patch at a known offset hits the wrong sector | Offset was for a 2048-byte "cooked" ISO, image is 2352-byte raw with a pregap | Convert: sector = off / 2048, raw = (sector + pregap) × 2352 + header + off % 2048, header 16 for Mode 1, 24 for Mode 2 Form 1 (PS1); pregap from the CUE INDEX lines |
| Relocated file corrupts a later movie | The "gap" was another file's extent | Place data only after every extent the directory lists |
| PSP: game works but stalls when the player accepts "install data" | Install payload removed, install option still reachable | Boot with no save and accept every first-run prompt |
| PS1: a hook in code reloaded at runtime acts half-patched | Trampoline spans two I-cache lines, one stale | Keep the trampoline in one cache line; run the hook body through the uncached KSEG1 alias (`0xA0…`) |
| PC Engine: an immediate in a handler looks like a bank number | It was a BIOS scheduler argument | Read MPR state at the call, not the constant |

## Process

| Symptom | What it turned out to be | Check |
|---|---|---|
| After fixing the decoder, some translations are now wrong | They were written from the old, wrong `jp` text | Diff old vs new `jp` per id; re-queue every changed id for translation |
| A translator gave the wrong speaker or turned narration into speech | Batch had strings without scene/speaker context | Ship speaker and lead-in lines in the batch (`translation.md` §Batch design) |
| English voice lines end early / text runs ahead of audio | Wait frames and per-glyph display time, not byte length, drove timing | Measure display time per page against the voice clip |
| A shot looks clipped or shows residue | A mid-animation frame | Check the frames before and after (`sheet.py --from --to`) before filing it |
| Each fix breaks a different screen | Rebuilding after every defect, before the rest of the tour was classified | Finish the tour on one build, group defects that share a cause, then rebuild and rerun the same routes |
| Removing the suspected hook doesn't change the bug | Wrong suspect (it was a WRAM collision) | Treat that as ruling out a single cause, not as proof it's innocent in combination |
| A token copied from an earlier patch behaves differently | Same bytes, different meaning in this engine | Confirm each control code in this game |
| A playtester's bug won't go away whatever you change | It is the original game's behaviour (title art, doubled rows, a black screen after a battle) | Replay the cited step on the original ROM first (`play.py --route`, `emulator-qa.md` §Agent playtest) |
| A route's presses do nothing from a user's savestate | The state was taken in the title attract demo, which ignores input | Check for a demo before debugging the route; a demo is also a free deterministic test |
