#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logo_generator.py — 满福/慢富 Logo 矢量生成器
====================================================================
默认模式：几何对数螺旋（等角螺旋）—— r = a·e^(bθ)
  光滑、精确、无伪影。参数从目标图 4768.jpg 实测推导。

可用模式：
  log     : 几何对数螺旋（推荐，默认）—— 参数方程直接生成
  banded  : 位图骨架化描边（备选）—— skeletonize → stroke
  filled  : 位图实心填充（备选）—— find_contours → fill

几何螺旋参数（默认值匹配目标 4768.jpg）：
  a=36        : 起始半径（内圈紧度）
  b=0.120     : 增长率（每圈半径 × e^(2πb) ≈ ×2.11）
  turns=2.5   : 圈数
  breakout=108°: 破口方向（11 点钟稍偏左）
  stroke=24   : 带宽（SVG stroke-width）

历史遗留：filled/banded 位图模式保留用于对比参考。
"""
import argparse, math, io, os, re
import numpy as np
from PIL import Image
import cairosvg
from skimage.measure import find_contours, approximate_polygon

# ---------------- 默认参数 ----------------
SRC_DEFAULT = os.path.join(os.path.dirname(__file__), "assets", "4764.jpg")
# V1 (portrait) 红色方块 bbox：CROP_SRC=(111,293,67,249)，182×182
CROP_SRC = (111, 293, 67, 249)
# 螺旋方向：V1 旋转 30° 顺时针（在 SVG 内 transform 旋转），与目标 4768.jpg 一致
SPIRAL_ROTATE = -30.0
RED   = "#E34F38"   # 品牌令牌 --brand-700 / --color-rise（多倍贝 设计语言 v2.3.3）
WHITE = "#FDFBF7"   # 品牌暖奶油令牌 --bg-page（螺线为负空间填充色；如需更高小尺寸对比可改 --bg-card #FFFFFF）
VIEWBOX = 512
# V1 icon 边长 182，目标 442（≈86%），给红方块四周留 ~35px 均匀珊瑚红边距
SC = 442.0 / 182.0
CORNER_R_RATIO = 0.165


# ---------------- 外轮廓（直角 / 圆角 / 超椭圆） ----------------
def square_path(size=512.0, inset=0.0):
    """直角方形。inset>0 时四周留透明边距（用于露出白线破口）"""
    s = size
    i = inset
    return f"M {i:.2f},{i:.2f} L {s-i:.2f},{i:.2f} L {s-i:.2f},{s-i:.2f} L {i:.2f},{s-i:.2f} Z"


def rounded_square_path(size=512.0, r=84.0, inset=0.0):
    """圆角方形（iOS app icon 风格）。inset>0 时四周留透明边距。"""
    s = size
    i = inset
    cr = min(r, (s - 2 * i) / 2.0)
    return (
        f"M {i+cr:.2f},{i:.2f} "
        f"L {s-i-cr:.2f},{i:.2f} "
        f"A {cr:.2f},{cr:.2f} 0 0 1 {s-i:.2f},{i+cr:.2f} "
        f"L {s-i:.2f},{s-i-cr:.2f} "
        f"A {cr:.2f},{cr:.2f} 0 0 1 {s-i-cr:.2f},{s-i:.2f} "
        f"L {i+cr:.2f},{s-i:.2f} "
        f"A {cr:.2f},{cr:.2f} 0 0 1 {i:.2f},{s-i-cr:.2f} "
        f"L {i:.2f},{i+cr:.2f} "
        f"A {cr:.2f},{cr:.2f} 0 0 1 {i+cr:.2f},{i:.2f} Z"
    )


def superellipse_path(cx=256.0, cy=256.0, a=256.0, b=256.0, n=3.0, steps=240, inset=0.0):
    """超椭圆（Lamé 曲线）|x/a|^n + |y/b|^n = 1，n=3 近似小米风。inset>0 时缩小半轴。"""
    a2, b2 = a - inset, b - inset
    pts = []
    for k in range(steps):
        t = 2.0 * math.pi * k / steps
        ct, st = math.cos(t), math.sin(t)
        x = cx + a2 * math.copysign(abs(ct) ** (2.0 / n), ct)
        y = cy + b2 * math.copysign(abs(st) ** (2.0 / n), st)
        pts.append((x, y))
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"


def circle_path(size=512.0, inset=0.0):
    """圆形轮廓。inset>0 时半径缩小，四周留透明边距。"""
    cx = cy = size / 2.0
    rad = size / 2.0 - inset
    steps = 64
    pts = [(cx + rad * math.cos(2 * math.pi * k / steps),
            cy + rad * math.sin(2 * math.pi * k / steps)) for k in range(steps)]
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"


def outline_path(kind="square", size=512.0, r=84.0, n=3.0, inset=0.0):
    """按 kind 返回外框 path：square / rounded / superellipse / circle。
    inset>0 时四周留透明边距，使白线破口能越出红边、露在背景上。"""
    if kind == "square":
        return square_path(size, inset=inset)
    if kind == "rounded":
        return rounded_square_path(size, r, inset=inset)
    if kind == "superellipse":
        return superellipse_path(cx=size / 2.0, cy=size / 2.0,
                                 a=size / 2.0, b=size / 2.0, n=n, inset=inset)
    if kind == "circle":
        return circle_path(size, inset=inset)
    raise SystemExit(f"未知外轮廓: {kind}（应为 square | rounded | superellipse | circle）")


# ---------------- 读取源图白色螺旋 ----------------
def load_white(path=SRC_DEFAULT, crop=CROP_SRC):
    """
    读取源图，提取受约束的白色螺旋 mask。

    改进策略（v3 —— 解决 JPEG 碎片化问题）：
      1. 降低白色阈值到 RGB>175（捕获抗锯齿边缘像素，保持连通性）
      2. 排除画布纯白（RGB>245）
      3. 红色 mask 吸收（约束在红方块内）
      4. 只保留最大连通分量（丢弃 JPEG 噪声碎点 → 从 98 域降到 1）
      5. 轻度闭运算 r=2（桥接 ≤4px 的微小缝隙）
      6. 不做 erosion（最大连通分量已干净，erosion 会重新打碎）
    """
    from scipy import ndimage as _nd
    im = Image.open(path).convert("RGB")
    a = np.array(im).astype(int)
    crop_arr = a[crop[0]:crop[1], crop[2]:crop[3]].astype("uint8")
    H, W, _ = crop_arr.shape
    ai = a[crop[0]:crop[1], crop[2]:crop[3]]
    R, G, B = ai[:, :, 0], ai[:, :, 1], ai[:, :, 2]
    # 1) 白色候选：降低阈值捕获抗锯齿边缘（原 >200 太严格，JPEG 碎片化）
    white_raw = (R > 175) & (G > 175) & (B > 175)
    # 2) 排除画布纯白
    canvas = (R > 245) & (G > 245) & (B > 245)
    white = white_raw & ~canvas
    # 3) 红色方块 mask 吸收：螺旋必须落在红色方块内
    red_str = (R > 170) & (G < 140) & (B < 140) & (R > G) & (R > B)
    red_square = red_str | white
    red_square_filled = _nd.binary_fill_holes(red_square)
    red_square_dilated = _nd.binary_dilation(red_square_filled, iterations=1)
    white = white & red_square_dilated
    # 4) 预闭运算：先桥接 JPEG 打碎的螺旋碎片（r=4 在源空间填 ≤8px 缝隙）
    #    这一步必须在连通分量分析之前！否则内圈细线会被当噪声丢弃
    pre_close_r = 4
    yy, xx = np.ogrid[-pre_close_r:pre_close_r + 1, -pre_close_r:pre_close_r + 1]
    disk_pre = (xx * xx + yy * yy <= pre_close_r * pre_close_r).astype(int)
    white = _nd.binary_closing(white, structure=disk_pre, iterations=1)
    # 5) 只保留最大连通分量（螺旋主体，丢弃残留噪声碎点）
    labeled, ncomp = _nd.label(white)
    if ncomp > 1:
        component_sizes = _nd.sum(white, labeled, range(1, ncomp + 1))
        largest_label = int(np.argmax(component_sizes)) + 1
        white = labeled == largest_label
    # 计算质心
    ys, xs = np.where(white)
    cx_src = float(xs.mean()) if len(xs) else W / 2.0
    cy_src = float(ys.mean()) if len(ys) else H / 2.0
    return crop_arr, white, H, W, (cx_src, cy_src)


# ---------------- banded 模式：骨架化中心线 → SVG stroke ----------------
def spiral_banded_path(white, H, W, cx=None, cy=None,
                       pitch=62.0, mod_amp=0.0,
                       upsample=4, tol=0.6, smooth=5):
    """
    提取白色螺旋带的**骨架（中心线）**，返回 SVG path 数据。
    渲染时用 fill="none" stroke + stroke-width 控制带宽，与目标图一致。

    流程：白带 mask → 骨架化(1px) → 去短枝 → 超采样平滑 →
          find_contours → 滑动平均 → approximate_polygon → 坐标映射。
    """
    if cx is None:
        cx = W / 2.0
    if cy is None:
        cy = H / 2.0
    from skimage.morphology import skeletonize as _skeletonize
    from PIL import Image as _I
    from scipy import ndimage as _nd

    # 1) 骨架化：白带 → 1px 中心线
    skel = _skeletonize(white.astype(uint8_if_available_or_bool()))

    # 2) 去短枝：删除长度 < branch_min 的分支（抗锯齿/噪声产生的小毛刺）
    branch_min = max(4, int(0.02 * max(H, W)))  # 源空间 ~4px
    skel = _prune_skeleton(skel, min_length=branch_min)

    # 3) 超采样 + 轻量闭运算（骨架是 1px，上采样后可能断开）
    big = _I.fromarray((skel.astype("uint8") * 255)).resize(
        (W * upsample, H * upsample), _I.NEAREST)
    skel_up = np.array(big) > 127
    cr = 1
    yy, xx = np.ogrid[-cr:cr + 1, -cr:cr + 1]
    disk = (xx * xx + yy * yy <= cr * cr).astype(int)
    skel_up = _nd.binary_closing(skel_up, structure=disk, iterations=1)

    # 4) 轮廓提取（骨架是线，find_contours 会给出细长轮廓）
    cs = find_contours(skel_up.astype(float), 0.5)
    cs = sorted(cs, key=len, reverse=True)

    sub = []
    for c in cs:
        if len(c) < 10:
            continue
        if smooth > 0:
            k = smooth
            pad = np.pad(c, ((k, k), (0, 0)), mode="edge")
            c = np.array([pad[i - k:i + k + 1].mean(0) for i in range(k, len(pad) - k)])
        c = approximate_polygon(c, tol)
        if len(c) <= 8:
            continue
        seg = ("M " + " L ".join(
            f"{(256 + (x[1] / upsample - cx) * SC):.2f},"
            f"{(256 + (x[0] / upsample - cy) * SC):.2f}" for x in c
        ))
        sub.append(seg)
    return " ".join(sub)


# ---------------- log 模式：几何对数螺旋（等角螺旋） ----------------
def spiral_logarithmic_path(cx, cy, a, b, theta_end, theta_offset,
                            steps=720, inner_turns=0.0):
    """
    生成几何对数螺旋（等角螺旋）SVG path 数据。

    方程：  r(θ) = a · e^(b·θ)      （θ 从 0 到 theta_end）
    点：    x = cx + r·cos(θ+φ₀),  y = cy − r·sin(θ+φ₀)   （SVG y 轴向下，故取负）

    参数：
      a            : 起始半径（最内圈）
      b            : 增长率（决定每圈扩张比例，b 越小越松）
      theta_end    : 总扫描角（= 2π·N，N 为圈数）
      theta_offset : 整体相位偏移，使破口（θ=theta_end 的最外点）落在指定方向
      inner_turns  : 起点相位（让内圈从某角度起笔，默认 0）

    破口方向：最外点角度 = theta_end + theta_offset，
              设为 breakout_deg 即可把破口放到目标方向（如 108° = 11点稍左）。
    """
    pts = []
    t0 = inner_turns * 2.0 * math.pi
    span = theta_end - t0
    for i in range(steps + 1):
        t = t0 + span * i / steps
        r = a * math.exp(b * t)
        ang = t + theta_offset
        x = cx + r * math.cos(ang)
        y = cy - r * math.sin(ang)
        pts.append((x, y))
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)


def generate_log(out, cx=256.0, cy=256.0, a=42.0, b=0.109, turns=2.5,
                 breakout_deg=108.0, stroke=24.0, rotate=0.0,
                 outline="square", red=RED, white=WHITE):
    """
    几何对数螺旋生成器（推荐模式）。
    破口方向由 breakout_deg 控制；rotate 仅作微调（一般 0）。
    """
    theta_end = 2.0 * math.pi * turns
    # 最外点角度 = theta_end + theta_offset，要等于 breakout_deg（弧度）
    theta_offset = math.radians(breakout_deg) - theta_end
    d_spi = spiral_logarithmic_path(cx, cy, a, b, theta_end, theta_offset, steps=720)
    svg = build_svg("banded", d_spi, red=red, white=white, width=stroke,
                    rotate=rotate, outline=outline)
    with open(out, "w") as f:
        f.write(svg)
    return svg


# ---------------- trace 模式：高保真描摹目标图 ----------------
TARGET_IMG = os.path.join(os.path.dirname(__file__), "assets", "4768.jpg")


def load_target_white(margin=35):
    """
    从目标图 4768.jpg 提取白色螺旋 mask。
    在红方块四周保留 margin 像素的边距，使突破红边的白色不被截断。
    返回：(white_mask_512x512, H=512, W=512, cx, cy) — 已映射到 512 画布。
    """
    from scipy import ndimage as _nd
    im = Image.open(TARGET_IMG).convert("RGB")
    arr = np.array(im).astype(int)
    H_img, W_img = arr.shape[:2]
    R, G, B = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # 红方块检测
    red = (R > 170) & (G < 150) & (B < 150) & (R > G) & (R > B)
    ry, rx = np.where(red)
    if len(rx) == 0:
        raise SystemExit("目标图 4768.jpg 中未找到红色方块")
    y0, y1, x0, x1 = ry.min(), ry.max(), rx.min(), rx.max()
    red_h, red_w = y1 - y0 + 1, x1 - x0 + 1

    # 扩大裁切范围：红方块 + margin 边距（保留突破红边的白色）
    my0 = max(0, y0 - margin)
    my1 = min(H_img, y1 + margin)
    mx0 = max(0, x0 - margin)
    mx1 = min(W_img, x1 + margin)
    cr = arr[my0:my1 + 1, mx0:mx1 + 1].astype("uint8")
    R2, G2, B2 = cr[:, :, 0], cr[:, :, 1], cr[:, :, 2]

    # 白色螺旋带：三通道都较亮（米白/近白）
    white_raw = (R2 > 190) & (G2 > 190) & (B2 > 190)

    # 排除纯红区（红色本身 R 也高，但 G/B 低）
    not_red = ~((R2 > 180) & (G2 < 140) & (B2 < 140))
    white = white_raw & not_red

    # 形态学清理：轻闭运算桥接 JPEG 缝隙 + 最大连通分量
    yy, xx = np.ogrid[-3:4, -3:4]
    disk3 = (xx * xx + yy * yy <= 9).astype(int)
    white = _nd.binary_closing(white, structure=disk3, iterations=1)

    labeled, ncomp = _nd.label(white)
    if ncomp > 1:
        sizes = _nd.sum(white, labeled, range(1, ncomp + 1))
        largest = int(np.argmax(sizes)) + 1
        white = labeled == largest

    # 扩大后的裁切区域整体缩放到 512x512（红方块会略小于满画布，白线可越出红边）
    big = Image.fromarray((white.astype(np.uint8) * 255), mode="L").resize(
        (512, 512), Image.LANCZOS)
    white_512 = np.array(big) > 127

    ys, xs = np.where(white_512)
    cx = float(xs.mean()) if len(xs) else 256.0
    cy = float(ys.mean()) if len(ys) else 256.0

    return white_512, 512, 512, cx, cy


def _polyline_to_bezier(points, closed=True, tension=0.5):
    """
    将折线点列转换为 Catmull-Rom 样条 → 三次贝塞尔曲线（SVG C 指令）。
    输出任意缩放都光滑，消除放大时的"毛刺/折角"。
    tension: 标量或逐点数组（与原始点等长）。越大曲线在途经点处越圆润
      （对应优化建议 1：中心涡卷高曲率处自动加大张力，气眼更圆润）。

    points: (N, 2) 数组，[[row, col], ...]（skimage 坐标系）
    返回: SVG path d 字符串（含 M/C/Z）
    """
    n = len(points)
    if n < 4:
        # 点太少，退化为折线
        seg = "M " + " L ".join(f"{p[1]:.2f},{p[0]:.2f}" for p in points)
        return seg + (" Z" if closed else "")

    pts = list(points)
    if closed:
        # 闭合环：首尾各补一点使样条平滑过渡
        pts = [pts[-2]] + pts + [pts[1], pts[2]]
    else:
        pts = [pts[0]] + pts + [pts[-1]]

    # tension 对齐：标量则全同；数组则与原始点等长后按 pts 补位
    tens = np.atleast_1d(np.asarray(tension, dtype=float))
    if tens.size == 1:
        pad_tens = [float(tens[0])] * len(pts)
    else:
        pad_tens = [tens[-2]] + list(tens) + [tens[1], tens[2]]

    d = []
    for i in range(1, len(pts) - 2):
        p0 = np.asarray(pts[i - 1], dtype=float)
        p1 = np.asarray(pts[i],     dtype=float)
        p2 = np.asarray(pts[i + 1], dtype=float)
        p3 = np.asarray(pts[i + 2], dtype=float)

        t = pad_tens[i]
        # Catmull-Rom 控制点 → 三次贝塞尔
        cp1 = p1 + (p2 - p0) * t / 6.0
        cp2 = p2 - (p3 - p1) * t / 6.0

        if i == 1:
            d.append(f"M {p1[1]:.2f},{p1[0]:.2f}")
        d.append(f"C {cp1[1]:.2f},{cp1[0]:.2f} {cp2[1]:.2f},{cp2[0]:.2f} {p2[1]:.2f},{p2[0]:.2f}")

    if closed:
        d.append("Z")
    return " ".join(d)


def resample_even_arclen(c, n):
    """把闭合轮廓重采样为 n 个等弧长间隔的点（消除采样密度不均带来的高频抖动）。"""
    d = np.sqrt(((c[1:] - c[:-1]) ** 2).sum(1))
    d = np.concatenate([[0.0], np.cumsum(d)])
    total = d[-1]
    new_d = np.linspace(0, total, n, endpoint=False)
    fx = np.interp(new_d, d, c[:, 0])
    fy = np.interp(new_d, d, c[:, 1])
    return np.column_stack([fx, fy])


def round_tail_tip(mask, cap_rows=5, cap_radius=None, truncate=True):
    """
    把白色螺旋最顶端（破口尾巴）的截面做成圆润截断面（圆形 Cap，对应优化建议 3）。

    设计原则（与用户"鹦鹉螺壳口自然圆润截断面"一致）：
      - 不收细（保持丝带自身厚度），只把顶端细尖换成与丝带等宽的半圆 Cap；
      - Cap 半径 = 截断处丝带的真实半宽，使圆口与丝带平滑衔接、不鼓包、不尖刺。

    为何用 EDT 而非列跨度：白色螺旋是对数带，同一水平行在下行后会穿过螺旋多圈臂，
    列跨度会被严重夸大（误测成 90px）。距离变换 EDT 取"白点到最近背景的垂直距离"，
    才是丝带真实半宽（顶端实测仅 1~6px）。

    参数：
      mask      : 512×512 白色布尔掩码（已含破口尾巴）
      cap_rows  : 自最顶端向下多少行作为"截断/封口"位置（默认 5，落在单臂干净截面）
      cap_radius: 强制指定 Cap 半径(px)；None 时取截断处 EDT 真实半宽
      truncate  : True 截掉上方细尖再封口（干净壳口）；False 仅在顶端叠加半圆（保留细尖）
    """
    from scipy import ndimage as _nd
    H, W = mask.shape
    ys = np.where(mask)[0]
    if len(ys) == 0:
        return mask
    ty = int(ys.min())                          # 最顶端白行
    edt = _nd.distance_transform_edt(mask)      # 真实局部半宽场
    r_cut = min(ty + cap_rows, H - 1)
    row_edt = edt[r_cut]
    if not mask[r_cut].any():
        return mask
    cc = float(np.argmax(row_edt))              # EDT 最大处 = 丝带中轴列（单臂时准确）
    R = float(cap_radius) if cap_radius is not None else float(row_edt.max())
    if R < 2:
        return mask
    if truncate:
        mask[ty:r_cut, :] = False               # 截掉上方细尖
    # 以 (cc, r_cut) 为圆心、R 为半径，向画布上方雕出半圆 Cap
    r_top = max(0, int(round(r_cut - R)))
    for r in range(r_top, r_cut + 1):
        d = r - r_cut                           # ∈ [-R, 0]
        hw = int(round(np.sqrt(max(0.0, R * R - d * d))))
        lo = int(np.floor(cc - hw)); hi = int(np.ceil(cc + hw))
        mask[r, max(0, lo):min(W, hi + 1)] = True
    return mask


def _turning_per_point(c):
    """闭合点列逐点局部转角（度）。"""
    n = len(c)
    out = np.zeros(n)
    for i in range(n):
        p0, p1, p2 = c[(i - 1) % n], c[i], c[(i + 1) % n]
        a = np.arctan2(p1[0] - p0[0], p1[1] - p0[1])
        b = np.arctan2(p2[0] - p1[0], p2[1] - p1[1])
        out[i] = np.degrees(abs((a - b + np.pi) % (2 * np.pi) - np.pi))
    return out


def spiral_trace_path(white, H, W, cx=None, cy=None,
                      upsample=10, tol=0.4, smooth=4, bezier=True, n_pts=1400,
                      tension_base=0.4, tension_center=0.9):
    """
    高保真描摹：白色 mask → 高倍超采样 → find_contours → 等弧长重采样 →
    一维高斯平滑（抹掉 JPEG 噪声与栅格阶梯，得到数学上光滑的曲线）→ 贝塞尔。
    smooth = 高斯 sigma（按重采样点序列索引），越大越光滑、形状略圆润。
    """
    if cx is None:
        cx = W / 2.0
    if cy is None:
        cy = H / 2.0
    from PIL import Image as _I
    from scipy import ndimage as _nd

    # 超采样（LANCZOS 抗锯齿）
    big = _I.fromarray((white.astype("uint8") * 255)).resize(
        (W * upsample, H * upsample), Image.LANCZOS)
    white_up = np.array(big) > 127

    # 轻量形态学清理（仅用于连通性/桥接，不参与描摹边界）
    yy, xx = np.ogrid[-3:4, -3:4]
    disk3 = (xx * xx + yy * yy <= 9).astype(int)
    white_up = _nd.binary_closing(white_up, structure=disk3, iterations=1)
    labeled, ncomp = _nd.label(white_up)
    if ncomp > 1:
        sizes = _nd.sum(white_up, labeled, range(1, ncomp + 1))
        white_up = labeled == (int(np.argmax(sizes)) + 1)

    # find_contours 提取轮廓（在二值上取 0.5 等值线）
    cs = find_contours(white_up.astype(float), 0.5)
    cs = sorted(cs, key=len, reverse=True)

    sub = []
    for c in cs:
        if len(c) <= 10:
            continue
        # 1) 等弧长重采样：把不均匀的 marching-squares 点拉成均匀序列
        c = resample_even_arclen(c, n_pts)
        # 2) 一维高斯平滑（闭合 wrap）：数学上压平高频抖动，边缘绝对光滑
        if smooth > 0:
            c[:, 0] = _nd.gaussian_filter1d(c[:, 0], smooth, mode="wrap")
            c[:, 1] = _nd.gaussian_filter1d(c[:, 1], smooth, mode="wrap")
        c = approximate_polygon(c, tol)
        if len(c) <= 10:
            continue
        # 映射到 512 画布坐标
        pts_512 = np.column_stack([c[:, 0] / upsample, c[:, 1] / upsample])
        if bezier:
            # 曲率自适应张力（优化建议 1）：基础张力保持已审定的 0.4，
            # 仅中心涡卷等高曲率处平滑拉升至 tension_center，使气眼更圆润、闭合感更好；
            # 其余低曲率段保持原貌，不改动已确认的整体调性。
            turn = _turning_per_point(pts_512)
            tmin, tmax = float(turn.min()), float(turn.max())
            if tmax - tmin > 1e-6:
                ref_lo, ref_hi = 6.0, 16.0   # 转角(°) <6 保持基础；>16 达中心张力
                norm = np.clip((turn - ref_lo) / (ref_hi - ref_lo), 0.0, 1.0)
                tens = tension_base + (tension_center - tension_base) * norm
            else:
                tens = tension_base
            seg = _polyline_to_bezier(pts_512, closed=True, tension=tens)
        else:
            seg = ("M " + " L ".join(
                f"{x[1]:.2f},{x[0]:.2f}" for x in pts_512
            ) + " Z")
        sub.append(seg)
    return " ".join(sub)


def generate_trace(out, upsample=10, tol=0.4, smooth=4,
                   outline="square", red=RED, white=WHITE, bezier=True,
                   inset=32.0, clip=False, center=True, center_nudge=3.0,
                   cap_tail=False, cap_rows=5, cap_radius=None, cap_truncate=True,
                   tension_base=0.4, tension_center=0.9, draw_red=True):
    """
    高保真描摹模式：直接从目标图 4768.jpg tracing 白色螺旋形状（鹦鹉螺对数螺旋）。
    bezier=True 时输出三次贝塞尔曲线（光滑无毛刺）。
    inset>0 时红框四周留透明边距。
    clip=True 时把白线裁切到红框形状内（白线贴合形状边界）。
      默认 clip=False：经验证仅上方破口溢出(~11px)，其他三边零溢出；关闭裁切让自然圆头露出
      （鹦鹉螺壳口自然生长感，避免被一刀切的生硬截面）。
    center=True 时把白线质心平移到画布中心，修正整体左偏。
    center_nudge>0 时在质心居中基础上再向右微调（px），用于光学平衡
      （螺旋起笔在左上、视觉重心偏左，右移抵消右侧过多留白，见优化建议 3）。
    cap_tail=True 时把顶端破口做成圆润壳口截断面（优化建议 3，圆形 Cap，不收细）。
    cap_rows/cap_radius/cap_truncate 见 round_tail_tip。
    tension_base/tension_center 见 spiral_trace_path（中心涡卷曲率自适应张力，优化建议 1）。
    """
    white_mask, H, W, cx, cy = load_target_white()
    if cap_tail:
        white_mask = round_tail_tip(white_mask, cap_rows=cap_rows,
                                    cap_radius=cap_radius, truncate=cap_truncate)
    d_spi = spiral_trace_path(white_mask, H, W, cx=cx, cy=cy,
                               upsample=upsample, tol=tol, smooth=smooth,
                               bezier=bezier,
                               tension_base=tension_base, tension_center=tension_center)
    d_out = outline_path(kind=outline, inset=inset)
    # 居中平移：
    #   - 水平：按白色螺旋「包围盒中心」居中（而非质心）。鹦鹉螺的"头"伸向右边，
    #     若按质心居中，白线左右外缘会整体右偏（实测包围盒中心较红形中心右偏 ~14.8px），
    #     表现为左留白远大于右留白。改为包围盒居中后左右间距相等。
    #   - 垂直：保持质心居中（未反馈问题，维持原状）。
    #   center_nudge 为水平微调（px，默认 0）：>0 右移 / <0 左移。
    _nums = re.findall(r'[-+]?\d*\.?\d+', d_spi)
    _coords = [float(v) for v in _nums]
    _bcx = (min(_coords[0::2]) + max(_coords[0::2])) / 2.0
    if center:
        dx = VIEWBOX / 2.0 + center_nudge - _bcx
        dy = VIEWBOX / 2.0 - cy
    else:
        dx = dy = 0.0
    if draw_red and clip:
        # A 版：红底 + 白线，白线严格裁切到红框形状边界内（边界处平头截断，不凸出）
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" '
                f'width="{VIEWBOX}" height="{VIEWBOX}">'
                f'<defs><clipPath id="shapeclip"><path d="{d_out}"/></clipPath></defs>'
                f'<path d="{d_out}" fill="{red}"/>'
                f'<g clip-path="url(#shapeclip)">'
                f'<g transform="translate({dx:.2f},{dy:.2f})">'
                f'<path d="{d_spi}" fill="{white}" fill-rule="nonzero"/>'
                f'</g></g>'
                f'</svg>')
    else:
        # 白线独立（B 版 draw_red=False：透明底纯白线；或 A 不裁切版）：不裁切，
        # 白线破口长出一截、由前端 CSS clip-path 在边界处裁平（见 B 方案）
        red_part = f'<path d="{d_out}" fill="{red}"/>' if draw_red else ''
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" '
                f'width="{VIEWBOX}" height="{VIEWBOX}">'
                f'{red_part}'
                f'<g transform="translate({dx:.2f},{dy:.2f})">'
                f'<path d="{d_spi}" fill="{white}" fill-rule="nonzero"/>'
                f'</g>'
                f'</svg>')
    with open(out, "w") as f:
        f.write(svg)
    return svg


def uint8_if_available_or_bool():
    """兼容不同 skimage 版本的 skeletonize dtype 要求。"""
    try:
        from skimage.morphology import skeletonize as _sk_test
        _sk_test(np.array([[True, False]]))
        return bool
    except Exception:
        return np.uint8


def _prune_skeleton(skel, min_length=4):
    """
    删除骨架上长度 < min_length 的短枝。
    算法：找端点（恰好 1 个邻居的像素）→ 追踪到分叉点 → 若路径长度不足则删除。
    """
    from scipy import ndimage as _nd
    arr = skel.copy()
    h, w = arr.shape
    # 8-邻域卷积核，计算每个骨架像素的邻居数
    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)
    padded = np.pad(arr, 1, mode='constant', constant_values=0)
    neighbor_count = _nd.convolve(padded, kernel, mode='constant')[1:h+1, 1:w+1]
    neighbor_count *= arr  # 只在骨架点上有效

    changed = True
    iterations = 0
    max_iter = 100  # 安全上限
    while changed and iterations < max_iter:
        changed = False
        iterations += 1
        # 找所有端点（恰好 1 个骨架邻居）
        endpoints = (arr > 0) & (neighbor_count == 1)
        ey, ex = np.where(endpoints)
        for i in range(len(ey)):
            y, x = ey[i], ex[i]
            # BFS 追踪到下一个分叉点或另一个端点
            visited = set()
            queue = [(y, x)]
            path = []
            while queue:
                cy_, cx_ = queue.pop(0)
                if (cy_, cx_) in visited:
                    continue
                visited.add((cy_, cx_))
                path.append((cy_, cx_))
                # 检查 8 邻居
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx_ = cy_ + dy, cx_ + dx
                        if 0 <= ny < h and 0 <= nx_ < w and arr[ny, nx_] > 0 and (ny, nx_) not in visited:
                            nc = int(neighbor_count[ny, nx_])
                            if nc >= 3:  # 分叉点，停止
                                break
                            queue.append((ny, nx_))
                    else:
                        continue
                    break
            # 删除短枝
            if min_length is not None and len(path) < min_length:
                for py, px in path:
                    if neighbor_count[py, px] <= 2:  # 不删分叉点本身
                        arr[py, px] = 0
                        changed = True
        # 更新邻居计数
        padded = np.pad(arr, 1, mode='constant', constant_values=0)
        neighbor_count = _nd.convolve(padded, kernel, mode='constant')[1:h+1, 1:w+1]
        neighbor_count *= arr

    return arr


# ---------------- filled 模式：bitmap 描摹（忠于原图） ----------------
def spiral_filled_path(crop, white, H, W, cx=None, cy=None,
                       upsample=6, tol=0.5, smooth=5, mask_open=2):
    """
    忠实复刻原图白色螺旋（保留原图圈数、带宽、形状）：
      用 load_white 算好的【受约束白色 mask】(红 icon 内部 ∩ 非红) 做超采样
      → 掩膜形态学开运算去刺 → find_contours(0.5) 子像素轮廓
      → 滑动平均平滑 → approximate_polygon 简化。
    注意：必须基于受约束 mask，而非原始 RGB 阈值，否则源图裁切区四角的
    画布纯白会被误判为螺旋，放大后落在方角形成白角。
    """
    if cx is None: cx = W / 2.0
    if cy is None: cy = H / 2.0
    from PIL import Image as _I
    from scipy import ndimage as _nd
    # 超采样【受约束】白色 mask（已排除画布背景白角）
    # 用 NEAREST 而非 BILINEAR：二值 mask 经双线性插值会稀释小碎片导致丢失
    big = _I.fromarray((white.astype("uint8") * 255)).resize(
        (W * upsample, H * upsample), _I.NEAREST)
    white_up = np.array(big) > 127
    if mask_open > 0:
        yy, xx = np.ogrid[-mask_open:mask_open + 1, -mask_open:mask_open + 1]
        st = (xx * xx + yy * yy <= mask_open * mask_open).astype(int)
        white_up = _nd.binary_opening(white_up, structure=st)
    # 形态学闭运算（超采样后轻量）：填上采样引入的亚像素间隙
    # 用 disk r=2（超采样空间）= 源空间 r≈0.33，几乎不增厚、消除白点伪影
    cr2 = 2
    yy, xx = np.ogrid[-cr2:cr2 + 1, -cr2:cr2 + 1]
    disk2 = (xx * xx + yy * yy <= cr2 * cr2).astype(int)
    white_up = _nd.binary_closing(white_up, structure=disk2, iterations=1)
    cs = find_contours(white_up.astype(float), 0.5)
    cs = sorted(cs, key=len, reverse=True)
    sub = []
    for c in cs:
        if smooth > 0:
            k = smooth
            pad = np.pad(c, ((k, k), (0, 0)), mode="edge")
            c = np.array([pad[i - k:i + k + 1].mean(0) for i in range(k, len(pad) - k)])
        c = approximate_polygon(c, tol)
        if len(c) <= 8:
            continue
        seg = ("M " + " L ".join(
            f"{(256 + (x[1] / upsample - cx) * SC):.2f},"
            f"{(256 + (x[0] / upsample - cy) * SC):.2f}" for x in c
        ) + " Z")
        sub.append(seg)
    return " ".join(sub)


# ---------------- 组装 SVG ----------------
def build_svg(mode, d_spi, red=RED, white=WHITE, width=40.0, rotate=0.0,
              outline="square"):
    """
    组装 SVG。
    rotate 仅作用于**白色螺旋 g**（不旋转红色 outline），让 V1 方向旋转到目标方向。
    """
    d_out = outline_path(kind=outline)
    rot_attr = f' transform="rotate({rotate:.1f} 256 256)"' if rotate else ""
    if mode == "banded":
        g = (f'<g clip-path="url(#icon)"{rot_attr}>'
             f'<path d="{d_spi}" fill="none" stroke="{white}" '
             f'stroke-width="{width:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
             f'</g>')
    else:
        g = (f'<g clip-path="url(#icon)"{rot_attr}>'
             f'<path d="{d_spi}" fill="{white}" fill-rule="evenodd"/>'
             f'</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" '
            f'width="{VIEWBOX}" height="{VIEWBOX}">'
            f'<defs><clipPath id="icon"><path d="{d_out}"/></clipPath></defs>'
            f'<path d="{d_out}" fill="{red}"/>'
            f'{g}</svg>')


def generate(mode, out, src=SRC_DEFAULT, width=40.0, pitch=62.0, rotate=SPIRAL_ROTATE,
             red=RED, white=WHITE, mod_amp=0.0, outline="square",
             upsample=10, tol=0.4, smooth=4, mask_open=2,
             # 几何螺旋参数
             a=36.0, b=0.120, turns=2.5, breakout_deg=108.0,
             # trace 模式参数
             bezier=True, inset=32.0, clip=False, center=True, center_nudge=3.0,
             cap_tail=False, cap_rows=5, cap_radius=None, cap_truncate=True,
             tension_base=0.4, tension_center=0.9, draw_red=True):
    if mode == "log":
        return generate_log(out, cx=256.0, cy=256.0, a=a, b=b, turns=turns,
                           breakout_deg=breakout_deg, stroke=width,
                           rotate=rotate, outline=outline, red=red, white=white)
    if mode == "trace":
        return generate_trace(out, upsample=upsample, tol=tol, smooth=smooth,
                              outline=outline, red=red, white=white,
                              bezier=bezier, inset=inset, clip=clip, center=center,
                              center_nudge=center_nudge,
                              cap_tail=cap_tail, cap_rows=cap_rows,
                              cap_radius=cap_radius, cap_truncate=cap_truncate,
                              tension_base=tension_base, tension_center=tension_center,
                              draw_red=draw_red)
    load_ret = load_white(src)
    crop, white_m, H, W = load_ret[0], load_ret[1], load_ret[2], load_ret[3]
    cx_src, cy_src = load_ret[4]
    if mode == "filled":
        d_spi = spiral_filled_path(crop, white_m, H, W,
                                   cx=cx_src, cy=cy_src,
                                   upsample=upsample, tol=tol, smooth=smooth,
                                   mask_open=mask_open)
    elif mode == "banded":
        d_spi = spiral_banded_path(white_m, H, W, pitch=pitch, mod_amp=mod_amp)
    else:
        raise SystemExit(f"未知模式: {mode}（应为 log | trace | filled | banded）")
    svg = build_svg(mode, d_spi, red=red, white=white, width=width,
                    rotate=rotate, outline=outline)
    with open(out, "w") as f:
        f.write(svg)
    return svg


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Logo 矢量生成器（默认几何对数螺旋）")
    ap.add_argument("--mode", default="trace", choices=["trace", "log", "filled", "banded"],
                    help="模式: trace(高保真描摹目标图,推荐) | log(几何对数螺旋) | filled(位图填充) | banded(位图描边)")
    ap.add_argument("--out", required=True)
    # 几何螺旋参数（仅 log 模式使用）
    ap.add_argument("--a", type=float, default=36.0, help="起始半径 (log 模式)")
    ap.add_argument("--b", type=float, default=0.120, help="增长率 (log 模式)")
    ap.add_argument("--turns", type=float, default=2.5, help="圈数 (log 模式)")
    ap.add_argument("--breakout", type=float, default=108.0, help="破口角度° (log 模式)")
    # 位图参数（filled/banded 使用）
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--outline", default="square",
                    choices=["square", "rounded", "superellipse", "circle"])
    ap.add_argument("--width", type=float, default=24.0, help="带宽/线宽")
    ap.add_argument("--pitch", type=float, default=62.0)
    ap.add_argument("--rotate", type=float, default=0.0)
    ap.add_argument("--mod", type=float, default=0.0)
    ap.add_argument("--upsample", type=int, default=10)
    ap.add_argument("--tol", type=float, default=0.4)
    ap.add_argument("--smooth", type=int, default=4,
                    help="轮廓一维高斯平滑 sigma（越大越光滑、形状略圆润）")
    ap.add_argument("--inset", type=float, default=32.0,
                    help="红框四周透明边距(px,512画布)")
    ap.add_argument("--clip", action="store_true",
                    help="开启形状裁切（默认关闭：仅上方破口溢出~11px，其他三边零溢出）")
    ap.add_argument("--no-center", action="store_true",
                    help="关闭白线质心居中（调试对比用）")
    ap.add_argument("--center-nudge", type=float, default=0.0,
                    help="白线水平居中后再微调的像素量（光学平衡，建议 -6~6；0=仅包围盒居中）")
    ap.add_argument("--bezier", action="store_true", default=True,
                    help="trace 模式使用贝塞尔曲线平滑（默认开启，关闭后为折线）")
    ap.add_argument("--no-bezier", action="store_true",
                    help="关闭贝塞尔曲线，输出折线（用于对比调试）")
    ap.add_argument("--mask-open", type=int, default=2)
    ap.add_argument("--cap-rows", type=int, default=5,
                    help="圆角壳口：自顶端向下截断行数（仅 trace 模式生效）")
    ap.add_argument("--cap-radius", type=float, default=None,
                    help="圆角壳口：强制 Cap 半径(px)；缺省取截断处丝带真实半宽")
    ap.add_argument("--cap", action="store_true",
                    help="开启顶端圆角壳口（默认关闭：平头截断，边界一刀切平）")
    ap.add_argument("--no-red", action="store_true",
                    help="关闭红色底，仅输出透明底纯白线（B 版，等价于 draw_red=False）")
    ap.add_argument("--no-cap-truncate", action="store_true",
                    help="圆角壳口不截断细尖，仅在顶端叠加半圆")
    ap.add_argument("--tension-center", type=float, default=0.9,
                    help="中心涡卷曲率自适应张力上限（基础 0.4，中心升至该值，建议 0.7~1.0）")
    ap.add_argument("--red", default=RED)
    ap.add_argument("--white", default=WHITE)
    a = ap.parse_args()
    generate(a.mode, a.out, src=a.src, width=a.width, pitch=a.pitch,
             rotate=a.rotate, red=a.red, white=a.white, mod_amp=a.mod,
             outline=a.outline, upsample=a.upsample, tol=a.tol,
             smooth=a.smooth, mask_open=a.mask_open,
             a=a.a, b=a.b, turns=a.turns, breakout_deg=a.breakout,
             bezier=not getattr(a, 'no_bezier', False), inset=a.inset,
             clip=getattr(a, 'clip', False),
             center=not getattr(a, 'no_center', False),
             center_nudge=getattr(a, 'center_nudge', 3.0),
             cap_tail=getattr(a, 'cap', False),
             cap_rows=a.cap_rows,
             cap_radius=a.cap_radius,
             cap_truncate=not getattr(a, 'no_cap_truncate', False),
             tension_base=0.4,
             tension_center=a.tension_center,
             draw_red=not getattr(a, 'no_red', False))
    print(f"已生成 -> {a.out}  (mode={a.mode}, outline={a.outline})")
