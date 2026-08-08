#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_combo.py — 横版组合生成器（"多倍贝 · 投资账本"）

副标字号 = 主名字号 × SUB_SCALE（黄金比例 0.618）。
主名：多倍贝（红粗 700，60px）
副标：投资账本（灰常规 400，60×0.618≈37px）
分隔符：·（灰色）
"""
import io, sys
sys.path.insert(0, "/workspace")
import cairosvg
from PIL import Image, ImageFont

WS = "/workspace"
RED, WHITE, SEC = "#E34F38", "#FDFBF7", "#6B655C"
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

SUB_SCALE = 0.618   # 黄金比例（副标相对主名字号）


def extract_inner(svg_path):
    s = open(svg_path).read()
    i = s.index("<svg"); j = s.index(">", i) + 1; k = s.rindex("</svg>")
    return s[j:k]


def build(sub_scale=SUB_SCALE):
    inner = extract_inner(f"{WS}/logo.svg")
    icon = 220.0; scale = icon / 512.0
    icon_left = 48.0; gap = icon / 3.0
    fs_main = 60.0; fs_sub = fs_main * sub_scale
    fnt_b = ImageFont.truetype(FONT_B, int(fs_main))
    fnt_r = ImageFont.truetype(FONT_R, int(fs_sub))
    name, dot, sub = "多倍贝", "·", "投资账本"
    w1 = fnt_b.getlength(name)
    wdot = fnt_r.getlength(" " + dot + " ")
    w2 = fnt_r.getlength(sub)
    text_w = w1 + wdot + w2
    H = 300.0
    icon_top = (H - icon) / 2.0
    text_x0 = icon_left + icon + gap
    W = text_x0 + text_w + 60.0
    baseline = H / 2.0 + fs_main * 0.34
    sub_baseline = H / 2.0 + fs_sub * 0.34
    combo = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
        f'width="{W:.0f}" height="{H:.0f}">'
        f'<g transform="translate({icon_left:.1f},{icon_top:.1f}) scale({scale:.5f})">{inner}</g>'
        f'<text x="{text_x0:.1f}" y="{baseline:.1f}" font-family="Noto Sans CJK SC" '
        f'font-weight="700" font-size="{fs_main:.0f}" fill="{RED}">{name}</text>'
        f'<text x="{text_x0+w1+wdot/2:.1f}" y="{sub_baseline:.1f}" font-family="Noto Sans CJK SC" '
        f'font-weight="400" font-size="{fs_sub:.0f}" fill="{SEC}" text-anchor="middle">{dot}</text>'
        f'<text x="{text_x0+w1+wdot:.1f}" y="{sub_baseline:.1f}" font-family="Noto Sans CJK SC" '
        f'font-weight="400" font-size="{fs_sub:.0f}" fill="{SEC}">{sub}</text>'
        f'</svg>')
    open(f"{WS}/logo_horizontal_combo.svg", "w").write(combo)
    png = cairosvg.svg2png(bytestring=combo.encode(), output_width=int(W), output_height=int(H),
                           background_color=WHITE)
    Image.open(io.BytesIO(png)).convert("RGB").save(f"{WS}/logo_horizontal_combo.png")
    print(f"combo: 主名{fs_main:.0f}px 副标{fs_sub:.1f}px(×{sub_scale})  W={W:.0f} text_w={text_w:.1f}")


if __name__ == "__main__":
    build()
