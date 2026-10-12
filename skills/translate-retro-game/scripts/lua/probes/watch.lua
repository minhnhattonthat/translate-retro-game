-- Who reads or writes an address range? Logs one line per distinct PC: frame, pc, address, the hook's extra args.
--   emu.py ... --script probes/watch.lua --var WATCH_LO=0x7E1000 [--var WATCH_HI=0x7E10FF] [--var WATCH_MODE='"read"']
--              [--var FROM=600 --var TO=900]
-- All emulators (mGBA needs 0.11+; PS1 needs --debugger). SNES also hooks the other bank mirror.
local lo = assert(WATCH_LO, "set --var WATCH_LO=0x...")
local hi, mode, from, to = WATCH_HI or lo, WATCH_MODE or "write", FROM or 0, TO or math.huge
local seen = {}
local function hit(addr, ...)
  if L.frame < from or L.frame > to then return end
  local pc = L.pc()
  if seen[pc] then return end
  seen[pc] = true
  local extra = {}
  for i = 1, select("#", ...) do extra[#extra + 1] = tostring((select(i, ...))) end
  L.log(string.format("f%d %s pc=%08X addr=%08X %s", L.frame, mode, pc, addr or 0, table.concat(extra, " ")))
end
if mode == "read" then L.on_read(lo, hi, hit) else L.on_write(lo, hi, hit) end
