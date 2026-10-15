"""Record a human playthrough (PS1, PCSX-Redux) as a route that replay.py plays back headlessly.

    python record.py GAME.cue --out work/rec/intro [--card save.mcd] [--state-every 1800]
                     [--watch map=0x800A1234:4 --watch hp=0x800B0000:2 ...] [--bios BIOS] [--emu EXE]

PCSX-Redux opens normally (real speed, sound, your keyboard or pad as configured there). Play; close the window to stop.
Output in --out:
  route.txt        the inputs, run-length encoded, in the emu.py route format (cold boot -> end; works with --route)
  start.mcd        the memory card the run started with (--card copy, or empty): replays begin from it
  states/          a savestate every --state-every frames (default 1800 = 30 s): run your checks over these
  checkpoints.txt  the --watch RAM bytes at each of those frames, which replay.py compares (resync check)
  meta.json        what replay.py needs (ROM, watches)
Record on the build you QA (translated) or the original; a replay on another build can drift when text length changes
how long a page takes (a press lands on another page): replay.py reports where it left the path.
Other emulators: Mesen / DeSmuME have their own movie recorders (.mmo / .dsm); this tool is PCSX-Redux only.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import emu  # noqa: E402


def parse_watch(s):
    name, rest = s.split('=', 1)
    addr, size = rest.split(':')
    return [name, int(addr, 0), int(size, 0)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('--out', required=True)
    ap.add_argument('--card', help='memory card (.mcd) to start from (copied, never modified)')
    ap.add_argument('--state-every', type=int, default=1800)
    ap.add_argument('--watch', action='append', default=[], help='NAME=0xADDR:SIZE RAM bytes to checkpoint')
    ap.add_argument('--bios')
    ap.add_argument('--emu')
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    (out / 'states').mkdir(parents=True, exist_ok=True)
    for old in list((out / 'states').glob('*.sstate')) + [out / 'route.txt', out / 'checkpoints.txt']:
        old.unlink(missing_ok=True)
    exe = a.emu or emu.find_emu('psx')
    bios = a.bios or os.environ.get('PSX_BIOS') or next(iter(sorted(Path('tools/bios').glob('scph*.bin'))), None)
    rom = Path(a.rom).resolve()
    start, session = out / 'start.mcd', out / 'session.mcd'
    card = a.card or os.path.join(os.path.dirname(exe), 'memcard1.mcd')  # the portable default card, so replays match
    if not os.path.exists(card):
        sys.exit('no memory card: pass --card FILE.mcd (any PS1 card image; a copy is used)')
    shutil.copy(card, start)
    shutil.copy(start, session)
    watch = [parse_watch(w) for w in a.watch]
    head = '\n'.join(f'{k} = {emu.lua_value(v)}' for k, v in
                     (('OUT', str(out).replace('\\', '/') + '/'), ('STATE_EVERY', a.state_every), ('WATCH', watch)))
    lua = out / '_record.lua'
    lua.write_text(head + '\n' + (HERE / 'lua' / 'pcsx_record.lua').read_text(encoding='utf-8') + '\n', encoding='utf-8')
    cmd = [exe, '-portable', '-noupdate', '-run', '-fastboot', '-loadiso', str(rom), '-dofile', str(lua),
           '-no-debugger', '-dynarec', '-memcard1', str(session)]
    if bios:
        cmd += ['-bios', str(Path(bios).resolve())]
    (out / 'meta.json').write_text(json.dumps({'rom': str(rom), 'watch': watch, 'state_every': a.state_every,
                                               'card': True}, indent=1))
    print('recording: play, then close the PCSX-Redux window to stop ->', out)
    subprocess.run(cmd, cwd=os.path.dirname(exe))
    route = out / 'route.txt'
    n = sum(int(line.split()[0]) for line in route.read_text().splitlines() if line.strip()) if route.exists() else 0
    print(f'recorded {n} frames ({n / 60:.0f} s), {len(list((out / "states").glob("*.sstate")))} states')
    return 0 if n else 1


if __name__ == '__main__':
    sys.exit(main())
