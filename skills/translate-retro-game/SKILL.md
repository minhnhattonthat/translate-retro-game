---
name: translate-retro-game
description: Playbook and tested tools for fan-translating Japanese retro games (SNES, GBA, NDS, PS1, PSP) into English. Covers tool setup, ROM recon, text extraction and insertion, fonts and VWF, text drawn as graphics, batch translation with parallel agents, headless emulator QA (Mesen2, mGBA, DeSmuME, PCSX-Redux, PPSSPP), leftover-Japanese scans and BPS/xdelta releases. Use it for any work in a ROM-hacking or game-translation repo, including starting a new game, translating script batches, fixing overflowing, garbled or untranslated text, testing a build in an emulator and packaging a patch, even when the user doesn't name the skill.
---

# Translate a retro game

The goal is an English patch that the user can playtest without acting as your QA loop. Past translation projects lost most of their time in three ways:
- the user relayed emulator logs and screenshots by hand;
- shell edits mangled source code;
- tests that never actually gated a commit.

This skill closes all three gaps. `$SKILL` below means the directory containing this SKILL.md. Resolve it once; in files you write into a repo (AGENTS.md/CLAUDE.md, settings, scripts), write the resolved absolute path, because `$SKILL` is not a real variable.

## Ground rules (every phase)

- **Use your file-edit tool for source files** (Edit/Write in Claude Code, apply_patch or the editor tool elsewhere). A heredoc, `sed -i` or a Python `.replace()` script turns `\n`, `\x00`, `\xff` and `\uXXXX` into real newlines, NUL bytes and raw characters, and `sed -i` strips CRLF. This broke code in most past sessions. For a throwaway analysis script, write it to a temp file with the same tool and run it.
- **`python -X utf8`** for anything that prints Japanese (Windows consoles default to cp1252). `-I` ignores `PYTHONUTF8`, so pass `-X utf8` explicitly. On Windows, `python3` may resolve to the Microsoft Store alias; use whichever interpreter `--version` confirms.
- **The test's exit code gates the commit.** Run tests on their own and read the result before committing. `pytest | tail && git commit` commits even when tests fail, because the pipe returns tail's exit code.
- **Boot it yourself before the user plays it.** Every build you hand over must pass `emu.py --smoke`. Black-screen boots reached users repeatedly when nobody booted the build first.
- **Cold boot after code, font or graphics changes.** Savestates carry the old code and VRAM, so they hide both fixes and bugs.
- **Close the emulator before building.** Some emulators (DuckStation, for one) keep the output image locked.
- **Promote any helper you use twice** into the repo's `tools/` and commit it. Temp and scratch dirs die with the session; whole emulator harnesses were lost this way.
- **Freeze tools while translator agents run.** Editing the wrap code mid-run broke three agents.
- **Wait on long runs by notification.** Start emulator tours and agent batches as background tasks where your harness has them, and act on the completion notice; a sleep-and-poll loop burns context.
- **Never push, publish or upload a release without the user's say-so.**

## Translation defaults (confirm with the user, then record in `glossary.md`)

These are what earlier users settled on. Offer them as defaults instead of guessing, and ask once per project:
- **Full names and terms, no abbreviations.** When text doesn't fit, prefer engine work over cutting meaning: a wider box, VWF, a tiny font, relocation, extra pages. Abbreviate only as a flagged last resort.
- **Names match `glossary.md` exactly.** Near-miss spellings ("Bran" for "Plan") are the most common thing users catch.
- **No suffix glued onto a variable.** "1st" came out as "1th". Rephrase instead, e.g. "Contest No. 1".
- **Jokes and wordplay keep their punch**, even if the literal meaning shifts.
- **Release zip = patch + README only**, no .cue or other files the player already has.
- **Questions to ask once per project:**
  - honorifics and name order (projects have gone both ways);
  - credits in Japanese or English;
  - the romanization source for names (official, earlier patch, Hepburn);
  - whether specs and plans need approval or are pre-approved (pre-approved means keep going through checkpoints, reporting at the end);
  - text drawn as graphics (titles, menus, banners) is in scope by default; ask which, if any, to leave Japanese;
  - saves, memory cards or savestates the user already has: they reach late scenes that routes take hours to reach.

