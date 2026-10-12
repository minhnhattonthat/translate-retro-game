-- Dump work RAM every RAM_EVERY frames (default 60) to <out>/ram_<frame>.bin, for ramsearch.py.
--   emu.py ... --script probes/ramdump.lua [--var RAM_EVERY=30]
-- Layout per system: see L.dump_ram in the driver library (SNES WRAM, GBA EWRAM+IWRAM, NDS/PS1 main RAM).
local every = RAM_EVERY or 60
L.on_frame(function(f)
  if f % every == 0 then L.dump_ram(string.format("ram_%06d.bin", f)) end
end)
