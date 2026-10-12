-- Mesen2 (SNES) driver library. emu.py prepends globals: OUT, ERRFILE, ROUTE, FRAMES, SHOT_EVERY, SHOTS,
-- STATE_IN, STATE_OUT, STATE_EVERY, MASH, MASH_KEY. A user script (--script) is appended after the driver and may
-- use L.*.
L = { frame = 0 }
local snes, cpuMem = emu.cpuType.snes, emu.memType.snesMemory

local logf = assert(io.open(OUT .. "log.txt", "w"))
function L.log(s) logf:write(tostring(s) .. "\n"); logf:flush() end
local function outpath(p) return (p:match("^%a:") or p:match("^/")) and p or OUT .. p end
function L.write_file(path, data) local f = assert(io.open(outpath(path), "wb")); f:write(data); f:close() end
function L.read_file(path) local f = assert(io.open(path, "rb")); local d = f:read("a"); f:close(); return d end
function L.shot(name) L.write_file(OUT .. name, emu.takeScreenshot()) end
function L.finish(code) logf:flush(); emu.stop(code or 0) end  -- callbacks still fire until the stop lands
function L.fail(msg)
  local f = io.open(ERRFILE, "a"); f:write(tostring(msg) .. "\n"); f:close()
  emu.stop(2)
end
-- Mesen swallows Lua errors and idles until timeout: wrap every callback so errors stop the run with exit 2.
function L.safe(fn) return function(...) local ok, e = pcall(fn, ...); if not ok then L.fail(e) end end end
-- LoROM CPU address -> file offset (memory callbacks report CPU addresses). HiROM: a & 0x3FFFFF.
function L.rom_off(a) return ((a & 0x7F0000) >> 1) | (a & 0x7FFF) end
-- Callbacks match the CPU address actually used, and code runs in either bank mirror ($00-$3F/$80-$BF,
-- $40-$7D/$C0-$FF), so a range inside one half is also hooked at addr ^ $800000. Not for WRAM banks $7E-$7F.
local function hook(kind, lo, hi, fn)
  local cb = L.safe(fn)
  local id = emu.addMemoryCallback(cb, kind, lo, hi, snes, cpuMem)
  local bank = lo >> 16
  if lo >> 23 == hi >> 23 and (bank & 0x7F) < 0x7E then
    emu.addMemoryCallback(cb, kind, lo ~ 0x800000, hi ~ 0x800000, snes, cpuMem)
  end
  return id
end
function L.on_exec(lo, hi, fn) return hook(emu.callbackType.exec, lo, hi, fn) end
function L.on_read(lo, hi, fn) return hook(emu.callbackType.read, lo, hi, fn) end   -- fn(addr, value)
function L.on_write(lo, hi, fn) return hook(emu.callbackType.write, lo, hi, fn) end -- fn(addr, value)
function L.pc() local s = emu.getState(); return (s["cpu.k"] << 16) | s["cpu.pc"] end
local function grab(mt, n)
  local t = {}
  for a = 0, n - 1 do t[#t + 1] = string.char(emu.read(a, mt)) end
  return table.concat(t)
end
-- <prefix>.vram.bin (64 KB), .pal.bin (CGRAM 512 B), .oam.bin (544 B), .ppu.txt (PPU registers: BG mode, layer
-- tilemap/chr addresses). A relative prefix lands in --out.
function L.dump_ppu(prefix)
  prefix = prefix or "ppu"
  L.write_file(prefix .. ".vram.bin", grab(emu.memType.snesVideoRam, 0x10000))
  L.write_file(prefix .. ".pal.bin", grab(emu.memType.snesCgRam, 0x200))
  L.write_file(prefix .. ".oam.bin", grab(emu.memType.snesSpriteRam, 0x220))
  local s, keys = emu.getState(), {}
  for k, v in pairs(s) do if k:find("^ppu") then keys[#keys + 1] = k .. "=" .. tostring(v) end end
  table.sort(keys)
  L.write_file(prefix .. ".ppu.txt", table.concat(keys, "\n") .. "\n")
end
function L.dump_ram(path) L.write_file(path, grab(emu.memType.snesWorkRam, 0x20000)) end -- WRAM $7E0000-$7FFFFF

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
    if (STATE_EVERY or 0) > 0 and n > 0 and n % STATE_EVERY == 0 then L.save_state(string.format("%ss%06d.mss", OUT, n)) end
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
