"""生成一个带 n=3 超椭圆背景容器的品牌 logo (Alive 理念)。
- 背景: n=3 超椭圆, |x/a|^3 + |y/a|^3 = 1, 暖奶油 #FDFBF7 填充, 珊瑚红细描边
- 前景: 居中、比例协调的鹦鹉螺扇贝图形 (branding/nautilus-fan.svg)
输出: branding/logo.svg
"""

import math
import re

SRC = "branding/nautilus-fan.svg"
OUT = "branding/logo.svg"

# --- 1. 读取 fan 图形各 path ---
src = open(SRC, "r", encoding="utf-8").read()
paths = re.findall(r"<path\b[^>]*?/>", src, flags=re.S)

# --- 2. 计算 n=3 超椭圆背景路径 ---
N = 3.0
CX, CY = 531.0, 565.0  # viewBox 0 0 1062 1130 的中心
A = B = 505.0  # 半宽/半高 (留约 56px 安全边)


def superellipse_path(cx, cy, a, b, n, steps=240):
    pts = []
    for i in range(steps + 1):
        th = 2 * math.pi * i / steps
        c = math.cos(th)
        s = math.sin(th)
        x = cx + a * math.copysign(abs(c) ** (2.0 / n), c)
        y = cy + b * math.copysign(abs(s) ** (2.0 / n), s)
        pts.append((x, y))
    d = "M%.2f,%.2f " % pts[0]
    for x, y in pts[1:]:
        d += "L%.2f,%.2f " % (x, y)
    d += "Z"
    return d


bg = superellipse_path(CX, CY, A, B, N)

# --- 3. 把 fan 图形居中放进超椭圆内 ---
# fan viewBox 0 0 1062 1130, 图形已大致居中.
# 目标: 让 fan 图形缩放后, 其可见内容占据超椭圆内约 86% 区域, 并水平垂直居中.
# 这里直接整体 transform: 以 viewBox 中心 (531,565) 缩放 s, 中心对齐.
S = 0.86
# 计算 fan 自身包围盒(用全部 path 的 d 中的数字粗略估计已知为居中, 直接按中心缩放即可)
transform = "translate(%.2f %.2f) scale(%.4f) translate(%.2f %.2f)" % (
    CX,
    CY,
    S,
    -CX,
    -CY,
)

# --- 4. 组装 SVG ---
parts = []
parts.append(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1062 1130" '
    'width="1062" height="1130" role="img" aria-label="FundMate 多倍贝 logo">'
)
# 背景超椭圆 (Alive 理念)
parts.append(
    "  <!-- Alive: n=3 superellipse background |x/a|^3+|y/a|^3=1, a=b=505, "
    "center(531,565) -->"
)
parts.append(
    '  <path d="%s" fill="#FDFBF7" stroke="#E34F38" stroke-width="6" '
    'stroke-opacity="0.9"/>' % bg
)
# 前景扇贝图形 (居中缩放)
parts.append('  <g transform="%s">' % transform)
for p in paths:
    parts.append("    " + p)
parts.append("  </g>")
parts.append("</svg>")

open(OUT, "w", encoding="utf-8").write("\n".join(parts) + "\n")
print("written", OUT, "paths:", len(paths))
