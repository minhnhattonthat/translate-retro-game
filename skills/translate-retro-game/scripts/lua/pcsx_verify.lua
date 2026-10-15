-- Replay checkpoint check (used by replay.py as an emu.py --script). Global CHECKS = {{frame, name, address, hex}, ...}.
-- At each recorded frame the watched RAM bytes must equal the recording's; the first mismatch is logged as
-- "DIVERGED frame name want got" and the run exits 4 at the end (the replay left the recorded path: timing or text
-- length changed, a press landed on another page, or the build changed behavior).
local ffi = require('ffi')
local byframe, last = {}, 0
for _, c in ipairs(CHECKS or {}) do
  byframe[c[1]] = byframe[c[1]] or {}
  table.insert(byframe[c[1]], c)
  if c[1] > last then last = c[1] end
end
local diverged, checked = false, 0
L.on_frame(function(n)
  for _, c in ipairs(byframe[n] or {}) do
    local want = c[4]
    local bytes = ffi.string(PCSX.getMemPtr() + (c[3] - 0x80000000), math.floor(#want / 2))
    local got = bytes:gsub('.', function(ch) return string.format('%02x', ch:byte()) end)
    checked = checked + 1
    if got ~= want then
      diverged = true
      L.log(string.format('DIVERGED frame %d %s want %s got %s', n, c[2], want, got))
    else
      L.log(string.format('CHECK ok frame %d %s', n, c[2]))
    end
  end
  if n == last and last > 0 then
    L.log(string.format('checkpoints %d, %s', checked, diverged and 'DIVERGED' or 'all match'))
    if diverged then L.finish(4) end
  end
end)
