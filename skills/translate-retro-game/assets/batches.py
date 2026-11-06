"""Translation batches (docs/translator-brief.md): split untranslated text, check translator output, merge it back.

    python -X utf8 tools/batches.py split [--size 3500]   work/tl/bNNN.tsv and build/terms_bNNN.txt for untranslated JP
    python -X utf8 tools/batches.py check [bNNN ...]      a batch's .out.tsv; with no batch, all shipped English (for check.py)
    python -X utf8 tools/batches.py merge bNNN ... [--overwrite]   check, then write the English into script/

Copied from the skill's assets/batches.py. Fit the ADAPTER section to this game's text format; the rest is shared.
Batch TSV: id, speaker, form, limit, JP. Output: work/tl/bNNN.out.tsv, id<TAB>English, every id once, same order.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TL = ROOT / "work/tl"
SCRIPT = ROOT / "script"
GLOSSARY = ROOT / "glossary.md"
MAX_ENTRIES = 150

# ---- ADAPTER: this game's text format ----
TOKEN = re.compile(r"\[[^\]\n]*\]")  # control codes and placeholders; must survive translation
FREE = {"[n]"}  # layout codes the English may place freely
VARIABLE = r"\[var[^\]]*\]"  # a number the game draws: "1st" comes out as "1th"
HONORIFICS = {}  # per the glossary ruling, e.g. {"先生": "-sensei", "さん": "-san"}; empty if honorifics are dropped


def docs():
    """(path, doc, entries) per script file; entries hold id, jp, en, and optionally speaker, box, max, dup."""
    for path in sorted(SCRIPT.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        yield path, doc, doc["entries"] if isinstance(doc, dict) else doc


def needs_english(entry):
    """Empty JP isn't "untranslated": it would be re-queued forever. Add this game's non-text kinds here."""
    return bool(entry.get("jp")) and not entry.get("en")


def group_of(entry):
    """Entries with the same value stay in one batch: fragments of one sentence, split around a drawn number."""
    return entry.get("dup") or entry["id"]


def limit_label(entry):
    return f"{entry['max']}" if entry.get("max") else ""


def width_problems(entry, en):
    """Over the box's real limit: replace with pixel widths from the measured font for VWF text."""
    plain = TOKEN.sub("", en).replace("\\n", "\n")
    if entry.get("max") and max(len(line) for line in plain.split("\n")) > entry["max"]:
        return [f"over the {entry['max']} limit"]
    return []


def encodable(char):
    """Read the project's table instead when it has glyphs beyond ASCII (a heart, say)."""
    return " " <= char <= "~"
# ---- end of ADAPTER ----


def kind(char):
    if "぀" <= char <= "ゟ":
        return "hiragana"
    if "゠" <= char <= "ヿ":
        return "katakana"
    if "一" <= char <= "鿿" or char == "々":
        return "kanji"
    return "other"


def has_term(jp, term):
    """term occurs as a whole kana or kanji run: ミン isn't in タイミング, くも isn't in ぼくも."""
    for m in re.finditer(re.escape(term), jp):
        a, b = m.start(), m.end()
        if (a == 0 or kind(jp[a - 1]) != kind(term[0])) and (b == len(jp) or kind(jp[b]) != kind(term[-1])):
            return True
    return False


def glossary():
    """[(JP forms, EN forms, avoid forms)] from glossary.md's | JP | EN | max | notes | Avoid | tables."""
    rows = []
    if not GLOSSARY.exists():
        return rows
    for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) >= 2 and cells[0] not in ("JP", "") and not set(cells[0]) <= set("-: "):
            avoid = [x.strip() for x in cells[4].split("/") if x.strip()] if len(cells) > 4 else []
            rows.append(([x.strip() for x in cells[0].split("/")], [x.strip() for x in cells[1].split("/")], avoid))
    return rows


