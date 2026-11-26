---
name: i18n-parallel-merge
description: Internationalize many frontend files at once by fanning the work out to parallel subagents (cheap model is fine) that each write their keys to a fragment JSON instead of the shared locale files, then deep-merge the fragments with merge_i18n.py (no overwrites, vi/en key sets checked). Use when the user asks to "bổ sung i18n", "dịch các chỗ còn viết cứng", "move hardcoded strings to locale files", or any i18n pass touching more than a handful of files, especially when splitting it across agents.
user-invocable: true
---

# Parallel i18n with fragment merge

Parallel agents editing the same `vi.json`/`en.json` lose each other's writes. Give every agent its own fragment files and merge once at the end with `merge_i18n.py` (next to this file).

## 1. Scan and scope

- Find hardcoded UI strings first, e.g. count lines with Vietnamese diacritics per `.ts/.tsx` file (skip comments, `locales/`, generated files) and note which files already call the translate hook.
- Default scope: screens operators/admins use. Skip dev tools, mock data and test harnesses unless the user asks; say what you skipped.
- Learn the project's API before briefing: hook name (`useTranslation()` → `translate("a.b")`?), whether a missing key fails `tsc` (string-path fallback or strict keys), interpolation support (if none: `"{n}"` placeholders + `.replace`), and how non-component modules get the language (e.g. a `notify.ts`-style inline map reading localStorage).

## 2. Fan out

One agent per disjoint group of files (an agent edits only the files it owns). Each brief says:

- Fragment paths: `<scratch>/i18n/<A|B|C>.vi.json` and `.en.json`, nested JSON rooted at the locale file's top level, identical key sets. Never edit the real locale files.
- One new top-level section per agent (check it doesn't exist). Adding keys inside an existing section is allowed only as new keys; never change an existing value; reuse an existing key that already says the same thing.
- Source-language text goes in VERBATIM (no rewording); write natural, concise target-language text for the domain.
- Don't translate identifiers, tag names, data from backend/PLC, console messages, comments, units.
- Helpers outside components take `translate` as a parameter; hooks only at top level.
- Modules loaded by plain-Node check scripts (no bundler) must not import JSON — use an inline per-language map there.
- Verify: `tsc`, `eslint` on owned files, fragments parse with identical flattened keys, every key used exists in the fragment or the locale file.

## 3. Merge

```
python3 ~/.claude/skills/i18n-parallel-merge/merge_i18n.py --locales frontend/src/locales --fragments <scratch>/i18n          # dry run
python3 ~/.claude/skills/i18n-parallel-merge/merge_i18n.py --locales frontend/src/locales --fragments <scratch>/i18n --write
```

It refuses to write if a fragment would overwrite a different existing value, if languages end up with different key sets, or if a value is empty. It warns when the locale file isn't in `json.dumps(indent=2, ensure_ascii=False)` format (the rewrite would reformat it; pass `--indent` to match).

## 4. After merging

- Run the project's full gate (e.g. `npm run ci`), not just `tsc`: a check script may load a module the agents changed.
- Run a missing/unused key audit (skill `frontend-i18n-cleanup`) and confirm none of the new keys are reported missing.
- Spot-check a random sample of target-language values; fix awkward ones in the locale file directly.
- Record in the changelog what was skipped on purpose (dev tools, mock data, backend-sent strings).