## Step 0: Set up the repo (once; skip if AGENTS.md or CLAUDE.md already lists build/check/smoke commands)

1. **Get the tools** for the platform: emulator, assembler, patcher, BIOS. `references/setup.md` lists what to get and where. Put third-party binaries in the repo's `tools/<name>/` (gitignored), where `emu.py` finds them.
2. **Claude Code only:** copy `$SKILL/scripts/hooks/guard_bash.py` to `.claude/hooks/guard_bash.py`, and merge `$SKILL/assets/settings.json` into `.claude/settings.json`. It sets `PYTHONUTF8` and runs a hook that blocks the three habits above. Other agents: set `PYTHONUTF8=1` in the environment and follow the ground rules; the pre-commit hook in the next step works for every agent.
3. `cp $SKILL/scripts/hooks/pre-commit .git/hooks/pre-commit` and set its `CHECK=` line to the repo's one-command check. If the repo has none, create one: a `check` target, or a `tools/check.py` that runs every test plus the text lint.
4. Check `git config user.name`. If it is unset, ask the user which identity to commit as; don't invent one.
5. Add `.gitattributes` with `* text=auto eol=lf`, then one `<pattern> binary` line per ROM/image type (`*.sfc binary`, `*.gba binary`, `*.png binary`...). Git takes one pattern per line. Skip this when the index already holds CRLF files (`git ls-files --eol | grep i/crlf`); renormalizing churns every file, so ask the user first. Add `.gitignore` for `rom/ build/ work/ dist/ release/`, `tools/` binaries and savestates.
6. Write the agent instructions file from `$SKILL/assets/AGENTS.md.template`: `AGENTS.md` (read by Codex, Cursor, Copilot, Gemini CLI and others) and/or `CLAUDE.md` (Claude Code). If you need both, keep the content in one and make the other a one-line pointer to it. 40 lines or fewer, covering: commands, paths, emulator location, project rulings, and a pointer index into `notes/` or `docs/`. Its job is to make orientation in a fresh or compacted session cost one file read instead of six.

**Done when** the smoke command boots the original ROM, a commit with a failing test is rejected, and the instructions file names the build, check, smoke and release commands.

## Phases

Each phase ends on a checkable condition. Do the phases in order. Skipping the identity build or the marker build is how the hard bugs got in.

| # | Phase | Done when | Read |
|---|---|---|---|
| 1 | **Research and recon**: earlier patches, docs, header, compression, text encoding, pointer tables, control codes, graphics text | `docs/re/` or `notes/` records encoding, pointer format, text ranges and free space; the graphics-text survey lists every tile-drawn Japanese element | `references/pipeline.md` §Recon, `references/graphics.md` §Survey, platform file |
| 2 | **Identity build**: unpack then repack with no edits | the rebuilt ROM or disc is byte-identical to the original, as a test | `references/pipeline.md` §Identity |
| 3 | **Extract** to the repo's text format | roundtrip test: re-encoding every extracted string gives the original bytes, and text ranges are fully covered | `references/pipeline.md` §Extract, `scripts/tbl.py` |
| 4 | **Engine spike and marker build**: font/VWF decision, every line replaced by `[id] marker text` | the marker ROM boots, every text box shows its id, non-text "strings" are found and excluded, and every box variant's width is measured in-game (the width gate) | `references/pipeline.md` §Marker, platform file |
| 5 | **Translate** in batches with parallel agents, only after the width gate | the batch check reports 0 errors, the glossary is updated, and the reviewer pass finds no Critical/Important issues | `references/translation.md` |
| 6 | **Insert, fit, check** | build green: width/overflow lint clean, control codes matched, `romdiff.py` shows no writes outside allowed ranges | `references/pipeline.md` §Checks |
| 7 | **QA in the emulator** | smoke passes; routes through changed scenes give contact sheets you have looked at; every graphics-text row is English in a zoomed cold-boot shot | `references/emulator-qa.md`, `references/graphics.md` |
| 8 | **Release** | `jp_left.py` on the release build reports no unintended Japanese; the patch is built, re-applied and verified; README has the base ROM hashes; zip holds patch + README | `references/pipeline.md` §Release |