def problems(entry, en, terms):
    """Every rule, on one line of English."""
    jp = entry["jp"]
    if not en.strip():
        return ["empty English"]
    out = []
    plain = TOKEN.sub("", en)
    if bad := sorted({c for c in plain if not encodable(c) and c != "\n"}):
        out.append(f"unencodable characters {bad}")
    if re.search(r"\\u[0-9a-fA-F]{4}", en) or "\t" in en:
        out.append("escape sequence or tab in the English")
    want = Counter(t for t in TOKEN.findall(jp) if t not in FREE)
    have = Counter(t for t in TOKEN.findall(en) if t not in FREE)
    if want != have:
        out.append(f"control codes differ: JP {dict(want)} EN {dict(have)}")
    if re.search(VARIABLE + r"(st|nd|rd|th)\b", en):
        out.append('ordinal suffix after a variable (write "No. [var]")')
    jp_plain = TOKEN.sub("", jp)
    for jps, ens, avoid in terms:
        if any(has_term(jp_plain, j) for j in jps) and not any(e.lower() in en.lower() for e in ens):
            out.append(f"glossary: {jps[0]} -> {ens[0]}")
        out += [f"glossary Avoid: {a}" for a in avoid if re.search(rf"\b{re.escape(a)}\b", en)]
    for jp_form, en_form in HONORIFICS.items():
        if jp_form in jp_plain and en_form.lower() not in en.lower():
            out.append(f"honorific {jp_form} needs {en_form}")
    return out + width_problems(entry, en)


def index():
    return {e["id"]: e for _, _, entries in docs() for e in entries}


def read_tsv(path):
    return [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def existing():
    return sorted(TL.glob("b[0-9][0-9][0-9].tsv"))


def split(size):
    """Numbers on from the last batch and leaves out ids already batched, so a repeat run can't duplicate work."""
    TL.mkdir(parents=True, exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)
    taken = {r[0] for p in existing() for r in read_tsv(p)}
    n = max((int(p.stem[1:]) for p in existing()), default=0)
    groups = {}
    for _, _, entries in docs():
        for e in entries:
            if needs_english(e) and e["id"] not in taken:
                groups.setdefault(group_of(e), []).append(e)
    batches, cur, chars = [], [], 0
    for group in groups.values():
        c = sum(len(TOKEN.sub("", e["jp"])) for e in group)
        if cur and (chars + c > size or len(cur) + len(group) > MAX_ENTRIES):
            batches.append(cur)
            cur, chars = [], 0
        cur += group
        chars += c
    if cur:
        batches.append(cur)
    terms = glossary()
    for batch in batches:
        n += 1
        name = f"b{n:03d}"
        path = TL / f"{name}.tsv"
        if path.exists():
            sys.exit(f"{path} already exists")
        rows = [f"{e['id']}\t{e.get('speaker', '')}\t{e.get('box', '')}\t{limit_label(e)}\t{e['jp']}" for e in batch]
        path.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
        jps = " ".join(TOKEN.sub("", e["jp"]) for e in batch)
        used = [(j, ens[0]) for jpl, ens, _ in terms for j in jpl if has_term(jps, j)]
        (ROOT / f"build/terms_{name}.txt").write_text("".join(f"{j}\t{e}\n" for j, e in used)
                                                      or "(no glossary terms in this batch)\n", encoding="utf-8", newline="\n")
    print(f"{len(batches)} new batches in {TL}, {len(taken)} ids already batched")


def check_batch(batch, entries, terms):
    want = [r[0] for r in read_tsv(TL / f"{batch}.tsv")]
    rows = [(r[0], "\t".join(r[1:])) for r in read_tsv(TL / f"{batch}.out.tsv")]
    bad = []
    if [r[0] for r in rows] != want:
        got = [r[0] for r in rows]
        dup = sorted(i for i, c in Counter(got).items() if c > 1)
        bad.append(f"ids differ: missing {sorted(set(want) - set(got))[:8]} extra {sorted(set(got) - set(want))[:8]} "
                   f"duplicate {dup[:8]} (order must match too)")
    for eid, en in rows:
        if eid in entries:
            bad += [f"{eid}: {p}: {en!r}" for p in problems(entries[eid], en, terms)]
    return bad, dict(rows)


def merge(new, overwrite):
    """Refuses to replace different English unless told to, before anything is written."""
    if not overwrite:
        for _, _, entries in docs():
            for e in entries:
                if e["id"] in new and e.get("en") and e["en"] != new[e["id"]]:
                    sys.exit(f"{e['id']} would lose {e['en']!r}: pass --overwrite if that is meant")
    changed = 0
    for path, doc, entries in docs():
        touched = False
        for e in entries:
            if e["id"] in new and e.get("en") != new[e["id"]]:
                e["en"], e["status"] = new[e["id"]], "done"
                touched = True
                changed += 1
        if touched:
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"merged: {changed} entries changed")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "split":
        return split(int(args[args.index("--size") + 1]) if "--size" in args else 3500)
    overwrite = "--overwrite" in args
    names = [a for a in args if a != "--overwrite"]
    entries, terms = index(), glossary()
    if cmd == "check" and not names:
        bad = [f"{i}: {p}: {e['en']!r}" for i, e in entries.items() if e.get("en") for p in problems(e, e["en"], terms)]
        print(f"{len(entries)} entries, {len(bad)} problems")
        print("\n".join(bad[:200]))
        return 1 if bad else 0
    if cmd not in ("check", "merge") or not names:
        sys.exit(__doc__)
    new, failed = {}, 0
    for batch in names:
        bad, rows = check_batch(batch, entries, terms)
        new.update(rows)
        failed += bool(bad)
        print(f"{batch}: " + ("OK" if not bad else f"{len(bad)} problems"))
        for line in bad:
            print("  " + line)
    if failed:
        return 1
    if cmd == "merge":
        merge(new, overwrite)
    return 0


