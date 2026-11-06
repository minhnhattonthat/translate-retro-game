-- Mesen (SNES, GBA): log each distinct address the game reads in the text ranges, for scripts/textcover.py.
--   emu.py ... --script probes/textcover.lua --var "RANGES='83AA38-83BE32,03AA38-03BE32'"
-- List every mirror the code may read through: callbacks match the CPU address actually used.
local cpu, mem = emu.cpuType.snes, emu.memType.snesMemory
if SYSTEM == "gba" then cpu, mem = emu.cpuType.gba, emu.memType.gbaMemory end
local seen = {}
local function hook(addr)
  if seen[addr] then return end
  seen[addr] = true
  L.log(string.format("TEXT %X f%d", addr, L.frame))
end
for lo, hi in string.gmatch(RANGES, "(%x+)-(%x+)") do
  emu.addMemoryCallback(L.safe(hook), emu.callbackType.read, tonumber(lo, 16), tonumber(hi, 16), cpu, mem)
end
