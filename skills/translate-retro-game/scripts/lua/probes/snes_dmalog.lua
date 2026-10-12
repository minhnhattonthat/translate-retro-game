-- SNES (Mesen): log every general DMA (write to $420B): caller PC, channel, source, size, B-bus register and the
-- VRAM word address. SRC_LO/SRC_HI filter the 24-bit source (e.g. only ROM: --var SRC_LO=0x808000).
-- Finds where graphics come from: a ROM source is raw tiles; a WRAM source ($7E/$7F) was decompressed first.
--   emu.py ... --script probes/snes_dmalog.lua [--var SRC_LO=0x800000 --var SRC_HI=0xFFFFFF]
local mem = emu.memType.snesMemory
local lo, hi = SRC_LO or 0, SRC_HI or 0xFFFFFF
local function rd(a) return emu.read(a, mem) end
L.on_write(0x420B, 0x420B, function(addr, value)
  for ch = 0, 7 do
    if value & (1 << ch) ~= 0 then
      local b = 0x4300 + ch * 16
      local src = rd(b + 4) << 16 | rd(b + 3) << 8 | rd(b + 2)
      if src >= lo and src <= hi then
        local s = emu.getState()  -- $2116 is write-only; the PPU state holds the VRAM word address
        L.log(string.format("f%d pc=%06X ch%d src=%06X n=%04X bbus=21%02X vram=%04X", L.frame,
          (s["cpu.k"] << 16) | s["cpu.pc"], ch, src, rd(b + 6) << 8 | rd(b + 5), rd(b + 1), s["ppu.vramAddress"]))
      end
    end
  end
end)
