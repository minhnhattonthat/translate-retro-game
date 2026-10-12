-- mGBA (GBA) driver library. emu.py prepends globals: OUT, ERRFILE, ROUTE, FRAMES, SHOT_EVERY, SHOTS,
-- STATE_OUT, STATE_EVERY, MASH, MASH_KEY (state-in is loaded by emu.py via the -t flag). A user script (--script)
-- is appended after the driver and may use L.*.
L = { frame = 0 }

local logf = assert(io.open(OUT .. "log.txt", "w"))
function L.log(s) logf:write(tostring(s) .. "\n"); logf:flush() end
local function outpath(p) return (p:match("^%a:") or p:match("^/")) and p or OUT .. p end
function L.write_file(path, data) local f = assert(io.open(outpath(path), "wb")); f:write(data); f:close() end
-- Watchpoints need mGBA 0.11+ (dev builds); 0.10 has no memory callbacks. fn(addr, value).
local watches = {}
local function arm(w) w.id = emu:setRangeWatchpoint(w.f, w.lo, w.hi, w.kind) end
local function watch(lo, hi, kind, fn)
  if not emu.setRangeWatchpoint then error("L.on_read/L.on_write need mGBA 0.11+ (setRangeWatchpoint)") end
  local cb = L.safe(fn)
  local w = { lo = lo, hi = hi, kind = kind, f = function(info) cb(info.address, info.newValue or info.oldValue) end }
  arm(w); watches[#watches + 1] = w
end
function L.on_read(lo, hi, fn) watch(lo, hi, C.WATCHPOINT_TYPE.READ, fn) end
function L.on_write(lo, hi, fn) watch(lo, hi, C.WATCHPOINT_TYPE.WRITE, fn) end
function L.pc() return emu:readRegister("pc") end
-- A watchpoint firing during the script's own readRange or screenshot deadlocks mGBA: lift them meanwhile.
local function quiet(f)
  for _, w in ipairs(watches) do emu:clearBreakpoint(w.id) end
  f()
  for _, w in ipairs(watches) do arm(w) end
end
function L.shot(name) quiet(function() emu:screenshot(OUT .. name) end) end
-- <prefix>.vram.bin (96 KB), .pal.bin (1 KB: BG then OBJ), .oam.bin (1 KB), .io.bin (LCD registers
-- 0x04000000-0x0400005F: DISPCNT, BGxCNT, scroll). A relative prefix lands in --out.
function L.dump_ppu(prefix)
  prefix = prefix or "ppu"
  quiet(function()
    L.write_file(prefix .. ".vram.bin", emu:readRange(0x06000000, 0x18000))
    L.write_file(prefix .. ".pal.bin", emu:readRange(0x05000000, 0x400))
    L.write_file(prefix .. ".oam.bin", emu:readRange(0x07000000, 0x400))
    L.write_file(prefix .. ".io.bin", emu:readRange(0x04000000, 0x60))
  end)
end
-- EWRAM (256 KB) then IWRAM (32 KB): file offset 0x40000 = 0x03000000.
function L.dump_ram(path)
  quiet(function() L.write_file(path, emu:readRange(0x02000000, 0x40000) .. emu:readRange(0x03000000, 0x8000)) end)
end
function L.finish(code) logf:close(); os.exit(code or 0) end
function L.fail(msg)
  local f = io.open(ERRFILE, "a"); f:write(tostring(msg) .. "\n"); f:close()
  os.exit(2)
end
-- mGBA swallows Lua errors and keeps running: wrap every callback so errors exit with code 2.
function L.safe(fn) return function(...) local ok, e = pcall(fn, ...); if not ok then L.fail(e) end end end

local KEYS = { a = "A", b = "B", start = "START", select = "SELECT", up = "UP", down = "DOWN",
               left = "LEFT", right = "RIGHT", l = "L", r = "R" }
local function mask(spec)
  local m = 0
  if spec ~= "-" then
    for name in spec:gmatch("[^+]+") do
      local k = KEYS[name:lower()] or error("unknown GBA key: " .. name)
      m = m | (1 << C.GBA_KEY[k])
    end
  end
  return m
end

local queue = {}
function L.press(spec, frames) queue[#queue + 1] = { keys = mask(spec), frames = frames } end
function L.load_route(path)
  for line in io.lines(path) do
    local l = line:gsub("#.*", ""):match("^%s*(.-)%s*$")
    if l ~= "" then
      local n, spec = l:match("^(%d+)%s+(%S+)$")
      if not n then error("bad route line: " .. line) end
      L.press(spec, tonumber(n))
    end
  end
end
function L.route_done() return #queue == 0 end

-- Keys must be applied in keysRead: setting them in the frame callback races the Qt frontend's polling.
local cur = 0
callbacks:add("keysRead", L.safe(function() emu:setKeys(cur) end))

local frameFns = {}
function L.on_frame(fn) frameFns[#frameFns + 1] = fn end

local shotset = {}
for _, f in ipairs(SHOTS or {}) do shotset[f] = true end
local ending = false
local function begin() if ROUTE then L.load_route(ROUTE) end end
L.safe(begin)()

callbacks:add("frame", L.safe(function()
  L.frame = L.frame + 1
  local n = L.frame
  local q = queue[1]
  if q then
    cur = q.keys
    q.frames = q.frames - 1
    if q.frames <= 0 then table.remove(queue, 1) end
  elseif (MASH or 0) > 0 and n % MASH < 6 then cur = mask(MASH_KEY or "a")
  else cur = 0 end
  if ((SHOT_EVERY or 0) > 0 and n % SHOT_EVERY == 0) or shotset[n] then L.shot(string.format("f%06d.png", n)) end
  if (STATE_EVERY or 0) > 0 and n % STATE_EVERY == 0 then emu:saveStateFile(string.format("%ss%06d.ss0", OUT, n), 31) end
  for _, fn in ipairs(frameFns) do fn(n) end
  local stop = FRAMES and n >= FRAMES or (not FRAMES and L.route_done())
  if stop and not ending then
    ending = true
    L.shot("final.png")
    L.log("final frame " .. n)
    if STATE_OUT then emu:saveStateFile(STATE_OUT, 31) end
    L.finish(0)
  end
end))
