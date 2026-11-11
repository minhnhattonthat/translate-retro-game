# Graphics text reference

Title logos, menu labels, battle banners, name plates and signs are often tiles, not strings. They are **in scope by default**: users asked for them in most past projects, and each one took 1–3.5 h when it was discovered late. Survey them in recon so the cost is known up front.

## Survey (recon, phase 1)

Tour the game with `emu.py` and list every screen whose Japanese did not change in the marker build. For each: screen name, savestate, BG layer or sprite, and a first guess at the source (raw tiles, compressed block, font-drawn into VRAM at runtime). Record the list in `docs/re/graphics.md`.

Screens that only show mid-game are the ones that get missed: chapter and title cards, area-name banners, "To be continued", game over, ending and credits. Warp to each one with the debug tool (one entry per chapter, not only chapter 1) and add it to the list, even if it looks like plain text. `jp_left.py` can't see tiles, so a clean report doesn't cover these.

A tour only sees what it visits. Also do a **static sweep**: render every raw and decompressed graphics region of the ROM (or every image file of a filesystem game) into numbered sheets with an offset index (`tiles.py render`), and give the sheets in chunks to read-only reviewer subagents that list every Japanese cell. Have the sweep script print every region it skipped and why, never drop one silently (a palette that came after its bank hid 193 banks in one survey). Render each block in linear formats too (`gba4`/`gba8`): some games store graphics as linear 4bpp and convert to planar after decompression, and in planar sheets those blocks look like noise (a title menu showed only in linear). Tour-only surveys missed sprite tags (修行中, `Ⓑ➔もどる`), result labels and name-entry keyboards, which shipped Japanese.

**Done when** every Japanese-on-screen element from the marker tour and the static sweep is either a known string or a row in that list.

## Find the source

1. **Dump the video state** on the screen: `emu.py ... --script $SKILL/scripts/lua/probes/ppudump.lua --var DUMP_AT=<frame>`, or `L.dump_ppu("title")` from your own hook, writes `title.vram.bin`, `.pal.bin` and `.oam.bin` into `--out` (file layouts: `emulator-qa.md` §Hooks). `snes_dmalog.lua` shows which ROM or WRAM source fed the tiles.
2. **Render it:** `tiles.py render` turns the VRAM dump into a tile sheet (pick the format the layer uses; SNES BG modes give the bpp), and `tiles.py map` draws a BG layer from its tilemap as the screen shows it. Sprites: read tile numbers from the OAM dump and render those tiles. NDS sprite and BG files come in groups (RGCN tiles, RLCN palette, RCSN screen, RECN cells); the palette may be shared or come after the tiles. An RGCN with the linear flag (0x101) stores pixels row-major, not in 8×8 tiles, and sprite sheets often ship as a tiled and a linear twin: edit both. Look at the render, not the emulator shot, to see which tiles carry the text.
3. **Match it to the ROM:** `vramfind.py` searches the ROM, and directories of decompressed blocks, for the dumped tiles (it matches unflipped tiles only). A tile that occurs twice matches its first copy, so a single-tile match can point at the wrong offset: confirm with two or more distinct tiles. No raw match means compressed graphics: decompress every block you can find (`docs/re/` compression notes) and search again. Still nothing means the game draws it at runtime from the font, which is text work, not graphics.
4. **Confirm before editing:** corrupt the matched bytes (fill with 0xFF), boot, and shoot the screen. The text breaks ⇒ that is the source. Several matches ⇒ corrupt one at a time.

## Edit and re-import

- **Fixed palette indices.** `tiles.py render` with the palette dump, draw in those colours only, and re-import with the `tiles.py import` command it prints. The importer refuses colours outside the palette; save as RGB/RGBA PNG (it refuses indexed PNGs), and keep the editor from dithering or smoothing.
- **Pixel font, drawn or traced per glyph.** A downscaled TrueType font turns to mush at 8 px. Zoom in (`sheet.py --zoom 4`) on the in-game shot and check every letter before handover.
- **Shared tiles:** a tile used by another screen (`vramfind.py --others other.vram.bin` marks it `shared`, `dup:N` means several ROM copies) must not be edited in place. Allocate new tiles and point this screen's tilemap at them.
- **Tilemaps can be record streams** (run-length, per-row headers), not flat arrays. Decode the format before moving tiles, and roundtrip-test it like text.
- **More tiles than the original:** free VRAM slots exist only if no other scene loads there. Check with dumps from neighbouring screens before claiming a slot.
- Recompress and write through the same block writer as text, so `romdiff.py` ranges and free-space checks cover graphics too.
- **Every copy:** after a redraw, search every ROM region and unpacked file for the original pixel bytes. The same image has shipped two or three times (a texture also embedded in a scene file, identical files under two names, three copies of one kanji cell), and only one got the English.
- **Change only what you meant to:** diff each new image against the original and fail on any changed pixel outside the rects you declared. Three rounds of user reports on one logo were pixels lost outside the text (letters of the logo art, the ring around it).
- **Preview under every palette** that uses the image: a selected/highlighted menu state uses another palette, and a stroke invisible in the normal one showed as a strike through "Continue" when selected.
- **Glyphs use the font's colour indices:** new text tiles take the ink and shadow indices of the ROM font they sit beside (one condensed font drawn with index 5 instead of 15 came out purple).

## Lettering (redrawn labels, logos, banners)

