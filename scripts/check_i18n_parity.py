#!/usr/bin/env python3
"""Check that en/ky/ru i18n dictionaries have identical keys and placeholders."""
import json
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "i18n"
LANGS = ["en", "ky", "ru"]
PH = re.compile(r"\{[^{}]*\}")


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


def main():
    data = {}
    for lang in LANGS:
        with open(DIR / f"{lang}.json", encoding="utf-8") as fh:
            data[lang] = flatten(json.load(fh))
    union = set().union(*(set(d) for d in data.values()))
    errors = []
    for lang in LANGS:
        for k in sorted(union - set(data[lang])):
            errors.append(f"{lang}.json: missing key {k}")
        for k, v in sorted(data[lang].items()):
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{lang}.json: empty or non-string value at {k}")
    for k in sorted(union):
        if all(k in data[l] and isinstance(data[l][k], str) for l in LANGS):
            sets = {l: frozenset(PH.findall(data[l][k])) for l in LANGS}
            if len(set(sets.values())) > 1:
                errors.append(
                    f"placeholder mismatch at {k}: "
                    + ", ".join(f"{l}={sorted(s)}" for l, s in sets.items())
                )
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print(f"i18n parity OK ({len(union)} keys)")


if __name__ == "__main__":
    main()
