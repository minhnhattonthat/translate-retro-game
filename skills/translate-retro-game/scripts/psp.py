"""PSP QA driver for emu.py: boots a PSP .iso/.cso in PPSSPP (window hidden), plays a scripted route over PPSSPP's WebSocket
debugger API (`--debugger PORT`), takes screenshots and exits with a real code. Windows only (window hiding, key events).

    python psp.py GAME.iso --out DIR [--route FILE | --route-str "600 -;3 cross;120 -"] [--frames N] [--shots 300,900]
                  [--shot-every N] [--smoke] [--sound] [--state F] [--save-state F] [--fast] [--show] [--clean-saves]
                  [--emu PPSSPPWindows64.exe] [--emu-arg ARG].. [--timeout SEC]
(emu.py calls this for PSP images and maps --state-in/--state-out to --state/--save-state.)

Route: "FRAMES KEYS" steps separated by ';' or newlines, "#" comments; KEYS is '-' or buttons joined with '+':
cross circle square triangle start select up down left right ltrigger rtrigger. FRAMES are 60 Hz emulated frames, read from
the emulator's own clock, so a slow host gets the same route, just later.
Speed: real time (1 frame = 16.7 ms) unless --fast, which holds PPSSPP's Tab fast-forward (~17x) with real key events: it needs
the window in the foreground, so it grabs the keyboard for the run. A state (--state) skips the boot and menus: save one
at the scene you test with --save-state (sends F2 to the window), then every later run starts there in seconds.
The memstick lives beside the exe (tools/.../memstick); saves persist between runs, --clean-saves wipes PSP/SAVEDATA first.
Exit: 0 ok, 2 driver/emulator error, 3 smoke failed (flat final frame), 124 timeout."""
import argparse, base64, ctypes, glob, json, os, re, shutil, socket, struct, subprocess, sys, time
from ctypes import wintypes

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
        self.buf = b''; self.ticket = 0

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
        """Send EVENT, return the reply with the same ticket (other events are dropped)."""
        self.ticket += 1
        self._send(1, json.dumps(dict(event=event, ticket=self.ticket, **params)).encode())
        while True:
            r = self.recv()
            if r.get('ticket') == self.ticket:
                if r['event'] == 'error': raise RuntimeError(r.get('message', r))
                return r

    def mem(self, addr, size):
        return base64.b64decode(self.call('memory.read', address=addr, size=size)['base64'])


# ---- window control ----
u = ctypes.windll.user32 if os.name == 'nt' else None
WM_KEYDOWN, WM_KEYUP = 0x100, 0x101
SW = {'hide': 0, 'show': 5, 'min': 6, 'restore': 9, 'noact': 4}
def find(pid):
    out = []
    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(lambda h, _: (out.append(h) if _pid(h) == pid and u.GetWindow(h, 4) == 0 else None) or True)
    u.EnumWindows(cb, 0)
    return out

def _pid(h):
    p = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p)); return p.value

def title(h):
    b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, b, 256); return b.value

def main_window(pid):
    ws = [h for h in find(pid) if title(h).startswith('PPSSPP')]
    return ws[0] if ws else None

def win_show(h, how): u.ShowWindow(h, SW[how])

def key(h, vk, down=True):
    sc = u.MapVirtualKeyW(vk, 0)
    u.PostMessageW(h, WM_KEYDOWN if down else WM_KEYUP, vk, 1 | (sc << 16) | (0 if down else 0xC0000000))


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

def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p

def find_emu(arg):
    for c in [arg, os.environ.get('PPSSPP')] + glob.glob('tools/**/PPSSPPWindows64.exe', recursive=True) + glob.glob('../*/tools/**/PPSSPPWindows64.exe', recursive=True):
        if c and os.path.exists(c): return os.path.abspath(c)
    sys.exit('PPSSPPWindows64.exe not found: pass --emu or set PPSSPP (setup.md says where to get it)')

