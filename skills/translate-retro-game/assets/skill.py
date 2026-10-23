"""Where the translate-retro-game skill lives. Repo scripts do `from skill import SKILL`; `python tools/skill.py` prints it.

Copied into a game repo's tools/ at setup. Env TRANSLATE_SKILL overrides the default (a non-plugin install).
"""
import os, sys

SKILL = os.environ.get("TRANSLATE_SKILL") or os.path.expanduser(
    "~/.claude/plugins/marketplaces/retro-translation/skills/translate-retro-game")
if not os.path.isfile(os.path.join(SKILL, "SKILL.md")):
    sys.exit(f"translate-retro-game skill not found at {SKILL}: install the plugin, or set TRANSLATE_SKILL to its folder")
SCRIPTS = os.path.join(SKILL, "scripts")

if __name__ == "__main__":
    print(SKILL.replace("\\", "/"))
