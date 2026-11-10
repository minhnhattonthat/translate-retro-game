# Graphics brief - <Game title> (<platform>)

You redraw Japanese text drawn as graphics (banners, plates, menu sheets, credits) in English for a fan patch.
Work only on the groups named in your dispatch, one at a time in the order given, each one finished before the next.
Do all the drawing yourself; do not dispatch subagents.

## Read first
1. `work/gfx/<group>.txt` - your rows: source path, size, palette or font class, and the pilot group to copy.
2. The pilot's `gfx/<pilot>.tsv`, and the generator `tools/gfx.py` with its `--help` - how this game's images are
   made. Copy the pilot's approach; don't invent another one.
3. `glossary.md` and `docs/fonts.md` - names exactly as in the glossary; only fonts under `fonts/`.
4. `$SKILL/references/graphics.md` §Edit and re-import, §Lettering, and §When the text is a texture.

## You may write only
- `gfx/<group>.tsv` (the translations), `gfx/out/<group>/` (images), and `tools/gfx_<group>.py` if the shared generator
  can't do something. Don't edit `tools/gfx.py`, the build, `glossary.md` or another group's files; don't run the build
  or an emulator, and don't commit. If you need a change to shared code, describe it in your report.

## Style
- One font, size and fill per label class, the same one the pilot uses for that class.
- Full words, no abbreviations to fit; condense (`xscale`) or use the narrow font first. If something still won't fit,
  report it with the shortest wording you'd accept.
- Match the original's colour, outline or glow and position; inpaint over artwork, don't clear it to a flat colour.

## Check every image, offline
- `python -X utf8 $SKILL/scripts/sheet.py EN.png --compare JP.png --zoom 3 --out <scratch>.png` and read it: every
  letter readable, nothing left of the Japanese.
- `python -X utf8 $SKILL/scripts/rectcover.py JP.png x,y,w,h..` on each clear rect exits 0.
- No pixel changed outside the rects you declared (the generator's diff check, as the pilot runs it).

## Report (your final message)
Per group: rows done, rows not done and why, new terms (`JP<TAB>EN`), shared-code changes you need.