def set_sound(ms_dir, on):
    """QA runs are silent: [Sound] Enable in the memstick's ppsspp.ini (PPSSPP rewrites the file on exit, so set it every run)."""
    ini = os.path.join(ms_dir, 'PSP', 'SYSTEM', 'ppsspp.ini'); os.makedirs(os.path.dirname(ini), exist_ok=True)
    lines = open(ini, encoding='utf-8').read().splitlines() if os.path.exists(ini) else []
    want = f'Enable = {on}'; sec = None; out = []; done = False
    for ln in lines:
        if ln.startswith('['):
            if sec == '[Sound]' and not done: out.append(want); done = True
            sec = ln.strip()
        elif sec == '[Sound]' and ln.split('=')[0].strip() == 'Enable': ln = want; done = True
        out.append(ln)
    if not done:
        if sec == '[Sound]': out.append(want)
        else: out += ['[Sound]', want]
    open(ini, 'w', encoding='utf-8', newline='\n').write('\n'.join(out) + '\n')

class Run:
    def __init__(self, emu, iso, out, show=False, state=None, memstick=None, extra=(), sound=False):
        self.out = out; self.emu = emu; os.makedirs(out, exist_ok=True)
        self.port = free_port()
        ms = memstick or os.path.join(os.path.dirname(emu), 'memstick')
        set_sound(ms, sound)
        cmd = [emu, f'--memstick={ms}', f'--debugger={self.port}', f'--log={os.path.abspath(out)}/ppsspp.log']
        if state: cmd.append(f'--state={state}')
        cmd += list(extra)
        cmd.append(os.path.abspath(iso))
        self.p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None; t0 = time.time()
        while time.time() - t0 < 30:
            try: self.ws = WS(self.port, timeout=30); break
            except OSError: time.sleep(0.2)
        if not self.ws: raise RuntimeError('debugger port never opened')
        t0 = time.time()
        while time.time() - t0 < 60:   # wait for the game to be running
            if self.ws.call('game.status')['game']: break
            time.sleep(0.2)
        else: raise RuntimeError('game did not start')
        self.hwnd = None
        for _ in range(50):
            self.hwnd = main_window(self.p.pid)
            if self.hwnd: break
            time.sleep(0.1)
        if self.hwnd and not show: win_show(self.hwnd, 'hide')
        self.keys = set(); self.fast = False; self.show = show

    def us(self): return self.ws.call('cpu.status')['us']
    def frame(self): return int(self.us() / FRAME_US)

    def pause(self):
        self.ws._send(1, b'{"event":"cpu.stepping","ticket":9999}')
        while self.ws.recv().get('event') == 'cpu.stepping': break

    def resume(self):
        self.ws._send(1, b'{"event":"cpu.resume","ticket":9998}')
        for _ in range(20):
            r = self.ws.recv()
            if r.get('event') == 'cpu.resume': break

    def shot(self, name):
        self.pause()
        try: r = self.ws.call('gpu.buffer.screenshot')
        finally: self.resume()
        data = base64.b64decode(r['uri'].split(',')[1])
        open(os.path.join(self.out, name), 'wb').write(data); return os.path.join(self.out, name)

    def press(self, keys):
        if keys == self.keys: return
        self.ws.call('input.buttons.send', buttons={k: (k in keys) for k in BUTTONS}); self.keys = set(keys)

    def set_fast(self, on):
        if on == self.fast or not self.hwnd: return
        u = ctypes.windll.user32
        if on: u.ShowWindow(self.hwnd, 4); u.SetForegroundWindow(self.hwnd); time.sleep(0.3)
        u.keybd_event(9, 0x0F, 0 if on else 2, 0); self.fast = on

    def key_vk(self, vk, hold=0.15):
        """Real keyboard event to the PPSSPP window (needs focus; used for save-state hotkeys)."""
        u = ctypes.windll.user32; u.ShowWindow(self.hwnd, 9); time.sleep(0.5)
        u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)   # an Alt tap lets SetForegroundWindow through
        u.SetForegroundWindow(self.hwnd); time.sleep(0.5)
        sc = u.MapVirtualKeyW(vk, 0); u.keybd_event(vk, sc, 0, 0); time.sleep(hold); u.keybd_event(vk, sc, 2, 0); time.sleep(0.3)
        if self.hwnd and not self.show: win_show(self.hwnd, 'hide')

    def save_state(self, dest):
        d = os.path.join(os.path.dirname(self.emu), 'memstick', 'PSP', 'PPSSPP_STATE'); before = set(glob.glob(d + '/*.ppst'))
        self.key_vk(0x71); time.sleep(1.5)   # F2 = save state to the current slot
        new = [f for f in glob.glob(d + '/*.ppst') if f not in before or os.path.getmtime(f) > time.time() - 10]
        if not new: raise RuntimeError('F2 did not produce a .ppst')
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True); shutil.copyfile(max(new, key=os.path.getmtime), dest)

    def close(self):
        try: self.set_fast(False)
        except Exception: pass
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.p.pid)], capture_output=True)

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
    ap.add_argument('--smoke', action='store_true'); ap.add_argument('--fast', action='store_true'); ap.add_argument('--show', action='store_true')
    ap.add_argument('--sound', action='store_true', help='leave PPSSPP audio on (QA runs are muted by default)')
    ap.add_argument('--clean-saves', action='store_true', help='empty PSP/SAVEDATA on the memstick first (fresh-install run)')
    ap.add_argument('--save-state', help='write the PPSSPP save state (slot 1) to this file at the end of the route'); ap.add_argument('--emu'); ap.add_argument('--emu-arg', action='append', default=[], help='extra PPSSPP argument, e.g. -d for debug logging'); ap.add_argument('--state'); ap.add_argument('--timeout', type=int, default=600)
    a = ap.parse_args(argv)
    steps = parse_route(open(a.route).read() if a.route else a.route_str or '')
    total = sum(n for n, _ in steps)
    frames = a.frames or total or 600
    shots = sorted(int(x) for x in a.shots.split(',') if x)
    run = None; code = 0; t_start = time.time()
    try:
        emu = find_emu(a.emu)
        if a.clean_saves:
            sd = os.path.join(os.path.dirname(emu), 'memstick', 'PSP', 'SAVEDATA')
            for d in glob.glob(sd + '/*'): shutil.rmtree(d, ignore_errors=True)
        run = Run(emu, a.iso, a.out, a.show, a.state, extra=a.emu_arg, sound=a.sound)
        base = run.frame(); log = open(os.path.join(a.out, 'log.txt'), 'w'); si = 0; nshots = 0; last_ev = -1
        edges = []; acc = 0
        for n, k in steps: edges.append((acc, acc + n, k)); acc += n
        if a.fast: run.set_fast(True)
        while True:
            if time.time() - t_start > a.timeout: code = 124; break
            f = run.frame() - base
            keys = next((k for lo, hi, k in edges if lo <= f < hi), set())
            run.press(keys)
            while si < len(shots) and f >= shots[si]:
                run.shot(f'f{shots[si]:06d}.png'); nshots += 1; si += 1
            if a.shot_every and f // a.shot_every != last_ev and f > 0:
                last_ev = f // a.shot_every; run.shot(f'f{f:06d}.png'); nshots += 1
            if f >= frames: break
            time.sleep(0.02)
        if code == 0:
            run.press(set()); run.set_fast(False)
            if a.save_state: run.save_state(a.save_state)
            fin = run.shot('final.png'); log.write(f'final frame {run.frame() - base}\n'); log.close()
            if a.smoke and blank(fin): code = 3
        print(f'exit {code}  shots {nshots}  final {"yes" if os.path.exists(os.path.join(a.out, "final.png")) else "no"}  '
              f'{time.time() - t_start:.1f}s for {frames} frames  dir {a.out}')
    except Exception as e:
        print('driver error:', e); code = 2
    finally:
        if run: run.close()
    sys.exit(code)

if __name__ == '__main__':
    main()