def _selftest():
    import tempfile
    global ROOT, TL, SCRIPT, GLOSSARY
    with tempfile.TemporaryDirectory() as d:
        ROOT = Path(d)
        TL, SCRIPT, GLOSSARY = ROOT / "work/tl", ROOT / "script", ROOT / "glossary.md"
        SCRIPT.mkdir()
        GLOSSARY.write_text("| JP | EN | max | notes | Avoid |\n|---|---|---|---|---|\n| ミン | Min | | | Minn |\n", encoding="utf-8")
        script = [{"id": "a", "jp": "ミンが来た[n]", "en": "", "max": 20}, {"id": "b", "jp": "タイミング", "en": ""},
                  {"id": "c", "jp": "", "en": ""}, {"id": "d", "jp": "[var]番", "en": "", "max": 8}]
        (SCRIPT / "s.json").write_text(json.dumps(script), encoding="utf-8")
        assert main(["split"]) is None
        assert [r[0] for r in read_tsv(TL / "b001.tsv")] == ["a", "b", "d"]  # c has no JP
        assert "ミン\tMin" in (ROOT / "build/terms_b001.txt").read_text(encoding="utf-8")
        split(3500)
        assert len(existing()) == 1  # a repeat run makes no duplicate batch
        out = TL / "b001.out.tsv"
        out.write_text("a\tHe came\nb\tTiming\n", encoding="utf-8")
        assert main(["check", "b001"]) == 1  # d missing, a lacks the glossary term
        out.write_text("a\tMin came\nb\tTiming\nd\t[var]th\n", encoding="utf-8")
        assert main(["merge", "b001"]) == 1  # ordinal after a variable: nothing written
        assert index()["a"]["en"] == ""
        out.write_text("a\tMinn and Min came\nb\tTiming\nd\tNo. [var]\n", encoding="utf-8")
        assert main(["check", "b001"]) == 1  # the Avoid spelling
        out.write_text("a\tMin came\nb\tThe timing\nd\tNo. [var]\n", encoding="utf-8")
        assert main(["merge", "b001"]) == 0 and index()["b"]["en"] == "The timing"
        assert main(["check"]) == 0
        out.write_text("a\tMin arrived\nb\tThe timing\nd\tNo. [var]\n", encoding="utf-8")
        try:
            main(["merge", "b001"])
            raise AssertionError("merge replaced English")
        except SystemExit:
            pass
        assert main(["merge", "b001", "--overwrite"]) == 0 and index()["a"]["en"] == "Min arrived"
    print("selftest ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit(main(sys.argv[1:]))
