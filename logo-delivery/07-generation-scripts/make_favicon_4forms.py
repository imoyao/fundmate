#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_favicon_4forms.py — 4 种 favicon 形态横向评比（方案 D 双轨制，≤16px 专用）

4 种形态（均超椭圆 n=3 容器 + 白螺带负空间 + 红眼居中）：
  Form 1  单螺旋线结构     : 白螺线描边（非填充带）+ 线端圆头自然收为白眼
  Form 2  最初版(小红眼标准圆): 白螺带 + 叠干净红圆 eye_r=12（"标准圆"小眼）
  Form 3  当前 v2.2(放大红眼) : 白螺带 + evenodd 内孔 eye_r=8（现交付版）
  Form 4  标准红圆+黄金比例  : 白螺带 + 叠干净红圆 eye_r=A×φ≈42（φ 派生，最醒目标准圆）

每种渲染：16px 标准尺寸 + 128px 放大看细节（深/浅双底）。
另含主版 logo.svg @16px 作为基线参照。
产出：
  logo-delivery/05-favicon/form{1..4}_*.svg / *.png
  logo_favicon_4forms_compare.png  （16px 同框 + 放大细节矩阵）
"""
import io, math, os, sys
sys.path.insert(0, "/workspace")
import numpy as np
import cairosvg
from PIL import Image, ImageDraw, ImageFont
from logo_generator import outline_path, RED, WHITE

VIEW = 512
CX = CY = 256.0
A = 26.0
B = 0.12
TURNS = 3.0
PHASE = math.pi / 2
PHI = (1 + math.sqrt(5)) / 2.0     # 黄金比例 ≈1.618
EYE_GOLDEN = A * PHI                # Form 4 红眼半径 ≈42（φ 派生）

# ----------------- 几何 -----------------
def spiral_band_path(phase=PHASE, a=A, b=B, turns=TURNS, steps=600,
                     mirror=True, inner_hole=8.0):
    te = 2 * math.pi * turns
    def _pt(r, ang):
        x = CX + r * math.cos(ang)
        y = CY - r * math.sin(ang)
        if mirror:
            x = VIEW - x
        return (x, y)
    outer, inner = [], []
    for i in range(steps + 1):
        t = te * i / steps
        outer.append(_pt(a * math.exp(b * t), t + phase))
    for i in range(steps + 1):
        t = te * (steps - i) / steps
        inner.append(_pt(inner_hole, t + phase))
    pts = outer + inner
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"


def spiral_stroke_path(phase=PHASE, a=A, b=B, turns=TURNS, steps=900, mirror=True):
    te = 2 * math.pi * turns
    pts = []
    for i in range(steps + 1):
        t = te * i / steps
        r = a * math.exp(b * t)
        ang = t + phase
        x = CX + r * math.cos(ang)
        y = CY - r * math.sin(ang)
        if mirror:
            x = VIEW - x
        pts.append((x, y))
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)


def build_form(form, eye_radius):
    d_out = outline_path(kind="superellipse", n=3.0)
    clip = f'<defs><clipPath id="fc"><path d="{d_out}"/></clipPath></defs>'
    red = f'<path d="{d_out}" fill="{RED}"/>'
    if form == "line":
        d = spiral_stroke_path()
        body = (f'<g clip-path="url(#fc)">'
                f'<path d="{d}" fill="none" stroke="{WHITE}" '
                f'stroke-width="26.0" stroke-linecap="round" stroke-linejoin="round"/>'
                f'</g>')
        return clip + red + body
    # band forms
    d = spiral_band_path(inner_hole=eye_radius)
    band = f'<g clip-path="url(#fc)"><path d="{d}" fill="{WHITE}" fill-rule="evenodd"/></g>'
    if form == "band_hole":          # Form 3: evenodd 内孔（当前 v2.2）
        return clip + red + band
    if form == "band_circle":        # Form 2 / Form 4: 叠干净红圆（标准圆）
        circle = f'<g clip-path="url(#fc)"><circle cx="{CX}" cy="{CY}" r="{eye_radius:.2f}" fill="{RED}"/></g>'
        return clip + red + band + circle
    raise ValueError(form)


FORMS = [
    ("form1", "单螺旋线结构",      "line",          0.0),
    ("form2", "最初版·小红眼标准圆", "band_circle",   12.0),
    ("form3", "当前 v2.2·放大红眼",  "band_hole",     8.0),
    ("form4", "标准红圆·黄金比例",   "band_circle",   EYE_GOLDEN),
]


def render_svg(svg, out_svg, size):
    with open(out_svg, "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" '
                f'width="{VIEW}" height="{VIEW}">{svg}</svg>')
    b = cairosvg.svg2png(url=out_svg, output_width=size, output_height=size,
                         background_color="rgba(0,0,0,0)")
    return Image.open(io.BytesIO(b)).convert("RGBA")


def measure_red_eye(png_path):
    """测量渲染图中红眼（中心红区）半径（512 画布像素），用于实证红眼尺寸。
    取包含画布中心(256,256)的红色连通分量，量其到质心最远距离 = 红眼半径。"""
    from scipy import ndimage as _nd
    im = np.array(Image.open(png_path).convert("RGBA"))
    R, G, Bc = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    A_ch = (R > 200) & (G < 140) & (Bc < 140)
    labeled, n = _nd.label(A_ch)
    if n == 0:
        return None
    best = None
    for k in range(1, n + 1):
        ys, xs = np.where(labeled == k)
        ccx, ccy = xs.mean(), ys.mean()
        # 选最靠近画布中心的分量
        if best is None or (ccx - 256) ** 2 + (ccy - 256) ** 2 < best[0]:
            d = np.sqrt((xs - ccx) ** 2 + (ys - ccy) ** 2)
            best = ((ccx - 256) ** 2 + (ccy - 256) ** 2, float(d.max()))
    return best[1]


def main():
    out_dir = "/workspace/logo-delivery/05-favicon"
    os.makedirs(out_dir, exist_ok=True)

    # 1) 生成各形态 SVG + 512 PNG
    meta = []
    for fid, ftitle, fkind, er in FORMS:
        svg = build_form(fkind, er)
        sv = f"{out_dir}/{fid}.svg"
        pn = f"{out_dir}/{fid}.png"
        img = render_svg(svg, sv, 512)
        img.save(pn)
        eye512 = measure_red_eye(pn)
        meta.append((fid, ftitle, fkind, er, sv, pn, eye512))
        print(f"{fid:6s} {ftitle:18s} kind={fkind:12s} eye_r(512)={er:6.1f} -> 实测红眼={eye512}")

    # 2) 构建对比矩阵 PNG：每行一种形态，列=[16px浅,16px深,放大128浅,放大128深]
    fonts = "/usr/share/fonts/opentype/noto/NotoSansCJK"
    fnt = ImageFont.truetype(f"{fonts}-Regular.ttc", 18)
    fntb = ImageFont.truetype(f"{fonts}-Bold.ttc", 20)
    fnts = ImageFont.truetype(f"{fonts}-Regular.ttc", 14)

    COLS = ["16px · 浅底", "16px · 深底", "128px · 浅底(放大)", "128px · 深底(放大)"]
    cell = 200
    label_w = 220
    W = label_w + len(COLS) * cell
    H = 70 + len(meta) * (cell + 36)
    img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)

    # 表头
    d.text((12, 18), "多倍贝 favicon 4 形态横向评比", fill=(26, 24, 22, 255), font=fntb)
    for j, c in enumerate(COLS):
        d.text((label_w + j * cell + cell // 2, 50), c,
               fill=(107, 101, 92, 255), font=fnts, anchor="mm")
    d.line([(0, 66), (W, 66)], fill=(214, 208, 199, 255), width=1)

    for i, (fid, ftitle, fkind, er, sv, pn, eye512) in enumerate(meta):
        y0 = 70 + i * (cell + 36)
        d.text((12, y0 + cell // 2 - 16), ftitle, fill=(26, 24, 22, 255), font=fntb, anchor="lm")
        note = f"eye_r≈{er:.0f} (512) · 实测红眼≈{eye512:.0f}px" if eye512 else f"eye_r≈{er:.0f} (512)"
        d.text((12, y0 + cell // 2 + 10), note, fill=(107, 101, 92, 255), font=fnts, anchor="lm")
        tiles = [
            (render_svg(build_form(fkind, er), "/tmp/_t.svg", 16),  (253, 251, 247)),
            (render_svg(build_form(fkind, er), "/tmp/_t.svg", 16),  (26, 24, 22)),
            (render_svg(build_form(fkind, er), "/tmp/_t.svg", 128), (253, 251, 247)),
            (render_svg(build_form(fkind, er), "/tmp/_t.svg", 128), (26, 24, 22)),
        ]
        for j, (tile, bg) in enumerate(tiles):
            x = label_w + j * cell
            d.rectangle([x + 8, y0 + 8, x + cell - 8, y0 + cell - 8], fill=bg + (255,))
            s = tile.size[0]
            img.paste(tile, (x + (cell - s) // 2, y0 + (cell - s) // 2), tile)
    img.convert("RGB").save("/workspace/logo_favicon_4forms_compare.png")
    print("logo_favicon_4forms_compare.png", img.size)

    # 3) 16px 同框速览（4 形态 + 主版基线）
    comp = Image.new("RGBA", (6 * 160, 220), (253, 251, 247, 255))
    cd = ImageDraw.Draw(comp)
    items = [(ftitle, render_svg(build_form(fk, er), "/tmp/_t.svg", 16)) for fid, ftitle, fk, er, *_ in meta]
    _b = cairosvg.svg2png(url="/workspace/logo.svg", output_width=16, output_height=16,
                          background_color="rgba(0,0,0,0)")
    items.append(("主版 logo.svg", Image.open(io.BytesIO(_b)).convert("RGBA")))
    for k, (lbl, t) in enumerate(items):
        x = 20 + k * 160
        comp.paste(t, (x + (120 - t.size[0]) // 2, 20), t)
        cd.text((x + 60, 175), lbl, fill=(26, 24, 22, 255), font=fnts, anchor="mm")
    comp.convert("RGB").save("/workspace/logo_favicon_16px_lineup.png")
    print("logo_favicon_16px_lineup.png", comp.size)


if __name__ == "__main__":
    main()
