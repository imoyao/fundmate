"""Generate nautilus logo candidates with an n=3 Superellipse (Alive) background.

Alive philosophy (brand-v1.6.md §1.1): replace the square/circle container with
a superellipse  |x/a|^n + |y/a|^n = 1, n=3  -- a curve with no straight segment,
midway between circle and square, conveying "life in flow".

The nautilus logarithmic-spiral band (ribbon) is reused from gen_nautilus.py.
Brand tokens (§3.1): coral #E34F38, warm cream #FDFBF7, white #FFFFFF.

Outputs into branding/:
  nautilus-alive-<v>.svg / .png / -white.png   (v1..v4)
  nautilus-alive-preview.png / -preview-white.png  (multi-size clarity sheet)
"""

import math
import os
from PIL import Image, ImageDraw

VB = 100.0
CORAL = (227, 79, 56, 255)  # #E34F38 --brand-700
CREAM = (253, 251, 247, 255)  # #FDFBF7 --bg-warm
WHITE = (255, 255, 255, 255)
OUT = os.path.join(os.path.dirname(__file__), "..", "branding")
N = 3.0  # superellipse exponent (Alive)
SEMI = 46.0  # superellipse half-width (a=b), within 0..100 viewBox


# ---- nautilus spiral band (reused geometry) ------------------------------
def spiral(cx, cy, a, b, tmax, phase, n):
    pts = []
    for i in range(n + 1):
        t = tmax * i / n
        r = a * math.exp(b * t)
        ang = t + phase
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang), r))
    return pts


def band(pts, hwfn):
    m = len(pts)
    outer, inner = [], []
    for i in range(m):
        x, y, r = pts[i]
        p = pts[max(0, i - 1)]
        q = pts[min(m - 1, i + 1)]
        tx, ty = q[0] - p[0], q[1] - p[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L
        h = hwfn(r)
        outer.append((x + nx * h, y + ny * h))
        inner.append((x - nx * h, y - ny * h))
    return outer, inner


# ---- superellipse path ----------------------------------------------------
def superellipse(cx, cy, a, b, n, steps=240):
    """Parametric Lamé curve: x=a*sgn(cosθ)|cosθ|^(2/n), y=b*sgn(sinθ)|sinθ|^(2/n)."""
    pts = []
    for i in range(steps + 1):
        th = 2 * math.pi * i / steps
        c = math.cos(th)
        s = math.sin(th)
        x = a * math.copysign(abs(c) ** (2.0 / n), c)
        y = b * math.copysign(abs(s) ** (2.0 / n), s)
        pts.append((cx + x, cy + y))
    return pts


def svg_poly(poly, closed=True):
    d = "M%.2f %.2f " % poly[0]
    for x, y in poly[1:]:
        d += "L%.2f %.2f " % (x, y)
    if closed:
        d += "Z"
    return d.strip()


def make_svg(outer, inner, se_pts, style, bg):
    """bg: 'cream' | 'coral' | None ; style: 'fill' | 'stroke'."""
    s = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'fill="none" stroke="#E34F38" stroke-linejoin="round" '
        'stroke-linecap="round">'
    ]
    if bg == "cream":
        s.append('<path d="%s" fill="#FDFBF7" stroke="none"/>' % svg_poly(se_pts))
    elif bg == "coral":
        s.append('<path d="%s" fill="#E34F38" stroke="none"/>' % svg_poly(se_pts))
    else:  # outline-only container
        s.append('<path d="%s" stroke-width="3.0"/>' % svg_poly(se_pts))
    if style == "fill":
        ribbon = outer + inner[::-1]
        fill = "#FFFFFF" if bg == "coral" else "#E34F38"
        s.append('<path d="%s" fill="%s" stroke="none"/>' % (svg_poly(ribbon), fill))
    else:
        stroke = "#FFFFFF" if bg == "coral" else "#E34F38"
        s.append(
            '<path d="%s" stroke-width="2.6" stroke="%s"/>'
            % (svg_poly(outer, False), stroke)
        )
        s.append(
            '<path d="%s" stroke-width="2.6" stroke="%s"/>'
            % (svg_poly(inner, False), stroke)
        )
    s.append("</svg>")
    return "\n".join(s)


