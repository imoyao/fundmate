#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_single_spiral.py — 单螺旋线辅助图形（仅螺线，无外框，无文字）
用于：水印 / 分隔符 / 装饰图案 / 品牌延展。

三种配色（512 画布，透明底）：
  color : 品牌珊瑚红描边  #E34F38（与容器同色，作独立装饰线）
  white : 暖奶油描边      #FDFBF7
  mono  : 深墨描边        #1A1816

几何：与主 Logo 同一定义 —— 对数螺旋 r=a·e^(bθ)，开口正上(90°)、水平镜像(旋向一致)。
"""
import io, math, sys
sys.path.insert(0, "/workspace")
import cairosvg
from PIL import Image
from logo_generator import RED, WHITE

VIEW = 512
CX = CY = 256.0
A = 26.0          # 起始半径（与 favicon 母本一致）
B = 0.12          # 增长率
TURNS = 3.0       # 圈数
PHASE = math.pi / 2   # 正上方开口（12 点钟）
STROKE = 22.0     # 螺线描边宽度（512 画布）；作装饰线偏粗更易识别
MONO = "#1A1816"


def spiral_stroke_path(phase=PHASE, a=A, b=B, turns=TURNS, steps=900, mirror=True):
    """单条对数螺旋中心线（用于描边，而非填充带）。"""
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


def build(color_hex, out_svg):
    d = spiral_stroke_path()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" '
           f'width="{VIEW}" height="{VIEW}">'
           f'<path d="{d}" fill="none" stroke="{color_hex}" '
           f'stroke-width="{STROKE:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
           f'</svg>')
    with open(out_svg, "w") as f:
        f.write(svg)
    return svg


def render(out_svg, out_png, size=512):
    b = cairosvg.svg2png(url=out_svg, output_width=size, output_height=size,
                         background_color="rgba(0,0,0,0)")
    Image.open(io.BytesIO(b)).convert("RGBA").save(out_png)


if __name__ == "__main__":
    base = "/workspace/logo-delivery/04-auxiliary-graphics"
    import os
    os.makedirs(base, exist_ok=True)
    specs = [
        ("color", RED,   f"{base}/spiral_single_color.svg",  f"{base}/spiral_single_color.png"),
        ("white", WHITE, f"{base}/spiral_single_white.svg",  f"{base}/spiral_single_white.png"),
        ("mono",  MONO,  f"{base}/spiral_single_mono.svg",   f"{base}/spiral_single_mono.png"),
    ]
    for name, hexc, sv, pn in specs:
        build(hexc, sv)
        render(sv, pn)
        print(f"辅助图形[{name}] -> {sv} / {pn}")
