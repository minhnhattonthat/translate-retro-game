-- PCSX-Redux (PS1) driver library, LuaJIT. emu.py prepends globals: OUT, ERRFILE, ROUTE_STEPS, FRAMES, SHOT_EVERY,
-- SHOTS, STATE_IN, STATE_OUT, MASH, MASH_KEY, and passes this file with -dofile. A user script (--script) is
-- appended after the driver and may use L.*. Screenshots are written as .psx (5-byte header + raw 16/24-bit
-- pixels); emu.py converts them to PNG. Files go through Support.File (PCSX-Redux's own file API).
L = { frame = 0 }

local logf = Support.File.open(OUT .. "log.txt", "TRUNCATE")
function L.log(s) logf:write(tostring(s) .. "\n") end
function L.shot(name)
  local s = PCSX.GPU.takeScreenShot()
  local f = Support.File.open(OUT .. (name:gsub("%.png$", ".psx")), "TRUNCATE")
  f:write(string.char(s.width % 256, math.floor(s.width / 256), s.height % 256, math.floor(s.height / 256),
                      tonumber(s.bpp)))
  f:write(s.data); f:close()
end
local quitting = false
function L.finish(code) if not quitting then quitting = true; logf:close(); PCSX.quit(code or 0) end end
function L.fail(msg)
  local f = Support.File.open(ERRFILE, "TRUNCATE"); f:write(tostring(msg) .. "\n"); f:close()
  L.finish(2)
end
-- Errors inside event listeners only reach the log: wrap every callback so errors exit 2.
function L.safe(fn) return function(...) local ok, e = pcall(fn, ...); if not ok then L.fail(e) end end end
-- Exec breakpoints need the debugger and the interpreter: emu.py --debugger. Keep the returned object alive.
local bps = {}
function L.on_exec(addr, fn) bps[#bps + 1] = PCSX.addBreakpoint(addr, "Exec", 4, "emu.py", L.safe(fn)) end
function L.save_state(path)
  local f = Support.File.open(path, "TRUNCATE"); f:writeMoveSlice(PCSX.createSaveState()); f:close()
end

local B = PCSX.CONSTS.PAD.BUTTON
local KEYS = { cross = B.CROSS, circle = B.CIRCLE, square = B.SQUARE, triangle = B.TRIANGLE, l1 = B.L1, r1 = B.R1,
               l2 = B.L2, r2 = B.R2, start = B.START, select = B.SELECT, up = B.UP, down = B.DOWN, left = B.LEFT,
               right = B.RIGHT }
local function parse(spec)
  local p = {}
  if spec ~= "-" then
    for name in spec:gmatch("[^+]+") do p[KEYS[name:lower()] or error("unknown PS1 key: " .. name)] = true end
  end
  return p
end

local queue = {}
function L.press(spec, frames) queue[#queue + 1] = { p = parse(spec), frames = frames } end
function L.route_done() return #queue == 0 end
for _, s in ipairs(ROUTE_STEPS or {}) do L.press(s[2], s[1]) end

local pad = PCSX.SIO0.slots[1].pads[1]
local held = {}
local function apply(p)
  for _, b in pairs(KEYS) do
    if p[b] and not held[b] then pad.setOverride(b) elseif held[b] and not p[b] then pad.clearOverride(b) end
  end
  held = p
end

local frameFns = {}
function L.on_frame(fn) frameFns[#frameFns + 1] = fn end

local shotset = {}
for _, f in ipairs(SHOTS or {}) do shotset[f] = true end
local NONE = {}
VSYNC = PCSX.Events.createEventListener("GPU::Vsync", L.safe(function()
  if quitting then return end
  if L.frame == 0 and STATE_IN then PCSX.loadSaveState(Support.File.open(STATE_IN)) end
  L.frame = L.frame + 1
  local n = L.frame
  local q = queue[1]
  if q then
    apply(q.p)
    q.frames = q.frames - 1
    if q.frames <= 0 then table.remove(queue, 1) end
  elseif (MASH or 0) > 0 and n % MASH < 6 then apply(parse(MASH_KEY or "cross"))
  else apply(NONE) end
  if ((SHOT_EVERY or 0) > 0 and n % SHOT_EVERY == 0) or shotset[n] then L.shot(string.format("f%06d.png", n)) end
  for _, fn in ipairs(frameFns) do fn(n) end
  if FRAMES and n >= FRAMES or (not FRAMES and L.route_done()) then
    L.shot("final.png")
    L.log("final frame " .. n)
    if STATE_OUT then L.save_state(STATE_OUT) end
    L.finish(0)
  end
end))
