"""Generate nautilus logo candidates per brand-v1.6.md, inspired by the
user-provided shell silhouette references (no external assets used).

Key idea vs the earlier "mosquito" single-line spiral:
  - use a *band* (filled ribbon) following a logarithmic spiral,
  - band width grows with radius so the outer whorl is a fat "body chamber"
    (shell aperture) while the inner coil stays a thin spiral -> reads as a
    nautilus shell, not a mosquito coil,
  - offset the spiral centre (eccentric) so the shell is asymmetric.

Brand tokens (brand-v1.6.md §3.1): coral red #E34F38, warm cream #FDFBF7.
"""

import math
import os
from PIL import Image, ImageDraw

VB = 100.0
CORAL = (227, 79, 56, 255)  # #E34F38 --brand-700 / --color-rise
CREAM = (253, 251, 247, 255)  # #FDFBF7 --bg-warm
WHITE = (255, 255, 255, 255)
OUT = os.path.join(os.path.dirname(__file__), "..", "branding")


def spiral(cx, cy, a, b, tmax, phase, n):
    pts = []
    for i in range(n + 1):
        t = tmax * i / n
        r = a * math.exp(b * t)
        ang = t + phase
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang), r))
    return pts


def band(pts, hwfn):
    """Return (outer, inner) offset edge polylines of a spiral ribbon."""
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


def svg_path(poly, closed=True):
    d = "M%.2f %.2f " % poly[0]
    for x, y in poly[1:]:
        d += "L%.2f %.2f " % (x, y)
    if closed:
        d += "Z"
    return d.strip()


def make_svg(outer, inner, circle, style):
    """style: 'fill' (solid shell) or 'stroke' (outline only)."""
    s = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'fill="none" stroke="#E34F38" stroke-linejoin="round" '
        'stroke-linecap="round">'
    ]
    if circle:
        s.append('<circle cx="50" cy="50" r="%.2f" stroke-width="3.0"/>' % circle)
    if style == "fill":
        # closed band (outer forward + inner reversed) -> ribbon fill
        ribbon = outer + inner[::-1]
        s.append('<path d="%s" fill="#E34F38" stroke="none"/>' % svg_path(ribbon))
    else:  # stroke: two open edges of the shell
        s.append('<path d="%s" stroke-width="2.6"/>' % svg_path(outer, False))
        s.append('<path d="%s" stroke-width="2.6"/>' % svg_path(inner, False))
    s.append("</svg>")
    return "\n".join(s)


def render_pil(outer, inner, circle, style, size, scale=8):
    H = size * scale
    img = Image.new("RGBA", (H, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    S = scale
    if circle:
        d.ellipse(
            [
                (50 - circle) * S,
                (50 - circle) * S,
                (50 + circle) * S,
                (50 + circle) * S,
            ],
            outline=CORAL,
            width=max(1, int(3.0 * S)),
        )
    if style == "fill":
        poly = [(x * S, y * S) for x, y in (outer + inner[::-1])]
        d.polygon(poly, fill=CORAL)
    else:
        for edge in (outer, inner):
            d.line(
                [(x * S, y * S) for x, y in edge],
                fill=CORAL,
                width=max(1, int(2.6 * S)),
                joint="curve",
            )
    return img.resize((size, size), Image.LANCZOS)


# ---- version definitions ----------------------------------------------
# eccentric centre; phase chosen so the fat outer whorl sits bottom-right
def phase_for(tmax):
    return math.pi / 4 - tmax  # outer max-radius point -> 45deg (bottom-right)


VERSIONS = {
    "v1": dict(
        cx=40,
        cy=40,
        a=2.4,
        b=0.16,
        turns=2.4,
        hw=lambda r: 1.6 + (r / 26.8) * 7.0,
        circle=None,
        style="fill",
    ),
    "v2": dict(
        cx=40,
        cy=40,
        a=2.4,
        b=0.16,
        turns=2.4,
        hw=lambda r: 1.6 + (r / 26.8) * 7.0,
        circle=33.0,
        style="fill",
    ),
    "v3": dict(
        cx=40,
        cy=40,
        a=2.4,
        b=0.16,
        turns=2.4,
        hw=lambda r: 1.6 + (r / 26.8) * 7.0,
        circle=None,
        style="stroke",
    ),
    "v4": dict(
        cx=40,
        cy=40,
        a=2.7,
        b=0.155,
        turns=2.2,
        hw=lambda r: 2.2 + (r / 25.0) * 6.0,
        circle=None,
        style="fill",
    ),
}


def build(name, cfg):
    tmax = cfg["turns"] * 2 * math.pi
    phase = phase_for(tmax)
    pts = spiral(cfg["cx"], cfg["cy"], cfg["a"], cfg["b"], tmax, phase, 400)
    outer, inner = band(pts, cfg["hw"])
    svg = make_svg(outer, inner, cfg["circle"], cfg["style"])
    # 512 master png (transparent)
    big = render_pil(outer, inner, cfg["circle"], cfg["style"], 512)
    white = Image.new("RGBA", (512, 512), CREAM)
    white.alpha_composite(big)
    return svg, big, white


def main():
    os.makedirs(OUT, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128]
    cols = len(sizes)
    rows = len(VERSIONS)
    pad = 12
    cell = 128 + pad
    # cream-background preview
    prev_c = Image.new("RGBA", (cols * cell + pad, rows * cell + pad), CREAM)
    prev_w = Image.new("RGBA", (cols * cell + pad, rows * cell + pad), WHITE)
    for ri, (name, cfg) in enumerate(VERSIONS.items()):
        svg, big, white = build(name, cfg)
        with open(os.path.join(OUT, f"nautilus-{name}.svg"), "w") as f:
            f.write(svg)
        big.save(os.path.join(OUT, f"nautilus-{name}.png"))
        white.save(os.path.join(OUT, f"nautilus-{name}-white.png"))
        for ci, sz in enumerate(sizes):
            tile = render_pil(*_edges(name, cfg, sz))
            prev_c.alpha_composite(tile, (pad + ci * cell, pad + ri * cell))
            prev_w.alpha_composite(tile, (pad + ci * cell, pad + ri * cell))
        print(f"{name}: ok  style={cfg['style']} circle={cfg['circle']}")
    prev_c.save(os.path.join(OUT, "nautilus-versions-preview.png"))
    prev_w.save(os.path.join(OUT, "nautilus-versions-preview-white.png"))
    print("preview saved.")


def _edges(name, cfg, sz):
    tmax = cfg["turns"] * 2 * math.pi
    phase = phase_for(tmax)
    pts = spiral(cfg["cx"], cfg["cy"], cfg["a"], cfg["b"], tmax, phase, 400)
    outer, inner = band(pts, cfg["hw"])
    return outer, inner, cfg["circle"], cfg["style"], sz


if __name__ == "__main__":
    main()
