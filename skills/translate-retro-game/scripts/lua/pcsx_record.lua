-- PCSX-Redux input recorder (LuaJIT), started by record.py with -dofile. Globals set by record.py: OUT (dir with a trailing
-- slash), STATE_EVERY (frames, 0 = none), WATCH = {{name, address, size}, ...}.
-- Each vsync it reads pad 1 (what the human presses) and run-length encodes it into OUT/route.txt in the emu.py route
-- format ("FRAMES BUTTONS"), rewritten every 120 frames so a closed window loses at most 2 s. Every STATE_EVERY frames it
-- saves OUT/states/sNNNNNN.sstate and appends the watched RAM bytes to OUT/checkpoints.txt ("frame name hex" lines)
-- that replay.py checks against.
local ffi = require('ffi')
local B = PCSX.CONSTS.PAD.BUTTON
local KEYS = { { 'cross', B.CROSS }, { 'circle', B.CIRCLE }, { 'square', B.SQUARE }, { 'triangle', B.TRIANGLE },
               { 'l1', B.L1 }, { 'r1', B.R1 }, { 'l2', B.L2 }, { 'r2', B.R2 }, { 'start', B.START },
               { 'select', B.SELECT }, { 'up', B.UP }, { 'down', B.DOWN }, { 'left', B.LEFT }, { 'right', B.RIGHT } }
local pad = PCSX.SIO0.slots[1].pads[1]
local runs, cur, frame = {}, nil, 0
local ckpt = {}

local function write_route()
  local lines = {}
  for _, r in ipairs(runs) do lines[#lines + 1] = r[1] .. ' ' .. r[2] end
  if cur then lines[#lines + 1] = cur[1] .. ' ' .. cur[2] end
  local f = Support.File.open(OUT .. 'route.txt', 'TRUNCATE')
  f:write(table.concat(lines, '\n') .. '\n')
  f:close()
end

local function pressed()
  local p = {}
  for _, k in ipairs(KEYS) do
    if pad.getButton(k[2]) then p[#p + 1] = k[1] end
  end
  return #p > 0 and table.concat(p, '+') or '-'
end

RECORD_VSYNC = PCSX.Events.createEventListener('GPU::Vsync', function()  -- not VSYNC: pcsx_lib's own listener owns that
  frame = frame + 1
  local s = pressed()
  if cur and cur[2] == s then cur[1] = cur[1] + 1
  else
    if cur then runs[#runs + 1] = cur end
    cur = { 1, s }
  end
  if frame % 120 == 0 then write_route() end
  if (STATE_EVERY or 0) > 0 and frame % STATE_EVERY == 0 then
    write_route() -- the route must reach every checkpoint
    local f = Support.File.open(string.format('%sstates/s%06d.sstate', OUT, frame), 'TRUNCATE')
    f:writeMoveSlice(PCSX.createSaveState())
    f:close()
    local m = PCSX.getMemPtr()
    for _, w in ipairs(WATCH or {}) do
      local bytes = ffi.string(m + (w[2] - 0x80000000), w[3])
      ckpt[#ckpt + 1] = string.format('%d %s %s', frame, w[1],
        (bytes:gsub('.', function(c) return string.format('%02x', c:byte()) end)))
    end
    local f2 = Support.File.open(OUT .. 'checkpoints.txt', 'TRUNCATE')
    f2:write(table.concat(ckpt, '\n') .. '\n')
    f2:close()
  end
end)
