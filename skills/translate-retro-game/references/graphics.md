# Graphics text reference

Title logos, menu labels, battle banners, name plates and signs are often tiles, not strings. They are **in scope by default**: users asked for them in most past projects, and each one took 1–3.5 h when it was discovered late. Survey them in recon so the cost is known up front.

## Survey (recon, phase 1)

Tour the game with `emu.py` and list every screen whose Japanese did not change in the marker build. For each: screen name, savestate, BG layer or sprite, and a first guess at the source (raw tiles, compressed block, font-drawn into VRAM at runtime). Record the list in `docs/re/graphics.md`.

**Done when** every Japanese-on-screen element from the marker tour is either a known string or a row in that list.

## Find the source

1. **Dump the video state** on the screen: `emu.py ... --script $SKILL/scripts/lua/probes/ppudump.lua --var DUMP_AT=<frame>`, or `L.dump_ppu("title")` from your own hook, writes `title.vram.bin`, `.pal.bin` and `.oam.bin` into `--out` (file layouts: `emulator-qa.md` §Hooks). `snes_dmalog.lua` shows which ROM or WRAM source fed the tiles.
2. **Render it:** `tiles.py render` turns the VRAM dump into a tile sheet (pick the format the layer uses; SNES BG modes give the bpp), and `tiles.py map` draws a BG layer from its tilemap as the screen shows it. Sprites: read tile numbers from the OAM dump and render those tiles. Look at the render, not the emulator shot, to see which tiles carry the text.
3. **Match it to the ROM:** `vramfind.py` searches the ROM, and directories of decompressed blocks, for the dumped tiles (it matches unflipped tiles only). No raw match means compressed graphics: decompress every block you can find (`docs/re/` compression notes) and search again. Still nothing means the game draws it at runtime from the font, which is text work, not graphics.
4. **Confirm before editing:** corrupt the matched bytes (fill with 0xFF), boot, and shoot the screen. The text breaks ⇒ that is the source. Several matches ⇒ corrupt one at a time.

## Edit and re-import

- **Fixed palette indices.** `tiles.py render` with the palette dump, draw in those colours only, and re-import with the `tiles.py import` command it prints. The importer refuses colours outside the palette; save as RGB/RGBA PNG (it refuses indexed PNGs), and keep the editor from dithering or smoothing.
- **Pixel font, drawn or traced per glyph.** A downscaled TrueType font turns to mush at 8 px. Zoom in (`sheet.py --zoom 4`) on the in-game shot and check every letter before handover.
- **Shared tiles:** a tile used by another screen (`vramfind.py --others other.vram.bin` marks it `shared`, `dup:N` means several ROM copies) must not be edited in place. Allocate new tiles and point this screen's tilemap at them.
- **Tilemaps can be record streams** (run-length, per-row headers), not flat arrays. Decode the format before moving tiles, and roundtrip-test it like text.
- **More tiles than the original:** free VRAM slots exist only if no other scene loads there. Check with dumps from neighbouring screens before claiming a slot.
- Recompress and write through the same block writer as text, so `romdiff.py` ranges and free-space checks cover graphics too.

**Done when** each row in `docs/re/graphics.md` is English in a cold-boot shot you have looked at zoomed in, or is marked "kept Japanese" with the user's agreement.

## When the text is a texture (PSP, 3D-era handhelds)

There are no tiles or VRAM dumps to chase: images are stored whole (PSP: GIM) inside archives. Find them by unpacking the game, not by tracing the screen. Contact-sheet every unique image, redraw the Japanese ones at the same pixel size, and let the build write them back byte-for-byte compatible (`platform-psp.md`; `typeset.py`, `gim.py`, `showgim.py`). Rules that held:
- Match the original's look: copy its colour (`typeset.dominant`), its width (condensed fonts + `xscale` for tall narrow lettering), its glow or outline. Read the layout file for the sprite's real size and anchor so text sits where the sprite is drawn.
- Remove old text over artwork with `typeset.inpaint`, then draw; a flat clear leaves a hole.
- Keep each redraw script in the repo (`tools/gen_gfx.py`-style, one section per screen, a dictionary of translations): rerunning it regenerates every PNG, so a wording change costs one command.
- Check every replacement next to the original, then once in the emulator; row-wise bands (`bands()`/`segments()` helpers in the generator) find the original text rows to redraw at the same places.
- Translations of text pictures are listed with the same glossary as any text; put per-line strings in a tsv beside the generator (`notes/subs.tsv`-style).
