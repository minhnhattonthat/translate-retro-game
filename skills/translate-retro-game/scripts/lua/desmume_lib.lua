-- DeSmuME (NDS) driver library, Lua 5.1 (lua51.dll beside the exe). emu.py prepends globals: OUT, ERRFILE, ROUTE,
-- FRAMES, SHOT_EVERY, SHOTS, MASH, MASH_KEY, STATE_EVERY and either STATE_IN/STATE_OUT (paths; QA fork) or
-- STATE_IN_SLOT/STATE_OUT_SLOT (stock). The fork runs this file via --lua; stock DeSmuME loads it as
-- <out>/<rom name>.lua through its "auto-load Lua with ROM" setting. A user script (--script) is appended after the
-- driver and may use L.*. Shots are both screens stacked (256x384): PNG on the fork, .gd on stock (emu.py converts).
L = { frame = 0 }
local fork = gui.savepng ~= nil

local logf = assert(io.open(OUT .. "log.txt", "w"))
function L.log(s) logf:write(tostring(s) .. "\n"); logf:flush() end
function L.shot(name)
  if fork then gui.savepng(OUT .. name); return end
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
-- Exec hooks fire under JIT on the QA fork; stock DeSmuME needs --debugger (interpreter) for them.
function L.on_exec(addr, fn) memory.registerexec(addr, L.safe(fn)) end
-- CPU and DMA accesses both fire. fn(addr, size); read the value with memory.readbyte etc.
function L.on_read(lo, hi, fn) memory.registerread(lo, hi - lo + 1, L.safe(fn)) end
function L.on_write(lo, hi, fn) memory.registerwrite(lo, hi - lo + 1, L.safe(fn)) end
function L.pc() return memory.getregister("arm9.r15") end
local function outpath(p) return (p:match("^%a:") or p:match("^/")) and p or OUT .. p end
local function dump(f, a, n)  -- n bytes from address a, little-endian dwords
  local buf = {}
  for p = a, a + n - 1, 4 do
    local v = memory.readdword(p)
    buf[#buf + 1] = string.char(v % 256, math.floor(v / 256) % 256, math.floor(v / 65536) % 256,
                                math.floor(v / 16777216) % 256)
    if #buf == 4096 then f:write(table.concat(buf)); buf = {} end
  end
  f:write(table.concat(buf))
end
local function dump_to(path, regions)
  local f = assert(io.open(outpath(path), "wb"))
  for _, r in ipairs(regions) do dump(f, r[1], r[2]) end
  f:close()
end
-- <prefix>.vram.bin = engine-mapped VRAM, 1 MB: BG-A 0x06000000 (512 KB) at file 0, BG-B 0x06200000 (128 KB) at
-- 0x80000, OBJ-A 0x06400000 (256 KB) at 0xA0000, OBJ-B 0x06600000 (128 KB) at 0xE0000. .pal.bin 2 KB (A: BG, OBJ;
-- B: BG, OBJ), .oam.bin 2 KB (A, B), .io.bin DISPCNT/BGxCNT/scroll for A (0x04000000) then B (0x04001000), 0x60
-- each. Extended palettes are not included. A relative prefix lands in --out.
function L.dump_ppu(prefix)
  prefix = prefix or "ppu"
  dump_to(prefix .. ".vram.bin", { { 0x06000000, 0x80000 }, { 0x06200000, 0x20000 }, { 0x06400000, 0x40000 },
                                   { 0x06600000, 0x20000 } })
  dump_to(prefix .. ".pal.bin", { { 0x05000000, 0x800 } })
  dump_to(prefix .. ".oam.bin", { { 0x07000000, 0x800 } })
  dump_to(prefix .. ".io.bin", { { 0x04000000, 0x60 }, { 0x04001000, 0x60 } })
end
function L.dump_ram(path) dump_to(path, { { 0x02000000, 0x400000 } }) end -- main RAM, 4 MB
if fork then  -- savestates by file path, at a frame boundary (call from L.on_frame)
  function L.save_state(path) savestate.save(outpath(path)) end
  function L.load_state(path) savestate.load(outpath(path)) end
end

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

local loaded = not (STATE_IN_SLOT or STATE_IN)
emu.registerafter(L.safe(function()
  if not loaded then loaded = true; savestate.load(STATE_IN or STATE_IN_SLOT); return end  -- at a frame boundary
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
  if (STATE_EVERY or 0) > 0 and n % STATE_EVERY == 0 then savestate.save(string.format("%ss%06d.dst", OUT, n)) end
  for _, fn in ipairs(frameFns) do fn(n) end
  local stop = FRAMES and n >= FRAMES or (not FRAMES and L.route_done())
  if stop and not ending then
    ending = true
    L.shot("final.png")
    L.log("final frame " .. n)
    if STATE_OUT or STATE_OUT_SLOT then savestate.save(STATE_OUT or STATE_OUT_SLOT) end
    L.finish(0)
  end
end))
