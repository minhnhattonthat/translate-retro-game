"""Claude Code PreToolUse hook for Bash and PowerShell: blocks the shell habits that broke past translation sessions.

1. `sed -i` - rewrote CRLF files as LF and mangled `\\n` / `\\xff` in replacements.
2. Shell-written source files: a heredoc, `python -c "...replace...write"`, or PowerShell Set-Content /
   [IO.File]::WriteAllText. `\\n`, `\\x00`, `\\uXXXX` arrived in .py files as real newlines, NUL bytes and raw
   characters (8 of 10 sessions; one took 7 rounds to repair). Quoting the delimiter (<<'EOF') does not help:
   it stops the shell, but Python itself turns "\\n" in a replacement string into a real newline.
3. Test output piped through tail/head in front of `&& git commit` - the pipe's exit code is tail's, so failing
   tests committed.
4. `gh release create|upload` while `qa_gate.py check` fails on work/qa/ (see release_gate).

Reading and analysis scripts (heredoc or -c) stay allowed; writing a source file goes through the file-edit tool.
Exit 2 + stderr = the call is blocked and the message is shown to the agent. Copy this file to the repo's
.claude/hooks/ and install it in .claude/settings.json (assets/settings.json has the full block):
  "hooks": {"PreToolUse": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command",
            "command": "python \\"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_bash.py\\""}]}]}
"""
import json, re, sys

SRC = r"\.(py|pyw|lua|asm|s|inc|c|h|cpp|js|ts|tbl|json|ps1|sh)\b"
WRITES = r"open\([^)]*['\"][wa]b?\+?['\"]|write_text|write_bytes|\.write\("
ESCAPES = r"\\(n|r|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|0)"
USE_EDIT = " Use the Edit/Write tool (or Write a script to the scratchpad with it and run that)."

RULES = [
    (re.compile(r"\bsed\s+(-[a-zA-Z]*i|--in-place)"),
     "sed -i is blocked here: it strips CRLF and mangles escapes." + USE_EDIT),
    (lambda c: re.search(r"<<-?\s*['\"]?\w+", c)
        and (re.search(WRITES, c) and (re.search(ESCAPES, c) or re.search(SRC + r"['\"]", c))
             or re.search(r"\bcat\s*>>?\s*\S+" + SRC + r".*<<", c, re.S)),
     "A heredoc that writes a source file or backslash escapes is blocked, quoted <<'EOF' too: escapes arrive "
     "mangled (real newlines, NUL bytes)." + USE_EDIT),
    (lambda c: re.search(r"\bpython[\w.]*\b[^|;&\n]*?\s-c\s", c)
        and re.search(r"\.replace\(", c) and re.search(WRITES, c),
     "python -c that reads, .replace()s and writes a file is blocked: the shell eats quotes and $, and Python turns "
     "\\n into real newlines." + USE_EDIT),
    (re.compile(r"(Set-Content|Add-Content|Out-File|WriteAll(Text|Lines|Bytes))\b[^;|]*?" + SRC, re.I),
     "Writing a source file from PowerShell is blocked: Set-Content/WriteAllText change the encoding and line "
     "endings." + USE_EDIT),
    (re.compile(r"\.Replace\([^)]*(\\n|`n|`r)"),
     "PowerShell .Replace() with a newline is blocked: \\n is literal there and `n misses CRLF files." + USE_EDIT),
    (re.compile(r"(pytest|unittest|test_\w+\.py|\bcheck\b)[^;|]*\|\s*(tail|head|grep|Select-Object|select)[^;&]*&&"
                r"[^;]*git\s+commit", re.I),
     "A pipe hides the test exit code, so this would commit on failing tests. Run the tests on their own, check "
     "the result, then commit."),
]


def check(cmd):
    for rule, msg in RULES:
        if (rule(cmd) if callable(rule) else rule.search(cmd)):
            return msg
    return None


def release_gate(cmd, cwd):
    """4. A GitHub release only after the visual-QA gate passes: one went public without it, and the gate then
    found two wrap bugs (a second release to fix them)."""
    if not re.search(r"\bgh\s+release\s+(create|upload)\b", cmd):
        return None
    import contextlib, io, os
    man, vdir = os.path.join(cwd, "work", "qa", "manifest.tsv"), os.path.join(cwd, "work", "qa", "verdicts")
    if not os.path.exists(man):
        return ("No visual-QA manifest (work/qa/manifest.tsv): run the QA tour and qa_gate.py before a release "
                "(SKILL.md phases 8-9). If the user wants to publish anyway, they can run the command themselves.")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    try:
        import qa_gate
    except ImportError:  # a copy of this hook outside $SKILL/scripts/hooks: no gate, never a crash
        return None
    with contextlib.redirect_stdout(io.StringIO()) as out:
        rc = qa_gate.check(man, vdir)
    if rc:
        return ("qa_gate.py check fails, so this release is blocked:\n" + "\n".join(out.getvalue().splitlines()[-6:])
                + "\nFinish visual QA first; if the user wants to publish anyway, they can run the command themselves.")
    return None


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        bad = [
            "sed -i 's/a/b/' tools/x.py",
            "python - <<'EOF'\np='a.py'; s=open(p).read().replace('x','\\n'); open(p,'w').write(s)\nEOF",
            "python - <<EOF\nfrom pathlib import Path\nPath('t.py').write_text('b\"\\x00\"')\nEOF",
            "python - <<'EOF'\nopen('tools/gen.lua','w').write('print(1)')\nEOF",
            "cat > tools/gen.py <<'EOF'\nprint(1)\nEOF",
            "python -X utf8 -c \"p='build.py'; s=open(p).read(); s=s.replace('a(','b('); open(p,'w').write(s)\"",
            ".venv/Scripts/python -X utf8 -c \"from pathlib import Path; p=Path('x.json'); "
            "p.write_text(p.read_text().replace('A','B'))\"",
            "(Get-Content tools/batches.py -Raw).Replace(\"'a': 1\",\"'a': 2\") | Set-Content tools/batches.py",
            "$c = Get-Content s.json -Raw; [IO.File]::WriteAllText(\"$PWD/script/06365.json\", $c)",
            "$s = (Get-Content a.txt -Raw).Replace(\"x`n\", \"y`n\")",
            "python -m pytest -q 2>&1 | tail -1 && git add . && git commit -m x",
            "python tools/check.py | Select-Object -Last 2 && git commit -m x",
        ]
        ok = [
            "python - <<'EOF'\nimport json\nprint(len(open('a.json').read().split('\\n')))\nEOF",
            "python -X utf8 -c \"d=open('rom/a.sfc','rb').read(); print(d.find(b'x'))\"",
            "python -c \"print('a b'.replace(' ', '_'))\"",
            "sed -n '1,20p' notes.md",
            "python -m pytest -q && git commit -m x",
            "git log --oneline | head -5",
            "cat > /tmp/route.txt <<'EOF'\n900 -\nEOF",
            "Get-Content tools/build.py | Select-Object -First 5",
            "Set-Content work/route.txt '900 -'",
        ]
        for c in bad:
            assert check(c), c
        for c in ok:
            assert not check(c), (c, check(c))
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            assert "No visual-QA manifest" in release_gate("gh release create v1.0 x.zip", d)
            assert release_gate("gh release view v1.0", d) is None
        print("selftest ok")
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
        cmd = data.get("tool_input", {}).get("command", "")
    except ValueError:
        sys.exit(0)
    msg = check(cmd) or release_gate(cmd, data.get("cwd") or ".")
    if msg:
        print(msg, file=sys.stderr)
        sys.exit(2)
