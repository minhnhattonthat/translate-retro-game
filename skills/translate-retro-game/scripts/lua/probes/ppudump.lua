-- Dump video memory with L.dump_ppu at frame DUMP_AT (default FRAMES - 1), or every DUMP_EVERY frames:
-- <out>/ppu_<frame>.vram.bin / .pal.bin / .oam.bin (+ .ppu.txt SNES, .io.bin GBA/NDS) for the tile tools.
--   emu.py ... --frames 900 --script probes/ppudump.lua [--var DUMP_AT=850 | --var DUMP_EVERY=120]
local at = DUMP_AT or (FRAMES and FRAMES - 1)
assert(at or DUMP_EVERY, "set --frames, --var DUMP_AT=N or --var DUMP_EVERY=N")
L.on_frame(function(f)
  if f == at or (DUMP_EVERY and f % DUMP_EVERY == 0) then L.dump_ppu(string.format("ppu_%06d", f)) end
end)
