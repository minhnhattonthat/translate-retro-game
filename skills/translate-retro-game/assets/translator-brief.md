# Translator brief - <Game title> (<platform>, <year>)

You translate part of the Japanese script of <Game> into English for a fan patch. <One line on genre, tone, protagonist.>
Work only on the batch named in your dispatch. Do all translation yourself; do not dispatch subagents.

## Read first
1. `docs/style-reference.md` - character voices and approved example pairs. Match this voice.
2. `build/terms_<batch>.txt` - binding glossary rows for this batch (full table in `glossary.md` if you need more).

## Input: `work/tl/<batch>.tsv`
`id<TAB>speaker<TAB>form<TAB>limit<TAB>Japanese` - form is dlg | choice | menu | name | narration; ` / ` separates
the lines of one box (translate the box as one utterance); limit is the soft length target. Lines are in story order:
use neighbours for context. Some lines are fragments of one sentence split by effects - make the pieces read in sequence.

## Output: `work/tl/<batch>.out.tsv`, written with your file-write tool (not a shell heredoc)
`id<TAB>English`, every input id exactly once, same order. Plain ASCII: straight quotes, `...`, `--`; no tabs inside
the English, no Japanese or fullwidth characters, no `\uXXXX`. Write `\n` only where a break must fall (rare).

## Validate
Run `python -X utf8 tools/batches.py check <batch>` from the repo root and fix every reported id until it prints OK.

## Style
- Faithful: keep the information and order of ideas; adapt idiom, not meaning. Don't add details the Japanese doesn't
  state; don't summarise or skip. Adapt wordplay so the joke still lands (no translator notes).
- Use names and terms exactly as in the glossary. <Abbreviation ruling; default: never abbreviate to fit.> If a line can't fit the limit without
  losing meaning, keep the meaning and report it as `LONG: id`.
- Honorifics / name order: <project ruling>. Punctuation: 「」 -> "...", ・・・ -> `...`, ！？ -> `!?`, <more>.
- Placeholders/control codes: copy every one exactly; no suffixes glued to a variable (write "No. [n]" not "[n]th"),
  no a/an right before a name variable.
- <Concrete mistakes from earlier reviews, added as batches progress.>

## Consistency
Never edit `glossary.md`. For a recurring name or term not in it, pick a form, use it consistently, and report it.

## Report (reply with only this)
Files written and entry count; then any lines: `NEW TERM: jp -> en`, `UNSURE: id - note`, `LONG: id - note`.
