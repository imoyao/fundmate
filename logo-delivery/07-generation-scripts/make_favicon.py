#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logo_favicon.py — 简化版 favicon（≤16px 专用，方案 D 双轨制）

依据 v1.7 §5.4「小尺寸简化版」语义：去最内圈、留 4-5 圈、线宽 3-3.5px。
实现为【填充白螺带】(负空间风格，与主 logo 一致)，而非细描边——保证在 16px 下
白螺带仍有 ~3px 可见宽度，而不是坍塌成白点。

v2 修订（2026-08-08）：
  - 开口方向改为【正上方 12 点钟】(B 方案，用户拍板)：PHASE = 90°，壳口向上、向上生长。
  - 新增【像素质心自动居中】：渲染后算白螺带质心，平移使落在画布中心，修正偏左。

产出：
  logo_favicon.svg                 简化版交付源（超椭圆 n=3 容器 + 白螺带）
  logo_favicon_preview.png        16/24/32/48/64 深/浅双底清晰度
  logo_favicon_vs_trace.png       16px 下 简化版 vs 主版 同框对比
"""
import io, math, sys
sys.path.insert(0, "/workspace")
import numpy as np
import cairosvg
from PIL import Image, ImageDraw, ImageFont
from logo_generator import outline_path, RED, WHITE

VIEW = 512
CX = CY = 256.0

# 螺带参数（512 画布坐标系）
A      = 26.0    # 内圈起始半径
B      = 0.12    # 增长率（每圈 ×e^(2πb)≈2.13）
TURNS  = 3.0     # 圈数（去最内圈后留 ~3 圈主臂 + 实心眼）
BAND   = 100.0   # 螺带宽度（512画布）；@16px ≈ 100/512*16 ≈ 3.1px（符合 §5.4 线宽）
PHASE  = math.pi / 2   # 90° = 正上方开口（12点钟，B 方案：向上螺旋）
INNER_HOLE = 18.0   # 中心红眼半径（512画布）；用 evenodd 强制内圆为孔（干净标准红圆，无 overlay 漏红）；
                    # 18 为「等比例协调」取值：放大图清晰可见、16px 下为小点；相对旧 8 更醒目且不过分

def spiral_band_path(phase=PHASE, a=A, b=B, turns=TURNS, band=BAND,
                     steps=600, mirror=True, inner_hole=INNER_HOLE):
    te = 2 * math.pi * turns
    def _pt(r, ang):
        x = CX + r * math.cos(ang)
        y = CY - r * math.sin(ang)
        if mirror:
            x = VIEW - x          # 水平镜像（左右翻转，旋向随之反转）
        return (x, y)
    outer, inner = [], []
    for i in range(steps + 1):
        t = te * i / steps
        r = a * math.exp(b * t)
        ang = t + phase
        outer.append(_pt(r, ang))
    for i in range(steps + 1):
        t = te * (steps - i) / steps
        r = inner_hole           # 内边界为半径 inner_hole 的圆 → 中心留出红眼
        ang = t + phase
        inner.append(_pt(r, ang))
    pts = outer + inner
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"

def _render_white_centroid(d_spi, size=VIEW):
    """渲染白螺带（不含红容器、不裁切），返回 (cx, cy) 质心与开口方位角。"""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" '
           f'width="{VIEW}" height="{VIEW}"><path d="{d_spi}" fill="{WHITE}"/></svg>')
    b = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size,
                         background_color="rgba(0,0,0,0)")
    im = np.array(Image.open(io.BytesIO(b)).convert("RGBA"))
    mask = im[:, :, 3] > 30
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return (CX, CY, None)
    cx = float(xs.mean()); cy = float(ys.mean())
    # 开口方位角：白像素中距质心最远的点的方向（最开放端）
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    k = int(np.argmax(d))
    ang = math.degrees(math.atan2(-(ys[k] - cy), xs[k] - cx))  # y 向上为正
    if ang < 0:
        ang += 360
    return (cx, cy, ang)

def build_favicon():
    d_out = outline_path(kind="superellipse", n=3.0)
    d_spi = spiral_band_path()
    # v3 居中修正（2026-08-08，用户反馈偏左）：
    #   之前把红眼(建造原点 CX,CY)锁画布正中，但白螺带质心本就偏左(~46px)，导致视觉整体偏左。
    #   改为「白螺带质心居中」——整体右移，使螺带质量落在画布中心、左右平衡（以缺口为视觉对称基准）。
    cx, cy, opening_ang = _render_white_centroid(d_spi)
    dx = VIEW / 2.0 - cx
    dy = VIEW / 2.0 - cy
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" '
           f'width="{VIEW}" height="{VIEW}">'
           f'<defs><clipPath id="fc"><path d="{d_out}"/></clipPath></defs>'
           f'<path d="{d_out}" fill="{RED}"/>'
           f'<g clip-path="url(#fc)"><g transform="translate({dx:.2f},{dy:.2f})">'
           f'<path d="{d_spi}" fill="{WHITE}" fill-rule="evenodd"/>'
           f'</g></g>'
           f'</svg>')
    with open("/workspace/logo_favicon.svg", "w") as f:
        f.write(svg)
    return svg, (dx, dy, cx, cy, opening_ang)

def render(path, size):
    b = cairosvg.svg2png(url=path, output_width=size, output_height=size,
                         background_color="rgba(0,0,0,0)")
    return Image.open(io.BytesIO(b)).convert("RGBA")

def main():
    svg, (dx, dy, cx, cy, opening_ang) = build_favicon()
    print(f"白质心居中平移: dx={dx:+.1f} dy={dy:+.1f} | 白质心=({cx:.0f},{cy:.0f}) | 开口方位角={opening_ang:.0f}° (90°=正上)")

    sizes = [16, 24, 32, 48, 64]
    pad, label_h = 24, 30
    W = len(sizes) * 240 + (len(sizes) + 1) * pad
    row_h = 240 + label_h
    H = 2 * row_h + 3 * pad
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fnt = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 20)
    fntb = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 20)
    for r, (bg_hex, bg_name) in enumerate([("#FDFBF7", "浅色背景 #FDFBF7"), ("#1A1816", "深色背景 #1A1816")]):
        bg = tuple(int(bg_hex[i:i+2], 16) for i in (1, 3, 5))
        img.paste(Image.new("RGBA", (W - 2 * pad, row_h), bg + (255,)), (pad, pad + r * (row_h + pad)))
        for i, s in enumerate(sizes):
            x = pad + i * (240 + pad); y = pad + r * (row_h + pad)
            tile = render("/workspace/logo_favicon.svg", s)
            img.paste(tile, (x + (240 - s) // 2, y + (240 - s) // 2), tile)
            d.text((x + 120, y + 244), f"{s}px", fill=((26, 24, 22) if bg_hex == "#FDFBF7" else (253, 251, 247)) + (255,),
                   font=fnt, anchor="mm")
        d.text((pad + 4, pad + r * (row_h + pad) + 4), bg_name,
               fill=((26, 24, 22) if bg_hex == "#FDFBF7" else (253, 251, 247)) + (255,), font=fntb)
    img.convert("RGB").save("/workspace/logo_favicon_preview.png")
    print("logo_favicon_preview.png", img.size)

    comp = Image.new("RGBA", (640, 360), (0, 0, 0, 0))
    cd = ImageDraw.Draw(comp)
    cd.rectangle([0, 0, 320, 360], fill=(253, 251, 247, 255))
    cd.rectangle([320, 0, 640, 360], fill=(253, 251, 247, 255))
    for col, (lbl, path) in enumerate([("主版 logo.svg (16px)", "/workspace/logo.svg"),
                                       ("简化版 logo_favicon.svg (16px)", "/workspace/logo_favicon.svg")]):
        t = render(path, 16)
        comp.paste(t, (80 + col * 320, 80), t)
        cd.text((160 + col * 320, 250), lbl, fill=(26, 24, 22, 255),
                font=ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 18), anchor="mm")
        t2 = render(path, 48)
        comp.paste(t2, (136 + col * 320, 280), t2)
        cd.text((160 + col * 320, 340), "48px 放大参考", fill=(107, 101, 92, 255),
                font=ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 16), anchor="mm")
    comp.convert("RGB").save("/workspace/logo_favicon_vs_trace.png")
    print("logo_favicon_vs_trace.png", comp.size)

if __name__ == "__main__":
    main()
