-- Mesen2 (SNES) driver library. emu.py prepends globals: OUT, ERRFILE, ROUTE, FRAMES, SHOT_EVERY, SHOTS,
-- STATE_IN, STATE_OUT, MASH, MASH_KEY. A user script (--script) is appended after the driver and may use L.*.
L = { frame = 0 }
local snes, cpuMem = emu.cpuType.snes, emu.memType.snesMemory

local logf = assert(io.open(OUT .. "log.txt", "w"))
function L.log(s) logf:write(tostring(s) .. "\n"); logf:flush() end
function L.write_file(path, data) local f = assert(io.open(path, "wb")); f:write(data); f:close() end
function L.read_file(path) local f = assert(io.open(path, "rb")); local d = f:read("a"); f:close(); return d end
function L.shot(name) L.write_file(OUT .. name, emu.takeScreenshot()) end
function L.finish(code) logf:close(); emu.stop(code or 0) end
function L.fail(msg)
  local f = io.open(ERRFILE, "a"); f:write(tostring(msg) .. "\n"); f:close()
  emu.stop(2)
end
-- Mesen swallows Lua errors and idles until timeout: wrap every callback so errors stop the run with exit 2.
function L.safe(fn) return function(...) local ok, e = pcall(fn, ...); if not ok then L.fail(e) end end end
-- LoROM CPU address -> file offset (memory callbacks report CPU addresses). HiROM: a & 0x3FFFFF.
function L.rom_off(a) return ((a & 0x7F0000) >> 1) | (a & 0x7FFF) end
function L.on_exec(lo, hi, fn) return emu.addMemoryCallback(L.safe(fn), emu.callbackType.exec, lo, hi, snes, cpuMem) end
function L.on_write(lo, hi, fn) return emu.addMemoryCallback(L.safe(fn), emu.callbackType.write, lo, hi, snes, cpuMem) end

-- Savestates only work inside an exec callback: queue jobs, run them on the next instruction.
local jobs, execId = {}, nil
local function service()
  local job = table.remove(jobs, 1)
  if not job then return end
  if job.op == "save" then L.write_file(job.path, emu.createSavestate())
  else emu.loadSavestate(L.read_file(job.path)) end
  if #jobs == 0 then
    emu.removeMemoryCallback(execId, emu.callbackType.exec, 0, 0xFFFFFF, snes, cpuMem)
    execId = nil
  end
  if job.done then job.done() end
end
local function schedule(job)
  jobs[#jobs + 1] = job
  if not execId then execId = L.on_exec(0, 0xFFFFFF, service) end
end
function L.save_state(path, done) schedule({ op = "save", path = path, done = done }) end
function L.load_state(path, done) schedule({ op = "load", path = path, done = done }) end

-- Input queue: {buttons, frames}. spec "-" (nothing) or "a+start+up".
local queue = {}
function L.press(spec, frames)
  local b = {}
  if spec ~= "-" then for name in spec:gmatch("[^+]+") do b[name] = true end end
  queue[#queue + 1] = { buttons = b, frames = frames }
end
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
emu.addEventCallback(L.safe(function()
  local q = queue[1]
  if q then emu.setInput(q.buttons, 0)
  elseif (MASH or 0) > 0 and L.frame % MASH < 6 then emu.setInput({ [MASH_KEY or "a"] = true }, 0) end
end), emu.eventType.inputPolled)

local frameFns = {}
function L.on_frame(fn) frameFns[#frameFns + 1] = fn end
emu.addEventCallback(L.safe(function()
  L.frame = L.frame + 1
  local q = queue[1]
  if q then q.frames = q.frames - 1; if q.frames <= 0 then table.remove(queue, 1) end end
  for _, fn in ipairs(frameFns) do fn(L.frame) end
end), emu.eventType.endFrame)

-- Driver: optional state load, play ROUTE, screenshots, stop at FRAMES (or when the route ends), optional state save.
local shotset = {}
for _, f in ipairs(SHOTS or {}) do shotset[f] = true end
local function begin()
  if ROUTE then L.load_route(ROUTE) end
  local start, ending = L.frame, false
  L.on_frame(function(f)
    local n = f - start
    if ((SHOT_EVERY or 0) > 0 and n % SHOT_EVERY == 0) or shotset[n] then L.shot(string.format("f%06d.png", n)) end
    local stop = FRAMES and n >= FRAMES or (not FRAMES and L.route_done())
    if stop and not ending then
      ending = true
      L.shot("final.png")
      L.log("final frame " .. n)
      if STATE_OUT then L.save_state(STATE_OUT, function() L.finish(0) end) else L.finish(0) end
    end
  end)
end
if STATE_IN then L.load_state(STATE_IN, begin) else begin() end
