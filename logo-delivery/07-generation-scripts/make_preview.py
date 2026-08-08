#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成满福 Logo 多形态对比预览 PNG（直角 / 超椭圆 / 圆角，附目标图参照）"""
import io
import os
import numpy as np
import cairosvg
from PIL import Image, ImageDraw, ImageFont

CANVAS_BG = (233, 233, 233)   # 浅灰，用于显出超椭圆透明角
TARGET_IMG = os.path.join(os.path.dirname(__file__), "assets", "4768.jpg")
VIEW = 512

def render_svg(path, size=VIEW):
    png = cairosvg.svg2png(url=path, output_width=size, output_height=size,
                           background_color="rgba(0,0,0,0)")
    return Image.open(io.BytesIO(png)).convert("RGBA")

def render_image(path, size=VIEW):
    im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    return im

def compose(items, cols=3, cell=VIEW, pad=24, label_h=34, font_path=None):
    """items: [(svg_path, label)]，渲染为网格对比图"""
    n = len(items)
    rows = (n + cols - 1) // cols
    W = cols * cell + (cols + 1) * pad
    H = rows * (cell + label_h) + (rows + 1) * pad
    img = Image.new("RGBA", (W, H), CANVAS_BG + (255,))
    draw = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 20)
    except Exception:
        fnt = ImageFont.load_default()
    for i, (svg, label) in enumerate(items):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = pad + r * (cell + label_h + pad)
        tile = render_svg(svg, cell) if svg.lower().endswith(".svg") else render_image(svg, cell)
        img.paste(tile, (x, y), tile)
        draw.text((x, y + cell + 6), label, fill=(40, 40, 40, 255), font=fnt)
    return img.convert("RGB")

if __name__ == "__main__":
    out = compose([
        (TARGET_IMG,             "目标图 4768.jpg（参照）"),
        ("logo_square.svg",      "① 直角 (Square) — trace"),
        ("logo_superellipse.svg","② 超椭圆 (Superellipse n=3) — trace"),
        ("logo_rounded.svg",     "③ 圆角 (Rounded) — trace"),
        ("logo_circle.svg",      "④ 圆形 (Circle) — trace"),
    ], cols=5)
    out.save("logo_forms_compare.png")
    print("已生成 -> logo_forms_compare.png", out.size)
