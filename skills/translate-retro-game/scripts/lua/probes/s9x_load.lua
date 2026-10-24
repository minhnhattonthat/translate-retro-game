-- Run a player's Snes9x/RetroArch state in Mesen (SNES): load BASE, a Mesen state in the same game mode (battle,
-- map, menu), then overwrite WRAM, VRAM, SRAM and CPU registers with s9x_state.py dumps.
--   python s9x_state.py PLAYER.state work/p        (writes work/p.RAM .VRA .SRA + work/p.lua with the CPU regs)
--   emu.py ROM --out D --frames 900 --shot-every 30 --script probes/s9x_load.lua \
--          --var "BASE=[[C:/abs/work/states/battle.mss]]" --var "S9X=[[C:/abs/work/p]]"
-- Don't pass --state-in: this probe loads BASE itself. Not copied: PPU/DMA registers, CGRAM, OAM, APU. The game logic
-- runs true; the picture can break after a mode change (battle -> map) the base state wasn't in. Trace text instead
-- (watch.lua, or L.on_exec on the message lookup).
assert(BASE and S9X, 'set --var "BASE=[[base.mss]]" --var "S9X=[[dump prefix]]"')
dofile(S9X .. ".lua")
local function inject(path, mem)
  local d = L.read_file(path)
  for i = 1, math.min(#d, emu.getMemorySize(mem)) do emu.write(i - 1, d:byte(i), mem) end
end
L.load_state(BASE, function()
  inject(S9X .. ".RAM", emu.memType.snesWorkRam)
  inject(S9X .. ".VRA", emu.memType.snesVideoRam)
  inject(S9X .. ".SRA", emu.memType.snesSaveRam)
  local s = { ["cpu.emulationMode"] = false }
  for k, v in pairs(S9X_REGS) do s[k] = v end
  emu.setState(s)
  L.log(string.format("s9x state injected, PC %02X:%04X", S9X_REGS["cpu.k"], S9X_REGS["cpu.pc"]))
end)
