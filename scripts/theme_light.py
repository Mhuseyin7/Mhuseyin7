#!/usr/bin/env python3
"""
Dark -> light palette mapping for the profile SVGs.

GitHub switches <picture> sources by its own theme setting, so every dark SVG
gets a "-light" twin produced by remapping the palette hex values. The mapping
runs in a single regex pass (no chained replacements), so a colour that is both
a source and a target never gets flipped twice.

CLI:  python3 scripts/theme_light.py assets/header.svg assets/now.svg ...
"""
import re
import sys
from pathlib import Path

DARK_TO_LIGHT = {
    "#0f172a": "#f8fafc",  # panel background
    "#1e293b": "#eef2f7",  # title bars, tiles
    "#334155": "#cbd5e1",  # hairlines, borders
    "#475569": "#94a3b8",  # window dots
    "#4ade80": "#16a34a",  # status green
    "#60a5fa": "#2563eb",  # accent
    "#93c5fd": "#1d4ed8",  # bright accent (shimmer, glow)
    "#94a3b8": "#64748b",  # meta text
    "#cbd5e1": "#475569",  # secondary text
    "#f8fafc": "#0f172a",  # primary text
}

_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def to_light(svg_text):
    return _HEX.sub(lambda m: DARK_TO_LIGHT.get(m.group(0).lower(), m.group(0)), svg_text)


def light_name(name):
    stem, dot, ext = name.rpartition(".")
    return f"{stem}-light{dot}{ext}"


def main(paths):
    for arg in paths:
        src = Path(arg)
        if src.stem.endswith("-light"):
            continue
        dst = src.with_name(light_name(src.name))
        dst.write_text(to_light(src.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
        print(f"[OK] {dst}")


if __name__ == "__main__":
    main(sys.argv[1:])
