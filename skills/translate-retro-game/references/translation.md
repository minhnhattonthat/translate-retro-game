# Translation workflow reference

How to turn extracted Japanese into reviewed English with parallel agents (subagents where your harness has them; otherwise separate sessions given the same one-line dispatch). Distilled from six projects, the largest of which dispatched 95 translator agents. Templates live in `$SKILL/assets/`.

## Contents
- Before the first batch
- Batch design
- Translator dispatch
- Validation and merge
- Review
- Second language on a finished repo
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
4. **Terms pass before wave 1.** Scan every batch for recurring proper nouns: katakana runs, kanji compounds, 『』/「」-quoted names, and term families (tier suffixes 弱/中/強, 小/中/大, "all"/team forms). Any that appear in two or more batches and aren't in the glossary get one translation now, in the glossary, with the family rule ("S/M/L tiers: 1/2/3"). Without it, parallel batches drifted (Kujaku/Peacock, Hiranipura/Hiranipla, ~20 mismatches in nine batches) and needed sed-and-remerge rounds.
5. **Write `docs/synopsis.md` for a story game:** the plot by chapter, routes and branches, who is who, relationship changes and late reveals (a disguised character, a traitor, a twist on a name). Build it from guides, wikis and a read of the extracted script, and put it on the translator brief's read list. A translator who only sees one batch can't know that the friendly merchant turns out to be the villain, and gives the early lines the wrong tone or gives away the reveal. Guides tell you the order and who is who; the extracted script decides the wording.

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
- **Generate batches with a tool** (`tools/batches.py split`), never by hand. Write per-batch term lists alongside (`build/terms_<batch>.txt`, the glossary rows whose JP appears in the batch) so agents don't each read a 40 KB glossary. Rules every project's `batches.py` relearned:
  - skip entries with empty JP: they are not "untranslated" and get re-queued forever otherwise;
  - number batches from b001 on every run and refuse to overwrite existing batch files (a "show tail" call once created duplicate batches b032–b060);
  - match glossary terms only on whole kana/kanji runs, never as substrings (ミン inside タイミング, くも inside ぼくも);
  - keep entries that share a fragment (one string split around a number the game draws, `dup` ids) in one batch, or translate the shared pieces first: three batches used three conventions for the same fragments;
  - the encodable-character check reads the project table, not plain ASCII (♥ was a table glyph).

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
- an ordinal suffix right after a variable (`\[var[^\]]*\](st|nd|rd|th)\b`);
- when the glossary keeps honorifics: a JP honorific or title (〜さん, 〜くん, 先生, 先輩, お姉ちゃん, 兄貴) without its ruled EN form. "Ms. Maria" for マリア先生 and 先輩 as "the president" were caught by the user, 25 lines in one game.

The merge refuses bad batches. The build/lint stays the hard gate.

**No bulk rewrites of translated prose without the user's approval.** A regex or script that edits English across many lines (replacing a term, shortening every line over a limit, changing a stock phrase) needs the user to approve the rule, the set of lines it touches and a sample of before/after, first. A change that looks mechanical still changes meaning in free text: a term inside a longer word, a pun, a line that only fits because of the old wording. Lint may *flag* such lines; fixing them goes through translator or fit-pass agents line by line. Rewriting control codes, escapes or serialization doesn't count; that is not prose. Lines that still overflow go to a dedicated **fit pass** (an agent given the exact check command, iterating until clean, reporting `CUT:` lines for anything dropped).

## Review

- **Reviewer agent** (template: `assets/reviewer-brief.md`): read-only. Its input is a pairs file of `>> id | JP / EN` entries with ±2 context lines.
  - It judges accuracy (quoting the JP and saying what it means), consistency, naturalness and voice.
  - Rate findings Critical / Important / Minor, with ids.
- A subagent cannot write its report to a file: tell it to return the report as its final message. Dispatch only models the harness offers (a ruling like "use model X for reviews" is unusable if the agent tool lacks X; say which model ran).
- Fix Critical and Important per batch. **Defer Minors to one polish pass** at the end; per-bank fix rounds for Minors wasted a lot of turns.
- **Whole-project sampled review** (~120–150 entries across the game) before release catches drift that per-batch review misses.
- Things reviewers missed and users caught:
  - a joke losing half its gag;
  - "1st" shown as "1th";
  - a name off by one letter ("Bran" vs "Plan");
  - awkward stock phrases ("TIPS … GET!").
- Put these on the reviewer checklist.

## Second language on a finished repo

Cloning English into another language (Vietnamese on top of English, same engine) went smoothly except for what was copied selectively:
- **Copy the style, not just the terms.** `glossary.md`'s Style rules (register per scene, e.g. rough first person in two endings) did not reach the new glossary; only the reviewer caught it. Copy the whole file, then translate its terms.
- **Pair the new language with the old one.** The reviewer's pairs file lists JP, the existing translation and the new lines (`tools/pairs.py OUT lang`), so it can judge against the source and flag calques.
- **Author paragraphs, generate lines.** Keep the translation as `{id: [paragraph, ...]}` and let a wrap tool make the fixed-width lines (`tools/wrap.py` in the Gundam repo): terms and names from the glossary never split, and a paragraph never ends on a stub shorter than ~6 chars ("vũ / trụ."). Edit the paragraphs, not the wrapped output.
- Lint reads the glossary of the language it checks (`glossary_<lang>.md`); a JP term that is a substring of another ("ガンダムチーム" inside "Ｇガンダムチーム") needs every form the longer text uses in its row.
- The engine needs the language as a parameter (`pipeline.md` §Repo layout), or each new language touches a dozen files.

## Diacritic-heavy targets (Vietnamese and similar)

- **One table code per precomposed letter+tone.** Check the font cell height first: stacked tone marks need a taller cell than an 8 px font has, and a clipped mark (top of the line buffer) is the classic failure of a patch nobody zoomed into. If the cell can't grow, compose base + mark at draw time (`platform-snes.md` §Engine patching).
- **Capitals with marks only where the text uses them.** Scan the translation and glossary for capitalised word starts, add the missing glyphs on demand, and make the lint flag any character outside the table.
- **Two glyph budgets when the engine loads glyphs on demand:** the total set (every distinct letter in the whole script, glossary and names, against code space and ROM storage) and the per-screen set (letters that must be in VRAM at the same time, including those still on screen from the previous page or an open menu behind the box, against the VRAM slots). Lint both: the total from the script, the per-screen set per page plus whatever stays on screen. A page can fit its slots and still corrupt the previous page's letters when slots are reused before that page is gone. With fixed one-glyph-per-code slots the two budgets are the same.
- **Fold the space into punctuation** (`, ` `. ` `! ` `... ` as single codes) to save a code and a width entry per use; the encoder must take the longest match.
- **Torture line for the width gate:** include the tallest stack (`Ấ`, `ẳ`, `ỗ`, `Ộ`, `Ự`) on the first and last line of every window type, menus and battle text included, and read a zoomed shot.
- Keep the original line as a comment or `jp` field beside each translation. Human-written scripts still carry control-code typos (`num <$02>` for `<num><$02>`), so the control-code check is not optional.

## Fitting text

- Limits come from the width gate (`pipeline.md` §Width gate), measured in this game before the first dispatch.
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
