"""Recolor the provided nautilus SVG to brand tokens from brand-v1.6.md.

Usage: place source SVG at branding/nautilus-source.svg, then run this script.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "branding" / "nautilus-source.svg"
dst = ROOT / "branding" / "nautilus-recolored.svg"

# brand tokens
CORAL = "#E34F38"  # --brand-700 / --color-rise
CREAM = "#FDFBF7"  # --bg-warm
CORAL_400 = "#FABDB0"  # 50–60% concentration
CORAL_200 = "#FEEDE8"  # ~30% concentration

# map original swatches to brand palette
REMAP = {
    "#fdfbf7": CREAM,
    "#8d6d9e": CORAL,
    "#faeede": CORAL_200,
    "#f283a4": CORAL_400,
}

svg = src.read_text(encoding="utf-8")


# normalize fill/stroke colors (case-insensitive)
def repl(m):
    color = m.group(2).lower()
    return m.group(1) + REMAP.get(color, m.group(2)) + m.group(3)


svg = re.sub(r'(fill=["\'])(#[0-9a-fA-F]{6})(["\'])', repl, svg)
svg = re.sub(r'(stroke=["\'])(#[0-9a-fA-F]{6})(["\'])', repl, svg)

# ensure the canvas background is warm cream
svg = re.sub(
    r"<svg([^>]*)>",
    r'<svg\1 style="background-color:#FDFBF7">',
    svg,
    count=1,
)

dst.write_text(svg, encoding="utf-8")
print("saved", dst)