Platform notes are loaded only for the platform at hand: `references/platform-snes.md`, `platform-gba.md`, `platform-nds.md`, `platform-ps1.md`, `platform-psp.md`.

When the user reports an in-game bug, reproduce it with `emu.py` first, from their savestate if they gave one, and save the shot. Then fix it, re-run the same route, and compare. Then grep for every other copy of the same text or code, because games often store a string two or three times.

## Tools (`$SKILL/scripts/`, tested; each has `--help`)

| Script | Use |
|---|---|
| `emu.py ROM --out DIR --route r.txt --shot-every 300 --smoke --sheet [--sav F] [--script x.lua]..` | Headless boot, scripted input, screenshots, contact sheet, saves, Lua hooks. Mesen .sfc, Mesen (with BIOS) or mGBA .gba, DeSmuME .nds, PCSX-Redux .cue, PPSSPP PSP .iso (window hidden, states, no Lua). Exit 0 ok / 2 Lua error / 3 smoke fail / 124 timeout |
| `lua/probes/*.lua` | `--script` probes: memory watch, RAM dump, PPU dump, SNES ROM-read and DMA logs |
| `sheet.py DIR --changed 0.02 [--from N --to M] [--crop x,y,w,h] [--zoom N] [--compare DIR2]` | One contact-sheet PNG from many frames; read it instead of individual shots |
| `jp_left.py BUILT --sjis\|--tbl jp.tbl [--slots F] [--known F] [--gba-ptrs] [--orig ORIG]` | Japanese runs still in the build; exit 1 if any. `--slots`/`--gba-ptrs` keep only text a pointer still reaches |
| `relsearch.py`, `dis65816.py`, `disasm.py` (capstone), `ramsearch.py` | Recon: relative search, SNES / ARM / MIPS disassembly + xref, cheat-style RAM search |
| `tiles.py render\|import\|map`, `vramfind.py` | Graphics text: render tiles and BG maps from dumps, re-import edited PNGs, find VRAM tiles in the ROM (`references/graphics.md`) |
| `iso9660.py`, `cpk.py`, `gim.py`, `sfo.py`, `showgim.py`, `typeset.py`, `jpscan.py` | PSP / 3D-era image work: ISO list/extract/patch, CRI CPK read/rebuild, GIM texture decode/encode, PARAM.SFO, side-by-side image sheets, English text rendering (Pillow), Japanese run scan in binaries (`references/platform-psp.md`) |
| `bps.py make ORIG BUILT OUT.bps` / `apply` / `snes-checksum` | Patch with built-in re-apply check; SNES header checksum |
| `romdiff.py ORIG NEW RANGES..` | Fails on any byte changed outside allowed ranges |
| `tbl.py` | Table codec with control codes, roundtrip-exact; import it in extract/insert code |
| `hooks/pre-commit` (any agent), `hooks/guard_bash.py` (Claude Code) | The guardrails from Step 0 |

## Ending a session

Update the instructions file (AGENTS.md/CLAUDE.md) or the notes status line: what's done, what's next, open bugs with savestate names. Commit any helper you used twice. Agent memory is per-folder and invisible to other repos, so put durable project knowledge in the repo.

If you fixed or extended anything under `$SKILL` (a script, a Lua library, a reference), tell the user in your final report, with the file and a one-line summary of the change. The copy you edited is usually per-project; unreported fixes stay stranded there and the next game hits the same bug.
