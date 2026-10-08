# Translation workflow reference

How to turn extracted Japanese into reviewed English with parallel agents (subagents where your harness has them; otherwise separate sessions given the same one-line dispatch). Distilled from six projects, the largest of which dispatched 95 translator agents. Templates live in `$SKILL/assets/`.

## Contents
- Before the first batch
- Batch design
- Translator dispatch
- Validation and merge
- Review
- Fitting text
- Glossary upkeep
- Models

## Before the first batch

1. **Settle the policy questions with the user** and write the answers at the top of `glossary.md` (template: `assets/glossary.md`):
   - honorifics and name order;
   - the romanization source;
   - credits;
   - sound-effect style;
   - target register.
2. **Pilot:** translate one short slice yourself (a prologue, ~10 scripts, one bank), insert it, boot it, and let the user approve it in-game. Turn the approved lines into `docs/style-reference.md`: a voice table per character plus paired JP/EN examples, including one corrected example. A ten-script pilot was enough to become the reference every later agent matched.
3. **Seed the glossary** from what already exists: an earlier patch's English, the game's item/skill/name tables, official localizations of the series, and the pilot.

## Batch design

- **One batch fits one Read:** about 3–4k JP characters or 100–150 entries. At 9,000 JP chars (~73 KB) per batch, agents Read each batch 2–4 times and twice hit the token cap.
- **Input format:** TSV, one entry per line: `id<TAB>speaker<TAB>form<TAB>limit<TAB>jp`.
  - `form` = dlg | choice | menu | name | narration.
  - `limit` = the soft target (e.g. `85ch` or `208px`).
  - Use ` / ` for in-box line breaks. Give the speaker as a name, not a portrait slot number.
- **Context:** include the neighbouring lines that matter: already-translated English neighbours (an earlier patch's English inline works well), or a few lead-in lines. Drop context lines that carry no English yet; in one project they were 34% of every batch and pure cost.
- **Output format:** `id<TAB>EN`, or a JSON object `{"id": "EN"}`, written with the agent's **file-write tool**, never a shell heredoc.
  - The output must be plain ASCII, with `\n` only where a break must fall.
  - Accept TSV output in the merge tool: agents often write TSV to avoid quote escaping.
- **Generate batches with a tool** (`tools/batches.py split`), never by hand. Write per-batch term lists alongside (`build/terms_<batch>.txt`, the glossary rows whose JP appears in the batch) so agents don't each read a 40 KB glossary.

## Translator dispatch

- Write a standing brief, `docs/translator-brief.md` (template: `assets/translator-brief.md`). Make the dispatch itself one line: "Read docs/translator-brief.md and follow it for batch b017."
- The brief contains:
  - the read list (style reference, term list);
  - the input/output formats;
  - the exact validation command, to be run until it prints OK;
  - the quality bar as a list of concrete past mistakes;
  - the report format (`NEW TERM: jp → en`, `UNSURE: id — note`, `CUT: id — what was dropped`).
- Agents **never edit `glossary.md`** in parallel. They report new terms and you merge them between waves.
- Give every new reviewer lesson to later batches as "notes from earlier batches" in the brief.
- **Isolation:**
  - Don't edit `tools/` while agents run, or give each agent its own git worktree.
  - Each agent writes only its own output file.
- Use a dedicated translator agent definition where your harness supports one (Claude Code: `.claude/agents/translator.md` with tools Read, Write, Bash and a set model; other agents: their custom-agent or prompt-file mechanism) rather than general agents that inherit every tool.

## Validation and merge

`tools/batches.py check <batch>` (or the merge step) must fail on:
- id set ≠ input id set (missing, extra or duplicate ids);
- control-code/placeholder multiset differing from the JP;
- non-ASCII or unencodable characters, tabs, `\uXXXX`;
- over-limit width per the box's real limit (pixels for VWF, bytes otherwise);
- glossary violations (a JP term present but its EN form missing; spellings from the "Avoid" column);
- an ordinal suffix right after a variable (`\[var[^\]]*\](st|nd|rd|th)\b`).

The merge refuses bad batches. The build/lint stays the hard gate. Lines that still overflow go to a dedicated **fit pass** (an agent given the exact check command, iterating until clean, reporting `CUT:` lines for anything dropped).

## Review

- **Reviewer agent** (template: `assets/reviewer-brief.md`): read-only. Its input is a pairs file of `>> id | JP / EN` entries with ±2 context lines.
  - It judges accuracy (quoting the JP and saying what it means), consistency, naturalness and voice.
  - Rate findings Critical / Important / Minor, with ids.
- Fix Critical and Important per batch. **Defer Minors to one polish pass** at the end; per-bank fix rounds for Minors wasted a lot of turns.
- **Whole-project sampled review** (~120–150 entries across the game) before release catches drift that per-batch review misses.
- Things reviewers missed and users caught:
  - a joke losing half its gag;
  - "1st" shown as "1th";
  - a name off by one letter ("Bran" vs "Plan");
  - awkward stock phrases ("TIPS … GET!").
- Put these on the reviewer checklist.

## Fitting text

- Measure what the player sees:
  - pixel width from the font's width table for VWF (`data/windows.json` per window: px, lines, cells);
  - bytes for fixed-width fonts.
  - Leave the edge pixel free: a 216 px box with auto-wrap needed a 208 px limit.
- Translators get a **soft** target (~85–95 chars per box). The lint is the hard gate.
- Give agents a dry-run fitter (`tools/fit.py "text" --box dialog` prints width per line), so they see the overflow before writing.
- When it still doesn't fit, use this order unless the user set a different one:
  1. engine (wider box, extra line or page, VWF, tiny font, relocation);
  2. rephrase without losing meaning;
  3. abbreviate only as a last resort, flagged to the user.
- Placeholders (`@I`, `@E`, `[name]`): no suffixes glued on, singular-safe pronouns, no a/an right before them.

## Glossary upkeep

`glossary.md`:
1. Policy and style rules first.
2. Then tables: `JP | EN | max | notes`, plus an `Avoid` column for spellings the user rejected.
3. Then "Decisions from earlier batches".

Merge `NEW TERM` reports between waves, and lint-enforce the table (above) so drift fails the check instead of relying on reviewers.

## Models

- Translators on the most capable model gave reviewer findings that were mostly Minor; there was no A/B test against cheaper models.
- A working split: translators on the strongest model, reviewers on a mid-tier one.
- Avoid the smallest models for anything that writes escapes; they mangled them twice.
- With many batches, run a 3-batch pilot with the cheaper model and review it before committing 90 agents to it.
