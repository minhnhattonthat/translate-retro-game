# translate-retro-game

A [Claude Code](https://claude.com/claude-code) skill for fan-translating Japanese retro games into English: SNES, GBA, NDS and PS1.

It is a playbook plus tested tools, distilled from eight finished fan translations. Its aim is a patch the player can test without acting as the agent's QA loop: the agent boots every build itself, screenshots the scenes it changed, and only hands over builds that pass.

## What's inside

- **A phased workflow**, each phase with a checkable "done when": recon → identity build (byte-identical repack) → extract (roundtrip-tested) → marker build → batch translation with subagents → insert and lint → emulator QA → release.
- **Headless emulator QA** (`emu.py`): boots a ROM, plays a scripted route of button presses (and touch on NDS), takes screenshots, makes contact sheets, saves and loads states, and exits with a real code (0 ok, 2 Lua error, 3 black-screen smoke failure, 124 timeout).

  | Platform | Emulator |
  |---|---|
  | SNES | Mesen2 |
  | GBA | mGBA |
  | NDS | DeSmuME + Lua 5.1 |
  | PS1 | PCSX-Redux |

- **ROM tools** (Python, stdlib only): leftover-Japanese scanner (`jp_left.py`, including a GBA pointer-reachability mode), BPS patch maker with re-apply verification (`bps.py`), out-of-range write checker (`romdiff.py`), table codec with control codes (`tbl.py`), contact sheets (`sheet.py`).
- **Guardrails**: a Bash hook that blocks the shell edits that kept corrupting source files (`sed -i`, heredocs with escapes, `tests | tail && git commit`), and a pre-commit hook that runs the repo's check and refuses ROM files.
- **Translation templates**: translator and reviewer briefs for subagents, a glossary template, and the policy questions to settle with you once per project (honorifics, name order, romanization, credits).
- **Platform notes** for SNES, GBA, NDS and PS1: mapping, pointers, compression, fonts, disc rebuilds, release formats.

## Install

In Claude Code:

```
/plugin marketplace add minhnhattonthat/translate-retro-game
/plugin install translate-retro-game@retro-translation
```

The skill loads on its own when you work on a ROM-hacking or game-translation repo, or ask for it by name.

Without the plugin system, copy `skills/translate-retro-game/` into `~/.claude/skills/`.

## What you need

- Python 3.10+ and git.
- **Your own ROM or disc dump** of the game. Nothing here downloads or contains ROMs or BIOS files.
- The emulator and tools for your platform. The skill's first step walks you through them; the full list with download sources is in [`skills/translate-retro-game/references/setup.md`](skills/translate-retro-game/references/setup.md).
- The emulator harness is tested on Windows. The Python tools are cross-platform.

## Notes

- Patches only: the workflow ships BPS/xdelta/IPS patches and a README with the base ROM hashes, never patched ROMs.
- The agent never publishes or uploads a release on its own.
- Releases made with it should disclose AI assistance; the release checklist includes that.

## License

MIT. See [LICENSE](LICENSE).
