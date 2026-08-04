"""Fix the user-provided fan-style nautilus SVG:
- recolor the out-of-order second segment (#f95f45 -> #FA9A74)
- compute approximate bbox, scale & translate so the fan is centered
  and proportionally balanced inside the 1062x1130 viewBox.

Outputs branding/nautilus-fan.svg
"""

import re
import xml.etree.ElementTree as ET

SRC = "branding/nautilus-fan-source.svg"
OUT = "branding/nautilus-fan.svg"
OLD_COLOR = "#f95f45"
NEW_COLOR = "#FA9A74"  # light coral between #fcb798 and #fe8965
FILL_TARGET = 0.85  # use up to 85% of viewBox dimension


def tokenize_path(d):
    return re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", d)


def path_bbox(d, steps=8):
    tokens = tokenize_path(d)
    if not tokens:
        return None
    pts = []
    i = 0
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = "M"
    while i < len(tokens):
        tok = tokens[i]
        if tok in "MmLlHhVvCcSsQqTtAaZz":
            cmd = tok
            i += 1
            continue
        if cmd in "Mm":
            x = float(tokens[i])
            y = float(tokens[i + 1])
            i += 2
            cur = (cur[0] + x, cur[1] + y) if cmd == "m" else (x, y)
            start = cur
            pts.append(cur)
            cmd = "l" if cmd == "m" else "L"
        elif cmd in "Ll":
            x = float(tokens[i])
            y = float(tokens[i + 1])
            i += 2
            cur = (cur[0] + x, cur[1] + y) if cmd == "l" else (x, y)
            pts.append(cur)
        elif cmd in "Hh":
            x = float(tokens[i])
            i += 1
            cur = (cur[0] + x if cmd == "h" else x, cur[1])
            pts.append(cur)
        elif cmd in "Vv":
            y = float(tokens[i])
            i += 1
            cur = (cur[0], cur[1] + y if cmd == "v" else y)
            pts.append(cur)
        elif cmd in "Cc":
            x1, y1 = float(tokens[i]), float(tokens[i + 1])
            x2, y2 = float(tokens[i + 2]), float(tokens[i + 3])
            x, y = float(tokens[i + 4]), float(tokens[i + 5])
            i += 6
            if cmd == "c":
                x1 += cur[0]
                y1 += cur[1]
                x2 += cur[0]
                y2 += cur[1]
                x += cur[0]
                y += cur[1]
            p0 = cur
            for k in range(1, steps + 1):
                t = k / steps
                u = 1 - t
                px = u**3 * p0[0] + 3 * u**2 * t * x1 + 3 * u * t**2 * x2 + t**3 * x
                py = u**3 * p0[1] + 3 * u**2 * t * y1 + 3 * u * t**2 * y2 + t**3 * y
                pts.append((px, py))
            cur = (x, y)
        elif cmd in "Zz":
            cur = start
            pts.append(cur)
        else:
            i += 1
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def main():
    tree = ET.parse(SRC)
    root = tree.getroot()
    ns = {"svg": "http://www.w3.org/2000/svg"}

    bboxes = []
    for path in root.findall("svg:path", ns):
        bbox = path_bbox(path.get("d", ""))
        if bbox:
            bboxes.append(bbox)

    minx = min(b[0] for b in bboxes)
    miny = min(b[1] for b in bboxes)
    maxx = max(b[2] for b in bboxes)
    maxy = max(b[3] for b in bboxes)
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    w = maxx - minx
    h = maxy - miny

    vb = root.get("viewBox").split()
    vw, vh = float(vb[2]), float(vb[3])
    scale = min(FILL_TARGET * vw / w, FILL_TARGET * vh / h)
    tx = vw / 2 - scale * cx
    ty = vh / 2 - scale * cy

    # read raw source and apply clean edits preserving default namespace
    with open(SRC, "r", encoding="utf-8") as f:
        text = f.read()

    text = text.replace(OLD_COLOR, NEW_COLOR)
    # wrap paths in a transformed group
    text = text.replace(
        'viewBox="0 0 1062 1130" width="1062" height="1130">',
        f'viewBox="0 0 1062 1130" width="1062" height="1130">\n<g transform="translate({tx:.2f}, {ty:.2f}) scale({scale:.4f})">',
    )
    text = text.replace("</svg>", "</g>\n</svg>")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"bbox: {minx:.1f},{miny:.1f} {maxx:.1f},{maxy:.1f}  size {w:.1f}x{h:.1f}")
    print(f"scale {scale:.4f}  translate {tx:.2f},{ty:.2f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
