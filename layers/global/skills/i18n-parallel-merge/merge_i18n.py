"""Deep-merge i18n fragment files written by parallel agents into the real locale files.

Each agent writes ``<fragments>/<agent>.<lang>.json`` (nested JSON rooted at the locale file's top
level) instead of editing the shared locale files, so parallel agents never clobber each other.
This script merges every fragment into ``<locales>/<lang>.json``:

- refuses to overwrite an existing key with a different value (and a leaf with a section),
- checks that every language ends up with the same flattened key set,
- keeps the locale files' formatting (``indent``, ``ensure_ascii=False``, trailing newline) and
  warns if the current file isn't already in that format (the rewrite would reformat it).

Dry run by default; ``--write`` only writes when there are no problems.

Usage:
  python3 merge_i18n.py --locales frontend/src/locales --fragments /tmp/i18n [--langs vi,en] [--indent 2] [--write]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def flat(d: dict, p: str = ""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from flat(v, f"{p}{k}.")
        else:
            yield f"{p}{k}", v


def merge(dst: dict, src: dict, path: str, errors: list[str]) -> None:
    for k, v in src.items():
        if isinstance(v, dict):
            if k in dst and not isinstance(dst[k], dict):
                errors.append(f"{path}{k}: section over an existing leaf")
                continue
            merge(dst.setdefault(k, {}), v, f"{path}{k}.", errors)
        elif isinstance(dst.get(k), dict):
            errors.append(f"{path}{k}: leaf over an existing section")
        elif k in dst and dst[k] != v:
            errors.append(f"{path}{k}: exists with a different value ({dst[k]!r} != {v!r})")
        else:
            dst[k] = v


def dump(data: dict, indent: int) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--locales", required=True, type=pathlib.Path, help="dir holding <lang>.json")
    ap.add_argument("--fragments", required=True, type=pathlib.Path, help="dir holding <agent>.<lang>.json")
    ap.add_argument("--langs", help="comma list; default: every <lang>.json in --locales")
    ap.add_argument("--indent", type=int, default=2)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    langs = args.langs.split(",") if args.langs else sorted(p.stem for p in args.locales.glob("*.json"))
    errors: list[str] = []
    merged: dict[str, dict] = {}
    for lang in langs:
        path = args.locales / f"{lang}.json"
        text = path.read_text(encoding="utf-8")
        base = json.loads(text)
        if dump(base, args.indent) != text:
            print(f"warning: {path} is not in json.dumps(indent={args.indent}) format; --write will reformat it")
        frags = sorted(args.fragments.glob(f"*.{lang}.json"))
        if not frags:
            errors.append(f"no fragments for {lang} in {args.fragments}")
        for frag in frags:
            merge(base, json.loads(frag.read_text(encoding="utf-8")), f"[{frag.name}] ", errors)
        merged[lang] = base

    keysets = {lang: set(dict(flat(d))) for lang, d in merged.items()}
    ref = langs[0]
    for lang in langs[1:]:
        for k in sorted(keysets[ref] - keysets[lang]):
            errors.append(f"key in {ref} but not {lang}: {k}")
        for k in sorted(keysets[lang] - keysets[ref]):
            errors.append(f"key in {lang} but not {ref}: {k}")
    for lang, d in merged.items():
        for k, v in flat(d):
            if v in ("", None):
                errors.append(f"empty value in {lang}: {k}")

    print("\n".join(errors) if errors else "no problems")
    print(", ".join(f"{lang}: {len(keysets[lang])} keys" for lang in langs))
    if args.write:
        if errors:
            print("not written (fix the problems first)")
            return 1
        for lang, d in merged.items():
            (args.locales / f"{lang}.json").write_text(dump(d, args.indent), encoding="utf-8")
        print("written")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
