#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_favicon_final.py — 终选 2 形态 favicon 对比（按 2026-08-08 用户反馈收敛）

Form 1  单螺旋线结构（原生态） : 主 logo 白色鹦鹉螺螺带（trace 描摹、自然带宽、去红背景）+ 透明底。
                                即「主版去掉红色容器」——单条有粗细变化的原生态螺旋，抖音音符感。
Form 4  标准红圆 · 红白红三层  : 红容器 + 白螺带(evenodd 干净内孔红圆) + 中心标准红圆(等比例协调 r=18)。
                                无 overlay 漏红、无多余白条；白质心居中（右移修正偏左）。

已淘汰：Form 2(小红眼标准圆) / Form 3(放大红眼) —— 与最初版肉眼无差，用户已弃用。

产出：
  logo-delivery/05-favicon/form1.svg / .png     （原生态单螺带）
  logo-delivery/05-favicon/form4.svg / .png     （标准红圆三层，= logo_favicon.svg 修正版）
  logo_favicon_final_compare.png                （Form1 vs Form4，16px + 放大，深/浅双底）
  logo_favicon_final_lineup.png                 （两版 16px 同框 + 主版基线）
"""
import io, math, os, sys
sys.path.insert(0, "/workspace")
import cairosvg
from PIL import Image, ImageDraw, ImageFont
from logo_generator import generate_trace, RED, WHITE

VIEW = 512
OUT = "/workspace/logo-delivery/05-favicon"
FONTS = "/usr/share/fonts/opentype/noto/NotoSansCJK"


def build_form1():
    """Form 1：原生态白螺带，透明底（去红背景）。"""
    sv = f"{OUT}/form1.svg"
    # trace 主螺旋、透明底纯白线（draw_red=False）、不裁切（缺口自然露出）、中心对齐
    generate_trace(sv, outline="superellipse", draw_red=False, clip=False,
                   center=True, tension_center=0.9)
    png = cairosvg.svg2png(url=sv, output_width=512, output_height=512,
                           background_color="rgba(0,0,0,0)")
    Image.open(io.BytesIO(png)).convert("RGBA").save(f"{OUT}/form1.png")
    return sv


def build_form1_red():
    """Form 1R：原生态螺带着主题红(#E34F38)、透明底（去红背景、去红容器）。
    即 Form 1 的白螺带改为主题红——浅色背景可见，深色背景亦清晰。"""
    sv = f"{OUT}/form1_red.svg"
    generate_trace(sv, outline="superellipse", draw_red=False, clip=False,
                   center=True, tension_center=0.9, white=RED)
    png = cairosvg.svg2png(url=sv, output_width=512, output_height=512,
                           background_color="rgba(0,0,0,0)")
    Image.open(io.BytesIO(png)).convert("RGBA").save(f"{OUT}/form1_red.png")
    return sv


def build_form4():
    """Form 4：标准红圆三层 = 修正版 logo_favicon.svg（白质心居中 + 协调红眼 r=18）。"""
    sv = "/workspace/logo_favicon.svg"
    png = cairosvg.svg2png(url=sv, output_width=512, output_height=512,
                           background_color="rgba(0,0,0,0)")
    Image.open(io.BytesIO(png)).convert("RGBA").save(f"{OUT}/form4.png")
    import shutil
    shutil.copy(sv, f"{OUT}/form4.svg")
    return sv


def render(url, size):
    b = cairosvg.svg2png(url=url, output_width=size, output_height=size,
                         background_color="rgba(0,0,0,0)")
    return Image.open(io.BytesIO(b)).convert("RGBA")


def main():
    os.makedirs(OUT, exist_ok=True)
    build_form1()
    build_form1_red()
    build_form4()
    print("Form1 / Form1R / Form4 已生成")

    forms = [
        ("Form 1 · 原生态白螺带(透明底)", f"{OUT}/form1.svg"),
        ("Form 1R · 原生态红螺带(透明底)", f"{OUT}/form1_red.svg"),
        ("Form 4 · 标准红圆(红白红三层)", f"{OUT}/form4.svg"),
    ]

    fnt = ImageFont.truetype(f"{FONTS}-Regular.ttc", 18)
    fntb = ImageFont.truetype(f"{FONTS}-Bold.ttc", 20)
    fnts = ImageFont.truetype(f"{FONTS}-Regular.ttc", 14)

    # 对比矩阵：每行一种形态，列 = [16浅, 16深, 128浅, 128深]
    # 注：Form1 透明底白螺带在浅底不可见 → 浅底格改放「深底描边参考」，此处统一用深底为主、浅底为辅标注
    COLS = ["16px · 深底", "16px · 浅底", "128px · 深底(放大)", "128px · 浅底(放大)"]
    cell = 200
    label_w = 260
    W = label_w + len(COLS) * cell
    H = 70 + len(forms) * (cell + 36)
    img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((12, 18), "多倍贝 favicon 终选 3 形态对比", fill=(26, 24, 22, 255), font=fntb)
    for j, c in enumerate(COLS):
        d.text((label_w + j * cell + cell // 2, 50), c,
               fill=(107, 101, 92, 255), font=fnts, anchor="mm")
    d.line([(0, 66), (W, 66)], fill=(214, 208, 199, 255), width=1)

    for i, (title, sv) in enumerate(forms):
        y0 = 70 + i * (cell + 36)
        d.text((12, y0 + cell // 2 - 8), title, fill=(26, 24, 22, 255), font=fntb, anchor="lm")
        # 深底为主展示（Form1 透明底白螺带在深底清晰）；浅底格同样渲染供参考
        tiles = [
            (render(sv, 16), (26, 24, 22)),
            (render(sv, 16), (253, 251, 247)),
            (render(sv, 128), (26, 24, 22)),
            (render(sv, 128), (253, 251, 247)),
        ]
        for j, (tile, bg) in enumerate(tiles):
            x = label_w + j * cell
            d.rectangle([x + 8, y0 + 8, x + cell - 8, y0 + cell - 8], fill=bg + (255,))
            s = tile.size[0]
            img.paste(tile, (x + (cell - s) // 2, y0 + (cell - s) // 2), tile)
    img.convert("RGB").save("/workspace/logo_favicon_final_compare.png")
    print("logo_favicon_final_compare.png", img.size)

    # 16px 同框速览（Form1 / Form4 / 主版基线）
    comp = Image.new("RGBA", (6 * 160, 220), (253, 251, 247, 255))
    cd = ImageDraw.Draw(comp)
    items = [(t, render(s, 16)) for t, s in forms]
    _b = cairosvg.svg2png(url="/workspace/logo.svg", output_width=16, output_height=16,
                          background_color="rgba(0,0,0,0)")
    items.append(("主版 logo.svg", Image.open(io.BytesIO(_b)).convert("RGBA")))
    for k, (lbl, t) in enumerate(items):
        x = 20 + k * 160
        comp.paste(t, (x + (120 - t.size[0]) // 2, 20), t)
        cd.text((x + 60, 175), lbl, fill=(26, 24, 22, 255), font=fnts, anchor="mm")
    comp.convert("RGB").save("/workspace/logo_favicon_final_lineup.png")
    print("logo_favicon_final_lineup.png", comp.size)


if __name__ == "__main__":
    main()
