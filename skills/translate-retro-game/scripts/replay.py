"""Replay a record.py recording headlessly on any build, saving states/screenshots and checking the checkpoints.

    python replay.py work/rec/intro --out work/qa/intro [GAME.cue] [--state-every 1800] [--shot-every 600]
                     [--sheet] [--bios BIOS] [--emu EXE] [--no-verify]

GAME.cue defaults to the recorded ROM. The run is emu.py with the recorded route, the recorded start card (copied, so the
recording stays untouched), --state-every (states land in --out as sNNNNNN.sstate, frame numbers equal the recording's)
and pcsx_verify.lua, which compares the --watch bytes at each recorded checkpoint:
  exit 0  all checkpoints match            exit 4  a checkpoint DIVERGED (log.txt: "DIVERGED frame N name want got")
  exit 3  smoke/blank screen               other   emu.py errors
After it, run the project's checks over --out/*.sstate and --out/f*.png (leftover-text scan, overflow, patch-code
integrity, screenshot diff vs the original-language replay).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import emu  # noqa: E402


def checks(rec, meta):
    addr = {w[0]: w[1] for w in meta['watch']}
    out = []
    p = rec / 'checkpoints.txt'
    for line in p.read_text().splitlines() if p.exists() else []:
        frame, name, hexs = line.split()
        out.append([int(frame), name, addr[name], hexs])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rec')
    ap.add_argument('rom', nargs='?')
    ap.add_argument('--out', required=True)
    ap.add_argument('--state-every', type=int)
    ap.add_argument('--shot-every', type=int, default=0)
    ap.add_argument('--sheet', action='store_true')
    ap.add_argument('--bios')
    ap.add_argument('--emu')
    ap.add_argument('--no-verify', action='store_true')
    a = ap.parse_args(argv)
    rec = Path(a.rec).resolve()
    meta = json.loads((rec / 'meta.json').read_text())
    route = rec / 'route.txt'
    frames = sum(n for n, _ in emu.read_route(str(route)))
    cmd = [sys.executable, '-X', 'utf8', str(HERE / 'emu.py'), a.rom or meta['rom'], '--out', a.out, '--route', str(route),
           '--frames', str(frames), '--state-every', str(a.state_every or meta['state_every']),
           '--sav', str(rec / 'start.mcd'), '--timeout', str(max(600, frames // 20))]
    if a.shot_every:
        cmd += ['--shot-every', str(a.shot_every)]
    if a.sheet:
        cmd.append('--sheet')
    if a.bios:
        cmd += ['--bios', a.bios]
    if a.emu:
        cmd += ['--emu', a.emu]
    ck = [] if a.no_verify else checks(rec, meta)
    if ck:
        cmd += ['--script', str(HERE / 'lua' / 'pcsx_verify.lua'), '--var', 'CHECKS=' + emu.lua_value(ck)]
    print(f'replaying {frames} frames ({frames / 60:.0f} s of play), {len(ck)} checkpoints')
    r = subprocess.run(cmd)
    log = Path(a.out) / 'log.txt'
    if log.exists():
        bad = [x for x in log.read_text(errors='replace').splitlines() if x.startswith('DIVERGED') or x.startswith('checkpoints')]
        print('\n'.join(bad[:5]))
    return r.returncode


if __name__ == '__main__':
    sys.exit(main())
