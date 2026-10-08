-- mGBA (GBA) driver library. emu.py prepends globals: OUT, ERRFILE, ROUTE, FRAMES, SHOT_EVERY, SHOTS,
-- STATE_OUT, MASH, MASH_KEY (state-in is loaded by emu.py via the -t flag). A user script (--script) is
-- appended after the driver and may use L.*.
L = { frame = 0 }

local logf = assert(io.open(OUT .. "log.txt", "w"))
function L.log(s) logf:write(tostring(s) .. "\n"); logf:flush() end
function L.shot(name) emu:screenshot(OUT .. name) end
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
