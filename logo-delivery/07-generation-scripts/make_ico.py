#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_ico.py — 生成多尺寸 favicon.ico（带透明通道）

产物（与最终两版 favicon 对应）：
  favicon.ico          <- Form 4 生产版基准（logo_favicon 红白红三层）
  favicon_form1r.ico    <- Form 1R 备选（红螺带透明底）

目标尺寸：16 / 32 / 48 / 64 px（Windows / macOS / 浏览器通用，均含透明）

渲染后端与说明：
  1. cairosvg 将 SVG 栅格化为 256px 高清 PNG（透明底），保证矢量精度。
  2. ImageMagick `convert` 用 -define icon:auto-resize=16,32,48,64
     把单张高清 PNG 下采样为多尺寸 ICO —— 这一步绕开了本环境 Pillow
     构建里被裁剪掉的 ICO 写编码器（Image.SAVE 为空）。

运行：
  python3 make_ico.py
依赖：cairosvg、ImageMagick（convert 在 PATH 中）
"""
import io
import os
import subprocess
import sys

import cairosvg

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "05-favicon")  # logo-delivery/05-favicon
SIZES = [16, 32, 48, 64]
HIRES = 256  # 先出高清 PNG，再下采样，避免直接缩放 SVG 的精度损失


def _need_convert():
    """确认 ImageMagick convert 可用。"""
    try:
        subprocess.run(["convert", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def make_ico(src_svg, out_ico):
    """从 SVG 生成多尺寸 .ico（透明通道）。"""
    os.makedirs(os.path.dirname(out_ico), exist_ok=True)

    # ① cairosvg 渲染高清透明 PNG
    png_bytes = cairosvg.svg2png(
        url=src_svg,
        output_width=HIRES,
        output_height=HIRES,
        background_color="rgba(0,0,0,0)",
    )

    if not _need_convert():
        raise RuntimeError("未找到 ImageMagick `convert`，无法合成 ICO。请安装 imagemagick。")

    # ② convert 下采样为含多尺寸的 ICO
    cmd = [
        "convert", "-",
        "-background", "none",
        "-define", "icon:auto-resize=" + ",".join(str(s) for s in SIZES),
        out_ico,
    ]
    proc = subprocess.run(cmd, input=png_bytes, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"convert 失败: {proc.stderr.decode('utf-8', 'ignore')}")

    # ③ 校验：用 identify 列出 ICO 内嵌尺寸
    verify = subprocess.run(
        ["identify", out_ico], capture_output=True, text=True
    )
    print(f"{os.path.basename(out_ico)}: {verify.stdout.strip().replace(chr(10), ' | ')}")


if __name__ == "__main__":
    src_form4 = os.path.join(OUT, "logo_favicon.svg")
    src_form1r = os.path.join(OUT, "form1_red.svg")

    # 兜底：若 05-favicon 下没有 logo_favicon.svg（命名差异），则尝试 form4.svg
    if not os.path.exists(src_form4):
        alt = os.path.join(OUT, "form4.svg")
        if os.path.exists(alt):
            src_form4 = alt

    print("生成多尺寸 favicon.ico ...")
    make_ico(src_form4, os.path.join(OUT, "favicon.ico"))        # Form 4 生产版
    make_ico(src_form1r, os.path.join(OUT, "favicon_form1r.ico"))  # Form 1R 备选
    print("完成。")
