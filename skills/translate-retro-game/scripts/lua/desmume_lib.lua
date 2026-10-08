-- DeSmuME (NDS) driver library, Lua 5.1 (lua51.dll beside the exe). emu.py prepends globals: OUT, ERRFILE, ROUTE,
-- FRAMES, SHOT_EVERY, SHOTS, STATE_IN_SLOT, STATE_OUT_SLOT, MASH, MASH_KEY, and loads this file as
-- <out>/<rom name>.lua through DeSmuME's "auto-load Lua with ROM" setting. A user script (--script) is appended
-- after the driver and may use L.*. Screenshots are written as .gd (both screens, 256x384); emu.py converts them.
L = { frame = 0 }

local logf = assert(io.open(OUT .. "log.txt", "w"))
function L.log(s) logf:write(tostring(s) .. "\n"); logf:flush() end
function L.shot(name)
  local f = assert(io.open(OUT .. (name:gsub("%.png$", ".gd")), "wb"))
  f:write(gui.gdscreenshot()); f:close()
end
function L.finish(code) logf:close(); os.exit(code or 0) end
function L.fail(msg)
  local f = io.open(ERRFILE, "a"); f:write(tostring(msg) .. "\n"); f:close()
  os.exit(2)
end
-- DeSmuME shows Lua errors in its script window and keeps emulating: wrap every callback so errors exit 2.
function L.safe(fn) return function(...) local ok, e = pcall(fn, ...); if not ok then L.fail(e) end end end
-- memory.registerexec(addr, fn) / registerwrite(addr, size, fn), memory.readbyte(addr) etc. are DeSmuME's own.
function L.on_exec(addr, fn) memory.registerexec(addr, L.safe(fn)) end

local KEYS = { a = "A", b = "B", x = "X", y = "Y", l = "L", r = "R", start = "start", select = "select",
               up = "up", down = "down", left = "left", right = "right", lid = "lid" }
-- "a+start" -> buttons; "t128,96" touches the bottom screen at (128,96) for that step.
local function parse(spec)
  local p = { keys = {}, touch = nil }
  if spec ~= "-" then
    for name in spec:gmatch("[^+]+") do
      local x, y = name:match("^t(%d+),(%d+)$")
      if x then p.touch = { x = tonumber(x), y = tonumber(y), touch = true }
      else p.keys[KEYS[name:lower()] or error("unknown NDS key: " .. name)] = true end
    end
  end
  return p
end

local queue = {}
function L.press(spec, frames) queue[#queue + 1] = { p = parse(spec), frames = frames } end
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

local NONE = parse("-")
local cur = NONE
emu.registerbefore(L.safe(function()
  local pad = {}
  for _, k in pairs(KEYS) do pad[k] = cur.keys[k] == true end
  joypad.set(pad)
  stylus.set(cur.touch or { touch = false })
end))

local frameFns = {}
function L.on_frame(fn) frameFns[#frameFns + 1] = fn end

local shotset = {}
for _, f in ipairs(SHOTS or {}) do shotset[f] = true end
local ending = false
L.safe(function()
  emu.speedmode("maximum")
  if ROUTE then L.load_route(ROUTE) end
end)()

local loaded = not STATE_IN_SLOT
emu.registerafter(L.safe(function()
  if not loaded then loaded = true; savestate.load(STATE_IN_SLOT); return end  -- at a frame boundary, not at script start
  L.frame = L.frame + 1
  local n = L.frame
  local q = queue[1]
  if q then
    cur = q.p
    q.frames = q.frames - 1
    if q.frames <= 0 then table.remove(queue, 1) end
  elseif (MASH or 0) > 0 and n % MASH < 6 then cur = parse(MASH_KEY or "a")
  else cur = NONE end
  if ((SHOT_EVERY or 0) > 0 and n % SHOT_EVERY == 0) or shotset[n] then L.shot(string.format("f%06d.png", n)) end
  for _, fn in ipairs(frameFns) do fn(n) end
  local stop = FRAMES and n >= FRAMES or (not FRAMES and L.route_done())
  if stop and not ending then
    ending = true
    L.shot("final.png")
    L.log("final frame " .. n)
    if STATE_OUT_SLOT then savestate.save(STATE_OUT_SLOT) end
    L.finish(0)
  end
end))
