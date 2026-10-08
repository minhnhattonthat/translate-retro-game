"""Claude Code PreToolUse hook for Bash: blocks the three shell habits that broke past translation sessions.

1. `sed -i` - rewrote CRLF files as LF and mangled `\\n` / `\\xff` in replacements.
2. A heredoc that writes source code containing backslash escapes - `\\n`, `\\x00`, `\\uXXXX` arrived in .py files as
   real newlines, NUL bytes and raw characters (8 of 10 sessions; one took 7 rounds to repair).
3. Test output piped through tail/head in front of `&& git commit` - the pipe's exit code is tail's, so failing
   tests committed.

Exit 2 + stderr = the call is blocked and the message is shown to the agent. Copy this file to the repo's
.claude/hooks/ and install it in .claude/settings.json (assets/settings.json has the full block):
  "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
            "command": "python \\"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_bash.py\\""}]}]}
"""
import json, re, sys

RULES = [
    (re.compile(r"\bsed\s+(-[a-zA-Z]*i|--in-place)"),
     "sed -i is blocked here: it strips CRLF and mangles escapes. Use the Edit tool."),
    (lambda c: re.search(r"<<-?\s*['\"]?\w+", c)
        and re.search(r"open\([^)]*['\"][wa]b?['\"]|write_text|write_bytes|\.write\(", c)
        and re.search(r"\\(n|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|0)", c),
     "Heredoc that writes a file with backslash escapes is blocked: escapes arrive mangled (real newlines, NUL "
     "bytes). Write the file with the Write tool, or Write a script to the scratchpad and run it."),
    (re.compile(r"\bcat\s*>>?\s*\S+\.(py|lua|asm|s|inc|c|h|tbl)\b.*<<", re.S),
     "Writing source files with cat > file << EOF is blocked. Use the Write tool."),
    (re.compile(r"(pytest|unittest|test_\w+\.py|\bcheck\b)[^;|]*\|\s*(tail|head|grep)[^;&]*&&[^;]*git\s+commit"),
     "A pipe hides the test exit code, so this would commit on failing tests. Run the tests on their own, check "
     "the result, then commit."),
]


def check(cmd):
    for rule, msg in RULES:
        if (rule(cmd) if callable(rule) else rule.search(cmd)):
            return msg
    return None


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        bad = [
            "sed -i 's/a/b/' tools/x.py",
            "python - <<'EOF'\np='a.py'; s=open(p).read().replace('x','\\n'); open(p,'w').write(s)\nEOF",
            "python - <<EOF\nfrom pathlib import Path\nPath('t.py').write_text('b\"\\x00\"')\nEOF",
            "cat > tools/gen.py <<'EOF'\nprint(1)\nEOF",
            "python -m pytest -q 2>&1 | tail -1 && git add . && git commit -m x",
        ]
        ok = [
            "python - <<'EOF'\nimport json\nprint(len(open('a.json').read().split('\\n')))\nEOF",
            "sed -n '1,20p' notes.md",
            "python -m pytest -q && git commit -m x",
            "git log --oneline | head -5",
            "cat > /tmp/route.txt <<'EOF'\n900 -\nEOF",
        ]
        for c in bad:
            assert check(c), c
        for c in ok:
            assert not check(c), (c, check(c))
        print("selftest ok")
        sys.exit(0)
    try:
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except ValueError:
        sys.exit(0)
    msg = check(cmd)
    if msg:
        print(msg, file=sys.stderr)
        sys.exit(2)