- **Open-licence fonts, committed in the repo:** the patch ships the pixels, so draw only with OFL (or similarly free) fonts kept under `fonts/` with their licence files and listed in `docs/fonts.md`, never `C:/Windows/Fonts` (users asked twice to switch, and every redraw was redone). `typeset.py` reads `fonts/`. Free stand-ins: Liberation Sans/Serif/Mono for Arial/Times/Courier, Liberation Sans Narrow (1.07.x; 2.x dropped it, take the release on github.com/liberationfonts) for Arial Narrow, Anton for Impact, TeX Gyre Pagella for Palatino.
- **Pick one font and size per label class** (menu tab, banner, button) before drawing, and one fill index per label; mixing four fonts at sizes 8-30 and per-row fills copied from the Japanese read as "terrible" to the user.
- At 11 px and below, render without antialiasing (or trace per glyph): smoothed small text turns to mush in 4- and 16-colour palettes.
- **Pixel TrueType fonts only at their native size or a whole multiple of it** (native px = unitsPerEm / the font's pixel unit, the gcd of its advance widths; Jersey 10 is 1400/75 = 18.67, not 20). Off-grid, some pixel columns double and others don't: the user saw uneven strokes and a gap after `r`.
- **Slanted, outlined display fonts (Bangers) garble below ~18 px** once a 1 px outline goes round them: counters close up. For small bars and buttons, a plain bold sans (Liberation Sans Bold 14) read cleanly where Bangers 16 didn't. Compare candidates on the real art (`typeset` into the original TIM), not on a flat colour.
- **Every clear rect must cover the whole original glyph,** dakuten, tails and edges included: a rect drawn by eye 1-2 px short leaves stray pixels that read as dirt in game. `rectcover.py ORIGINAL.png x,y,w,h..` (library `spill(px, rect)` on palette indices) reports how far each rect's text runs past it and the rect that covers it; run it on every row in the project check. Packed atlases flag neighbours (a bracket, a coloured end bar) touching the rect: look once at original vs English and keep a waiver list with the reason.

**Done when** each row in `docs/re/graphics.md` is English in a cold-boot shot you have looked at zoomed in, or is marked "kept Japanese" with the user's agreement.

## Parallel redraws
Done one screen at a time in the main thread, graphics text was the longest phase on texture-heavy games: one PSP game took 21 h and about 30 worker sessions in phase 8, mostly credits, banners, name plates and story pages redrawn in a row. Most of that work is repetitive, so give it to parallel agents on a mid-tier model. Do this only when about 20 or more rows remain after the pilot, in groups that share no tiles, VRAM slots or compressed blocks: usually texture and file-based games (PSP, NDS), or a large static set on tile hardware (credits, plates from one block whose source you already found). Otherwise, as on most SNES/GBA games, redraw the rows in the main thread one by one:
1. **Main thread first builds the pipeline and one pilot group** end to end: find the source, a generator (`tools/gfx.py`-style) that reads a translation tsv and writes the images, re-import through the build, then a zoomed cold-boot shot. Freeze the shared generator code and the build after this, as for translators.
2. **Split the remaining survey rows into groups** that don't share a source file or texture (credits, chapter cards, banners, unit plates, menu sheets, story pages). For each group, write a row list in `work/gfx/<group>.txt`: rows, source paths, sizes, palette or font class, and the pilot that shows how it's done.
3. **Dispatch graphics agents with `docs/graphics-brief.md`** (template: `assets/graphics-brief.md`), 3–5 groups per agent ("Read docs/graphics-brief.md and follow it for groups credits banners plates"), up to 4 agents at a time. Use a mid-tier model: in Claude Code, dispatch the `graphics` agent type (the plugin's `translate-retro-game:graphics`, model sonnet). Codex and opencode: the template's `.codex/agents/graphics.toml` / `.opencode/agents/graphics.md`. Each agent writes only its own group's files: `gfx/<group>.tsv`, `tools/gfx_<group>.py` if it needs code of its own, and the PNGs under `gfx/out/<group>/`. Agents never touch the build, the emulator, `glossary.md` or the shared generator; they report new terms and helpers they need.
4. **Agents check offline**: for every image, the original next to the English (`sheet.py --compare`), `rectcover.py` on each clear rect, and a pixel diff outside the declared rects. They return a list of finished rows and anything they couldn't do.
5. **Main thread merges between waves**: merge the terms into the glossary, build, take the cold-boot shots by warping, and send the shots in chunks to visual-QA subagents. Send each fix back to the agent that drew the group (SendMessage) rather than a new agent.

## When the text is a texture (PSP, 3D-era handhelds)

There are no tiles or VRAM dumps to chase: images are stored whole (PSP: GIM) inside archives. Find them by unpacking the game, not by tracing the screen. Contact-sheet every unique image, redraw the Japanese ones at the same pixel size, and let the build write them back byte-for-byte compatible (`platform-psp.md`; `typeset.py`, `gim.py`, `showgim.py`). Rules that held:
- Match the original's look: copy its colour (`typeset.dominant`), its width (condensed fonts + `xscale` for tall narrow lettering), its glow or outline. Read the layout file for the sprite's real size and anchor so text sits where the sprite is drawn.
- Remove old text over artwork with `typeset.inpaint`, then draw; a flat clear leaves a hole.
- Keep each redraw script in the repo (`tools/gen_gfx.py`-style, one section per screen, a dictionary of translations): rerunning it regenerates every PNG, so a wording change costs one command.
- Check every replacement next to the original, then once in the emulator; row-wise bands (`bands()`/`segments()` helpers in the generator) find the original text rows to redraw at the same places.
- Translations of text pictures are listed with the same glossary as any text; put per-line strings in a tsv beside the generator (`notes/subs.tsv`-style).
