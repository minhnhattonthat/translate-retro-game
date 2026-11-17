"""Regression fixtures for the promoted script gotchas; no ROMs or emulator processes needed."""
import importlib.util
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import emu
import fetch_emu
import gim
import psp
import qa_gate
import romdiff

spec = importlib.util.spec_from_file_location("batches", SCRIPTS.parent / "assets/batches.py")
batches = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batches)


class Gotchas(unittest.TestCase):
    def test_new_manifest_rejects_old_verdict_and_preserves_unchanged_time(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "sheet.png").write_bytes(b"pixels")
            (root / "verdicts").mkdir()
            verdict = root / "verdicts/old.tsv"
            verdict.write_text("sheet\tok\n")
            os.utime(verdict, (10, 10))
            man = str(root / "manifest.tsv")
            with patch.object(qa_gate.time, "time", return_value=100):
                qa_gate.init(man, [d], "*.png")
            self.assertEqual(qa_gate.problems(man, str(verdict.parent))[1], ["sheet"])
            with patch.object(qa_gate.time, "time", return_value=200):
                qa_gate.init(man, [d], "*.png")
            self.assertEqual(qa_gate.read_manifest(man)["sheet"][2], 100)

    def test_palette_before_image_does_not_leak_between_pictures(self):
        def block(kind, payload):
            return struct.pack("<HHIII", kind, 0, 16 + len(payload), 0, 16) + payload

        def data(fmt, width):
            raw = bytearray(48)
            struct.pack_into("<HHHHHHHHH", raw, 0, 48, 0, fmt, 0, width, 1, 8, 0, 0)
            struct.pack_into("<III", raw, 24, 0, 48, 48)
            return raw

        image = block(4, data(5, 1))
        p1, p2 = block(5, data(3, 16)), block(5, data(3, 32))
        for first, second in ((image + p1, p2 + image), (p1 + image, image + p2)):
            raw = b"MIG.00.1PSP".ljust(16, b"\0") + block(2, block(3, first) + block(3, second))
            images = gim.parse(raw)
            self.assertEqual([i.pal[1] for i in images], [16, 32])

    def test_websocket_close_and_non_utf8_log(self):
        ws = psp.WS.__new__(psp.WS)
        payload = b'{"event":"log","text":"\x82\xa0"}'
        ws.buf = bytes([0x81, len(payload)]) + payload
        self.assertEqual(ws.recv()["event"], "log")
        ws.buf = b"\x88\x00"
        with self.assertRaises(EOFError):
            ws.recv()

    def test_fetch_uses_explicit_ca_bundle_and_reports_certificate_failure(self):
        import ssl
        import urllib.error
        with patch.dict(os.environ, {"SSL_CERT_FILE": "trusted.pem"}), \
                patch.object(fetch_emu.ssl, "create_default_context") as context, \
                patch.object(fetch_emu.urllib.request, "urlopen") as request:
            request.side_effect = urllib.error.URLError(ssl.SSLCertVerificationError("untrusted"))
            with self.assertRaisesRegex(SystemExit, "SSL_CERT_FILE"):
                fetch_emu.get("https://example.invalid/fixture")
            context.assert_called_once_with(cafile="trusted.pem")

    def test_mesen_saves_and_config_are_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, out = root / "source", root / "run"
            source.mkdir(); out.mkdir()
            exe = source / "Mesen.exe"
            exe.write_bytes(b"fixture")
            config = source / "settings.json"
            config.write_text('{"Preferences":{"SaveDataFolder":"shared"}}')
            private, saves = emu.mesen_run(str(exe), str(out))
            Path(saves, "game.sav").write_bytes(b"old run")
            private2, saves2 = emu.mesen_run(str(exe), str(out))
            self.assertNotEqual(saves, saves2)
            self.assertEqual(list(Path(saves2).iterdir()), [])
            self.assertEqual(json.loads(config.read_text())["Preferences"]["SaveDataFolder"], "shared")
            cfg = json.loads(Path(private2).with_name("settings.json").read_text())
            self.assertEqual(cfg["Preferences"]["SaveDataFolder"], saves2)
            self.assertEqual(Path(private).read_bytes(), b"fixture")

    def test_batches_unique_keys_partial_merge_and_wrapped_terms(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.multiple(batches, ROOT=root, TL=root / "tl", SCRIPT=root / "script", GLOSSARY=root / "glossary.md"):
                batches.SCRIPT.mkdir(); batches.TL.mkdir()
                path = batches.SCRIPT / "s.json"
                path.write_text(json.dumps([{"id": "same", "addr": 16, "jp": "猫", "en": ""},
                                            {"id": "same", "addr": 32, "jp": "犬", "en": ""}]))
                for name, key, en in (("b001", "same@16", "Cat"), ("b002", "same@32", "")):
                    (batches.TL / (name + ".tsv")).write_text(key + "\tJP\n")
                    (batches.TL / (name + ".out.tsv")).write_text(key + "\t" + en + "\n")
                self.assertEqual(batches.main(["merge", "b001", "b002"]), 1)
                self.assertEqual(batches.index()["same@16"]["en"], "Cat")
                self.assertEqual(batches.index()["same@32"]["en"], "")
        self.assertTrue(batches.has_term("マッスル / ハチエモン", "マッスルハチエモン"))
        self.assertEqual(batches.problems({"jp": "猫"}, "Big[n]Cat", [(["猫"], ["Big Cat"], [])]), [])

    def test_sector_diff_matches_byte_oracle(self):
        rng = random.Random(0)
        orig = bytes(rng.randrange(256) for _ in range(5000))
        new = bytearray(orig + b"\xff" * 10)
        for i in (0, 2351, 2352, 4704, 5009):
            new[i] ^= 1
        errs, count = romdiff.check(orig, new, [range(2351, 2353), range(5000, 5010)], [])
        self.assertEqual(count, 3)
        self.assertEqual(errs[-1], "2 differing bytes outside writes and allowed ranges")
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.bin", Path(d) / "b.bin"
            a.write_bytes(orig); b.write_bytes(new)
            result = subprocess.run([sys.executable, str(SCRIPTS / "romdiff.py"), str(a), str(b), "0-FFFF"], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_iso_no_args_prints_usage(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "iso9660.py")], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"usage:", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_driver_globals_cannot_be_overwritten(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            args = SimpleNamespace(state_in=None, rom="game.cue", route=None, route_str=None,
                                   frames=1, emu="pcsx-redux.exe", state_every=0, out=d, state_out=None,
                                   shots=None, shot_every=0, mash=0, mash_key=None, debugger=False)
            for name in ("SHOTS", "OUT", "FRAMES", "ROUTE", "L", "VSYNC"):
                args.var = [name + "={}"]
                with self.assertRaisesRegex(SystemExit, "non-driver global"):
                    emu.run(args)

    @unittest.skipUnless(os.environ.get("LUA51_DLL"), "set LUA51_DLL to run Lua callback fixtures")
    def test_lua_callbacks(self):
        import ctypes
        lua = ctypes.CDLL(os.environ["LUA51_DLL"])
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]
        common = '''
local noop = function() end
OUT = ""; ERRFILE = "errors"; FRAMES = 100
local file = {write=noop, flush=noop, close=noop}
io.open = function() return file end
os.exit = function(code) error("unexpected exit " .. code) end
'''
        cases = [
            ("desmume_lib.lua", '''
gui = {}; joypad = {}; stylus = {}
emu = {registerbefore=function(f) before=f end, registerafter=function(f) after=f end, speedmode=noop}
registered = 0
memory = {registerexec=function(a, f) registered=registered+1; callback=f end}
''', '''
local hits = 0
L.on_exec(100, function() hits=hits+1 end)
L.on_exec(100, function() hits=hits+10 end)
callback()
assert(registered == 1 and hits == 11)
'''),
            ("pcsx_lib.lua", '''
Support = {File={open=function() return file end}}
PCSX = {settings={spu={}}, CONSTS={PAD={BUTTON={}}}, SIO0={slots={{pads={{}}}}},
  Events={createEventListener=function() return {} end},
  addBreakpoint=function() return {} end, resumeEmulator=noop}
''', '''
assert(not pcall(function() L.on_exec(100, function() end) end))
DEBUGGER = true
assert(pcall(function() L.on_exec(100, function() end) end))
L.frame = 1
assert(not pcall(function() L.on_exec(100, function() end) end))
''')]
        for name, prelude, assertions in cases:
            state = lua.luaL_newstate()
            try:
                lua.luaL_openlibs(state)
                code = common + prelude + (SCRIPTS / "lua" / name).read_text() + assertions
                rc = lua.luaL_loadstring(state, code.encode()) or lua.lua_pcall(state, 0, 0, 0)
                self.assertEqual(rc, 0, lua.lua_tolstring(state, -1, None) if rc else name)
            finally:
                lua.lua_close(state)


if __name__ == "__main__":
    unittest.main()
