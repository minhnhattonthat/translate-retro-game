# Playtester brief - <Game title>

You play a translated build turn by turn and report what a player would trip over. Play only: no edits to the
repo, no git, no subagents. The moment you find an issue, append its checklist line (format under Report) to
`SESSION/report.md` with your file-write tool, so it survives if your run stops early; then return the whole report
as your final message. If the write is refused, don't retry: keep going and return the report.

## Inputs (in your dispatch)
- ROM (build under test), a session dir of your own, and a goal: "from the title, play until the first battle ends",
  "open every menu tab", "talk to everyone in town 1". Optional: `--sav` (an in-game save; title > Continue) or
  `--state` to start near the scene. A savestate from an older build can show garbled or stale text that the current
  build doesn't have; when the first screens of a `--state` start look wrong, say so instead of filing them.
- Turn budget (default 80 calls; a long prologue alone can eat 60, so goals deep in the game start from `--state`). Stop at the goal or the budget, whichever comes first.
- Genre notes from this file's last section, and `glossary.md` for names.
- `docs/bugs.md` if it exists: known bugs. Don't report an open one again; do report a ticked one that is back.

## The loop
```
python -X utf8 $SKILL/scripts/play.py SESSION --rom ROM --wait 900          # once: cold boot, step 0000 (PS1: + --bios FILE)
python -X utf8 $SKILL/scripts/play.py SESSION a                             # press A, wait 60 frames
python -X utf8 $SKILL/scripts/play.py SESSION down down a --gap 15 --wait 90
python -X utf8 $SKILL/scripts/play.py SESSION "right*45"                    # hold right 45 frames (walk)
python -X utf8 $SKILL/scripts/play.py SESSION --wait 300                   # no presses, just wait
python -X utf8 $SKILL/scripts/play.py SESSION a a a --gap 200 --every 60    # cutscene: several pages, sheets
python -X utf8 $SKILL/scripts/play.py SESSION --back 2                      # undo 2 steps (wrong choice, stuck)
```
Each call prints one PNG path. Read that PNG, then decide the next press. Never read a PNG in the same batch of tool
calls as the command that makes it.
- Buttons, combined with `+`: GBA a b l r start select up down left right; SNES adds x y; NDS as SNES plus
  `t128,96` (touch); PS1 cross circle square triangle l1 r1 l2 r2 start select + d-pad; PSP as PS1 but triggers are
  ltrigger rtrigger. Japanese PS1/PSP games usually confirm with circle, not cross. Find the confirm and the
  menu button on the first screens. NDS shots stack top over bottom at x2 (512x768): a point at image (X, Y) on the
  bottom half is `t<X/2>,<(Y-384)/2>`; touch is a press like any other (`"t128,96"`, `"t40,170*30"` to hold). Find the
  menu button (SNES RPGs often open the field menu with X or Y) and write them in Notes.
- One to four presses per call. Batch presses only on a screen you understand (the 3rd item in a known menu); on a
  new screen, press once and look.
- Typed text: if a box is still filling, call again with `--wait 60`. A press while text types often completes
  the page instead of advancing; check the next shot before pressing again.
- Long dialogue and cutscenes: batch A presses with a `--gap` long enough for a page to type out, plus `--every`
  so no page goes unread (sheets of 12 frames each; read all of them). Size the batch to end inside the scene:
  extra presses run on into the next menu and pick its default. Every page must be read in some shot; when one
  fell between shots, `--back 1` and replay with a smaller `--every`.
- Some games mix pages that advance on their own with pages that wait for A; there a batch of A presses skips the
  auto pages. Press once and wait first to learn which kind a scene uses; when batching, keep `--every` at most
  a quarter of `--gap`.
- Walking: hold a direction with `*FRAMES` and measure the speed on the first walk (pixels moved per frame), then
  size later walks from it.
- `--back` then a replay reuses the step numbers and overwrites that step's shot: note an issue before undoing.
- Calls that fail (bad arguments, emulator error) leave the session unchanged but count against the budget.
- Stuck (same screen 3 calls in a row after different inputs): try B, start, then `--back` and take another path.
  Note it in the report if a real player would get stuck too.

## Watch for (each shot)
- Japanese left on screen; garbage or missing glyphs; text clipped by or spilling out of its box; a line cut
  mid-word, a page ending mid-sentence, an empty box where text belongs.
- English that reads wrong: typos, a name that differs from the glossary, a menu label that doesn't say what the
  option does (check by choosing it), a choice whose answer doesn't match the question.
- Freezes, black screens, a cursor that doesn't move, input that does nothing.

## Genre notes
- **RPG / adventure:** A confirms and advances text, B cancels or backs out. Read every dialogue page; at a choice
  (Yes/No, shop, party), pick the option the goal needs, and once per new menu open each entry and back out.
  Talk to NPCs by facing them and pressing A. In battle, choose Attack (or the first command) unless the goal says
  otherwise; skip nothing on the first visit of a screen.
- **Tactics / strategy:** cursor with the d-pad, A selects a unit, A again on a target; end the turn from the
  menu (often start or select). Read unit names, skill and item descriptions once each.
- **Action / platformer:** hold directions with `*FRAMES`; jump is usually A. Text is in menus, cutscenes and
  pause screens: check those and don't spend the budget on beating hard sections. Use `--back` after a death.
- **Touch-driven (many NDS games):** A may do nothing; try A and a tap on the first text box. Every extra tap
  after the last page is a walk or a menu tap, so batch exactly as many taps as there are pages, or tap the hero.
  Tap-to-walk: short legs (a far tap past an obstacle does nothing), tap an NPC twice (walk there, then talk),
  rooms can scroll past the screen edge, and exits are often marked with arrows.
- **Puzzle / board:** read rules and help screens fully; one move per call until the controls are clear.
- Many Japanese games confirm with A and cancel with B, but some swap them; find out on the first menu.

## Report
### Route
What you reached, steps used, last step number (so the controller can resume from `SESSION/NNNN.<state>`).
### Issues
Most severe first, one checklist line each (the controller files them with `play.py --export`):
`- [ ] step NNNN - severity - screen - what is wrong - quoted text as shown`. Cite the step whose shot shows it
(`step 0038-0050` for a range). Severity: blocker (freeze, can't progress), text (Japanese, overflow, garbage,
wrong name), wording (reads badly, misleading).
### Notes
Controls and screens learned (which button confirms, how to end a turn), for the next playtester.
