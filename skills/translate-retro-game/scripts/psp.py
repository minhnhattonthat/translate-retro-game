"""PSP QA driver for emu.py: boots a PSP .iso/.cso in PPSSPPHeadless (no window), plays a scripted route over PPSSPP's
WebSocket debugger API (`--debugger PORT`), takes screenshots and exits with a real code.

    python psp.py GAME.iso --out DIR [--route FILE | --route-str "600 -;3 cross;120 -"] [--frames N] [--shots 300,900]
                  [--shot-every N] [--smoke] [--state F] [--save-state F] [--sav DIR] [--memstick DIR]
                  [--emu PPSSPPHeadless.exe] [--emu-arg ARG].. [--timeout SEC]
(emu.py calls this for PSP images and maps --state-in/--state-out to --state/--save-state.)

Route: "FRAMES KEYS" steps separated by ';' or newlines, "#" comments; KEYS is '-' or buttons joined with '+':
cross circle square triangle start select up down left right ltrigger rtrigger. FRAMES are 60 Hz emulated frames. The CPU
runs to each press edge and shot with cpu.runUntilTime and stops there, so a route lands on the same frames every run, as
fast as the host allows. States load and save by path (game.state.load/save). Needs PPSSPPHeadless built from PPSSPP
master of 2026-10-19 or later. One install per machine (fetch_emu.py ppsspp-headless puts it in SHARED below): the
debugger listens on a port, so Windows Firewall asks once per exe path; a copy per repo would ask again in each.
In-game saves are per test: each run gets a fresh memstick in OUT/memstick (no saves, as a new console), seeded by
--sav DIR (a save folder such as PSP/SAVEDATA/NPJH50457DATA00, or a whole SAVEDATA folder). --memstick DIR keeps one
memstick across runs instead (play.py gives each session its own).
Exit: 0 ok, 2 driver/emulator error, 3 smoke failed (flat final frame), 124 timeout."""
import argparse, base64, json, os, re, shutil, socket, struct, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sheet as sheetmod  # noqa: E402  (stdlib PNG reader for the smoke check)


# ---- WebSocket client (stdlib) ----
class WS:
    def __init__(self, port, host='127.0.0.1', timeout=30):
        self.s = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(f'GET /debugger HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                       f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
        buf = b''
        while b'\r\n\r\n' not in buf: buf += self.s.recv(1)
        assert b' 101 ' in buf.split(b'\r\n')[0], buf
        self.buf = b''; self.ticket = 0; self.events = []

    def _read(self, n):
        while len(self.buf) < n:
            c = self.s.recv(1 << 20)
            if not c: raise EOFError
            self.buf += c
        r, self.buf = self.buf[:n], self.buf[n:]; return r

    def recv(self):
        data = b''
        while True:
            h = self._read(2); op, ln = h[0] & 15, h[1] & 127
            if ln == 126: ln = struct.unpack('>H', self._read(2))[0]
            elif ln == 127: ln = struct.unpack('>Q', self._read(8))[0]
            p = self._read(ln)
            if op == 9: self._send(10, p); continue
            data += p
            if h[0] & 128: break
        return json.loads(data)

    def _send(self, op, p):
        m = os.urandom(4); ln = len(p)
        h = bytes([128 | op]) + (bytes([128 | ln]) if ln < 126 else b'\xfe' + struct.pack('>H', ln) if ln < 65536 else b'\xff' + struct.pack('>Q', ln))
        self.s.sendall(h + m + bytes(b ^ m[i & 3] for i, b in enumerate(p)))

    def call(self, event, **params):
        """Send EVENT, return the reply with the same ticket (other events are kept for wait())."""
        self.ticket += 1
        self._send(1, json.dumps(dict(event=event, ticket=self.ticket, **params)).encode())
        while True:
            r = self.recv()
            if r.get('ticket') == self.ticket:
                if r['event'] == 'error': raise RuntimeError(r.get('message', r))
                return r
            if 'ticket' not in r: self.events.append(r)

    def wait(self, event):
        """Block until the unsolicited EVENT (e.g. cpu.stepping) arrives."""
        while True:
            r = self.events.pop(0) if self.events else self.recv()
            if r.get('event') == event: return r

    def mem(self, addr, size):
        return base64.b64decode(self.call('memory.read', address=addr, size=size)['base64'])


# ---- driver ----
BUTTONS = {'cross', 'circle', 'square', 'triangle', 'start', 'select', 'up', 'down', 'left', 'right', 'ltrigger', 'rtrigger'}
FRAME_US = 1e6 / 60

def parse_route(text):
    steps = []
    text = '\n'.join(l.split('#')[0] for l in text.split('\n'))   # comments first: they may contain ';'
    for ln in re.split(r'[;\n]', text):
        ln = ln.strip()
        if not ln: continue
        n, _, k = ln.partition(' '); k = k.strip() or '-'
        keys = set() if k == '-' else set(x.lower() for x in k.split('+'))
        bad = keys - BUTTONS
        if bad: sys.exit(f'unknown button(s) {bad}')
        steps.append((int(n), keys))
    return steps

def plan(steps, frames, shots):
    """[(frame, shoot?, keys held from there)] for every frame where the keys change or a shot is due, up to `frames`."""
    edges = []; acc = 0
    for n, k in steps: edges.append((acc, k)); acc += n
    stops = sorted({lo for lo, _ in edges} | shots | {acc, frames})   # acc: the route's end releases its last keys
    return [(f, f in shots, next((k for lo, k in reversed(edges) if lo <= f), set()) if f < acc else set())
            for f in stops if f <= frames]

def _selftest():
    p = plan(parse_route('10 -;6 circle;20 -'), 36, {12, 30})
    assert p == [(0, False, set()), (10, False, {'circle'}), (12, True, {'circle'}), (16, False, set()),
                 (30, True, set()), (36, False, set())], p
    assert plan([(5, {'up'})], 8, set()) == [(0, False, {'up'}), (5, False, set()), (8, False, set())]
    with tempfile.TemporaryDirectory() as t:   # seed_saves: one save folder, or a folder of them
        one = os.path.join(t, 'src', 'ULJM00001DATA00'); os.makedirs(one); open(os.path.join(one, 'PARAM.SFO'), 'w').close()
        seed_saves(os.path.join(t, 'a'), one); seed_saves(os.path.join(t, 'b'), os.path.join(t, 'src'))
        for m in 'ab': assert os.path.exists(os.path.join(t, m, 'PSP', 'SAVEDATA', 'ULJM00001DATA00', 'PARAM.SFO')), m
    print('selftest ok')

def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p

SHARED = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'translate-retro-game', 'ppsspp-headless')