def render_pil(outer, inner, se_pts, style, bg, size, scale=8):
    H = size * scale
    img = Image.new("RGBA", (H, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    S = scale
    se_px = [(x * S, y * S) for x, y in se_pts]
    if bg == "cream":
        d.polygon(se_px, fill=CREAM)
    elif bg == "coral":
        d.polygon(se_px, fill=CORAL)
    else:
        d.line(se_px, fill=CORAL, width=max(1, int(3.0 * S)), joint="curve")
    if style == "fill":
        poly = [(x * S, y * S) for x, y in (outer + inner[::-1])]
        fill = WHITE if bg == "coral" else CORAL
        d.polygon(poly, fill=fill)
    else:
        stroke = WHITE if bg == "coral" else CORAL
        for edge in (outer, inner):
            d.line(
                [(x * S, y * S) for x, y in edge],
                fill=stroke,
                width=max(1, int(2.6 * S)),
                joint="curve",
            )
    return img.resize((size, size), Image.LANCZOS)


# ---- version definitions ----------------------------------------------
def phase_for(tmax):
    return math.pi / 4 - tmax


VERSIONS = {
    # cream superellipse bg + coral filled shell (clean, on any light bg)
    "v1": dict(
        cx=40,
        cy=40,
        a=2.4,
        b=0.16,
        turns=2.4,
        hw=lambda r: 1.6 + (r / 26.8) * 7.0,
        bg="cream",
        style="fill",
    ),
    # superellipse coral outline + coral filled shell (Alive container stroked)
    "v2": dict(
        cx=40,
        cy=40,
        a=2.4,
        b=0.16,
        turns=2.4,
        hw=lambda r: 1.6 + (r / 26.8) * 7.0,
        bg=None,
        style="fill",
    ),
    # coral superellipse bg + cream shell (inverse, for favicon / dark)
    "v3": dict(
        cx=40,
        cy=40,
        a=2.4,
        b=0.16,
        turns=2.4,
        hw=lambda r: 1.6 + (r / 26.8) * 7.0,
        bg="coral",
        style="fill",
    ),
    # cream superellipse bg + coral stroked shell (airy, lighter life feel)
    "v4": dict(
        cx=40,
        cy=40,
        a=2.4,
        b=0.16,
        turns=2.4,
        hw=lambda r: 1.6 + (r / 26.8) * 7.0,
        bg="cream",
        style="stroke",
    ),
}


def build(name, cfg):
    tmax = cfg["turns"] * 2 * math.pi
    phase = phase_for(tmax)
    pts = spiral(cfg["cx"], cfg["cy"], cfg["a"], cfg["b"], tmax, phase, 400)
    outer, inner = band(pts, cfg["hw"])
    se = superellipse(50, 50, SEMI, SEMI, N)
    svg = make_svg(outer, inner, se, cfg["style"], cfg["bg"])
    big = render_pil(outer, inner, se, cfg["style"], cfg["bg"], 512)
    white = Image.new("RGBA", (512, 512), CREAM)
    white.alpha_composite(big)
    return svg, big, white


def main():
    os.makedirs(OUT, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128]
    cols, rows = len(sizes), len(VERSIONS)
    pad = 12
    cell = 128 + pad
    prev_c = Image.new("RGBA", (cols * cell + pad, rows * cell + pad), CREAM)
    prev_w = Image.new("RGBA", (cols * cell + pad, rows * cell + pad), WHITE)
    for ri, (name, cfg) in enumerate(VERSIONS.items()):
        svg, big, white = build(name, cfg)
        with open(os.path.join(OUT, f"nautilus-alive-{name}.svg"), "w") as f:
            f.write(svg)
        big.save(os.path.join(OUT, f"nautilus-alive-{name}.png"))
        white.save(os.path.join(OUT, f"nautilus-alive-{name}-white.png"))
        for ci, sz in enumerate(sizes):
            tmax = cfg["turns"] * 2 * math.pi
            phase = phase_for(tmax)
            pts = spiral(cfg["cx"], cfg["cy"], cfg["a"], cfg["b"], tmax, phase, 400)
            outer, inner = band(pts, cfg["hw"])
            se = superellipse(50, 50, SEMI, SEMI, N)
            tile = render_pil(outer, inner, se, cfg["style"], cfg["bg"], sz)
            prev_c.alpha_composite(tile, (pad + ci * cell, pad + ri * cell))
            prev_w.alpha_composite(tile, (pad + ci * cell, pad + ri * cell))
        print(f"{name}: ok  bg={cfg['bg']} style={cfg['style']}")
    prev_c.save(os.path.join(OUT, "nautilus-alive-preview.png"))
    prev_w.save(os.path.join(OUT, "nautilus-alive-preview-white.png"))
    print("alive preview saved.")


if __name__ == "__main__":
    main()
