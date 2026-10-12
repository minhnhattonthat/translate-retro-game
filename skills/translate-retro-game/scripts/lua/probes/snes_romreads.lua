-- SNES (Mesen): log each distinct (PC, ROM bank) that reads ROM between frames FROM..TO, with registers.
-- Finds the text, font and graphics readers: run a route that reaches the screen, with a narrow frame window.
--   emu.py ... --script probes/snes_romreads.lua --var FROM=1200 --var TO=1260 [--script probes/snes_dmalog.lua]
-- The file offset assumes LoROM (L.rom_off); for HiROM use addr & 0x3FFFFF.
local from, to = FROM or 0, TO or math.huge
local seen = {}
local function hook(addr, value)
  if L.frame < from or L.frame > to then return end
  local s = emu.getState()
  local pc = (s["cpu.k"] << 16) | s["cpu.pc"]
  local key = pc * 256 + (addr >> 16)
  if seen[key] then return end
  seen[key] = true
  L.log(string.format("f%d pc=%06X read %06X (off %06X)=%02X A=%04X X=%04X Y=%04X DB=%02X", L.frame, pc, addr,
    L.rom_off(addr), value, s["cpu.a"], s["cpu.x"], s["cpu.y"], s["cpu.dbr"]))
end
for bank = 0, 0xFF do  -- every bank's ROM half, both mirrors, skipping WRAM banks $7E-$7F
  if bank < 0x7E or bank > 0x7F then
    emu.addMemoryCallback(L.safe(hook), emu.callbackType.read, (bank << 16) | 0x8000, (bank << 16) | 0xFFFF,
      emu.cpuType.snes, emu.memType.snesMemory)
  end
end