def find_emu(arg):
    # one install for every repo (see the docstring: firewall), not tools/ in each
    for c in [arg, os.environ.get('PPSSPP_HEADLESS'), os.path.join(SHARED, 'PPSSPPHeadless.exe')]:
        if c and os.path.exists(c): return os.path.abspath(c)
    sys.exit(f'PPSSPPHeadless.exe not found in {SHARED}: run scripts/fetch_emu.py ppsspp-headless, or pass --emu')

def seed_saves(ms, sav):
    """Copy a save folder (has PARAM.SFO) or a folder of them into memstick MS's PSP/SAVEDATA."""
    dest = os.path.join(ms, 'PSP', 'SAVEDATA')
    if os.path.exists(os.path.join(sav, 'PARAM.SFO')): dest = os.path.join(dest, os.path.basename(os.path.normpath(sav)))
    shutil.copytree(sav, dest, dirs_exist_ok=True)

class Run:
    """One PPSSPPHeadless process, stopped at the entry point (or at the loaded state) until run_to()."""
    def __init__(self, emu, iso, out, state=None, memstick=None, extra=()):
        self.out = out; os.makedirs(out, exist_ok=True)
        self.port = free_port()
        self.ms = memstick or os.path.join(out, 'memstick')
        # --ppge (QA fork): draw the PSP system dialogs (save/load prompts) that stock headless leaves out
        cmd = [emu, f'--memstick={self.ms}', f'--debugger={self.port}', '--ppge', *extra, os.path.abspath(iso)]
        self.log = open(os.path.join(out, 'ppsspp.log'), 'w')
        self.p = subprocess.Popen(cmd, stdout=self.log, stderr=self.log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.ws = None; t0 = time.time()
        while time.time() - t0 < 30 and self.p.poll() is None:
            try: self.ws = WS(self.port, timeout=30); break
            except OSError: time.sleep(0.2)
        if not self.ws: raise RuntimeError(f'debugger port never opened (see {self.log.name})')
        if not self.ws.call('game.status')['game']: raise RuntimeError('game did not start')
        if state: self.ws.call('game.state.load', path=os.path.abspath(state), wait=True)
        self.base = self.ws.call('cpu.status')['us']   # frame 0: a loaded state carries its own clock
        self.keys = None

    def frame(self): return round((self.ws.call('cpu.status')['us'] - self.base) / FRAME_US)

    def run_to(self, f):
        """Run until frame F (from the start or the loaded state) and stop there."""
        target = self.base + round(f * FRAME_US)
        if target > self.ws.call('cpu.status')['us'] + 100:
            self.ws.call('cpu.runUntilTime', us=target)
            # an older cpu.stepping (the entry-point break) may still be queued: go by the clock, which stops up to
            # a cycle short of the target
            while self.ws.wait('cpu.stepping') and self.ws.call('cpu.status')['us'] < target - 100: pass

    def shot(self, name):
        r = self.ws.call('gpu.buffer.screenshot')
        open(os.path.join(self.out, name), 'wb').write(base64.b64decode(r['uri'].split(',')[1]))
        return os.path.join(self.out, name)

    def press(self, keys):
        if keys == self.keys: return
        self.ws.call('input.buttons.send', buttons={k: (k in keys) for k in BUTTONS}); self.keys = set(keys)

    def save_state(self, dest):
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        self.ws.call('game.state.save', path=os.path.abspath(dest), wait=True)

    def close(self):
        self.p.kill(); self.p.wait(); self.log.close()

def blank(png):
    """True when the screenshot is (nearly) one flat colour: a black or white screen that never rendered."""
    w, h, bpp, rows = sheetmod.read_png(png)
    sample = [rows[y][x * bpp:x * bpp + 3] for y in range(0, h, max(1, h // 24)) for x in range(0, w, max(1, w // 40))]
    return all(max(p[i] for p in sample) - min(p[i] for p in sample) < 6 for i in range(3))

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('iso'); ap.add_argument('--out', required=True)
    ap.add_argument('--route'); ap.add_argument('--route-str'); ap.add_argument('--frames', type=int)
    ap.add_argument('--shots', default=''); ap.add_argument('--shot-every', type=int, default=0)
    ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--sav', help='save folder (PSP/SAVEDATA/<ID>DATA00) or SAVEDATA folder copied into the memstick first')
    ap.add_argument('--memstick', help='keep the memstick in DIR across runs (default: a fresh one in OUT/memstick)')
    ap.add_argument('--save-state', help='write a PPSSPP save state to this file at the end of the route')
    ap.add_argument('--state', help='start from this PPSSPP save state')
    ap.add_argument('--emu'); ap.add_argument('--emu-arg', action='append', default=[], help='extra PPSSPPHeadless argument, e.g. --graphics=directx11')
    ap.add_argument('--timeout', type=int, default=600)
    a = ap.parse_args(argv)
    steps = parse_route(open(a.route).read() if a.route else a.route_str or '')
    frames = a.frames or sum(n for n, _ in steps) or 600
    shots = {int(x) for x in a.shots.split(',') if x}
    if a.shot_every: shots |= set(range(a.shot_every, frames + 1, a.shot_every))
    run = None; code = 0; t_start = time.time()
    try:
        emu = find_emu(a.emu)
        ms = os.path.abspath(a.memstick or os.path.join(a.out, 'memstick'))
        if not a.memstick: shutil.rmtree(ms, ignore_errors=True)   # per test: what an earlier run saved is gone
        if a.sav: seed_saves(ms, a.sav)
        run = Run(emu, a.iso, a.out, a.state, memstick=ms, extra=a.emu_arg)
        run.ws.s.settimeout(a.timeout)
        for f, shoot, keys in plan(steps, frames, shots):
            run.run_to(f)
            if shoot: run.shot(f'f{f:06d}.png')
            run.press(keys)
            if time.time() - t_start > a.timeout: code = 124; break
        if code == 0:
            fin = run.shot('final.png')
            if a.save_state: run.save_state(a.save_state)
            if a.smoke and blank(fin): code = 3
        print(f'exit {code}  shots {len([s for s in shots if s <= frames])}  final {"yes" if code != 124 else "no"}  '
              f'{time.time() - t_start:.1f}s for {frames} frames  dir {a.out}')
    except socket.timeout:
        print('timeout'); code = 124
    except Exception as e:
        print('driver error:', e); code = 2
    finally:
        if run: run.close()
    sys.exit(code)

if __name__ == '__main__':
    _selftest() if sys.argv[1:] == ['--selftest'] else main()
