# -*- coding: utf-8 -*-
"""
Mi Sans 首屏子集化脚本（多多贝 应用站字体资产）。

用途：从本地官方 MiSans 母本（woff2 分包）裁剪出前端首屏子集 woff2，
产物入库 frontend/public/fonts/，由 EdgeOne/Cloudflare/Vercel 分发（自托管）。

字表策略（首屏子集）：
  1. GB2312 一级汉字（3755 个，覆盖常见界面文案与用户动态内容大头）；
  2. frontend/src 源码实际用到的 CJK 字符（扫描补全，覆盖业务特有字）；
  3. 常用全角标点 / 符号（CJK 符号区 + 全角 ASCII 区）；
半角数字 / 拉丁字母由 Inter（latin 子集）承担，不落入本子集。

授权说明：MiSans 全球免费商用；嵌入式使用需在产品内注明「使用了 MiSans 字体」。
子集化属「使用」而非对字体外观进行更改，合规（font-design.md §6 / §11）。

用法（须在 backend 下执行，依赖 fonttools + brotli）：
    pdm run python scripts/subset_misans.py
"""

from __future__ import annotations

from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

REPO_ROOT = Path(__file__).resolve().parents[2]  # d:/codes/fundmate
SOURCE_DIR = Path(r'D:\MiSans\MiSans\woff2')  # 本地官方母本
OUT_DIR = REPO_ROOT / 'frontend' / 'public' / 'fonts'
FRONTEND_SRC = REPO_ROOT / 'frontend' / 'src'

# 目标字重（覆盖 90%+ 场景，见 font-design.md §10-2）
WEIGHTS = [
    ('MiSans-Regular.woff2', 'misans-subset-400.woff2'),
    ('MiSans-Medium.woff2', 'misans-subset-500.woff2'),
    ('MiSans-Semibold.woff2', 'misans-subset-600.woff2'),
    ('MiSans-Bold.woff2', 'misans-subset-700.woff2'),
]


def gb2312_level1_chars() -> set[str]:
    """生成 GB2312 一级汉字（区 16~55，3755 个常用字）。"""
    chars: set[str] = set()
    for hi in range(0xB0, 0xD8):  # 0xB0A1 ~ 0xD7F9
        for lo in range(0xA1, 0xFF):
            if hi == 0xD7 and lo > 0xF9:
                break
            try:
                chars.add(bytes([hi, lo]).decode('gb2312'))
            except UnicodeDecodeError:
                continue
    return chars


def scan_frontend_chars() -> set[str]:
    """扫描 frontend/src 下源码实际用到的 CJK 字符与全角符号。"""
    chars: set[str] = set()
    exts = {'.vue', '.ts', '.tsx', '.js', '.scss', '.css', '.json'}
    for p in FRONTEND_SRC.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for ch in text:
            o = ord(ch)
            if (
                0x4E00 <= o <= 0x9FFF
                or 0x3400 <= o <= 0x4DBF
                or 0xF900 <= o <= 0xFAFF
                or 0x3000 <= o <= 0x303F
                or 0xFF01 <= o <= 0xFF60
                or 0xFFE0 <= o <= 0xFFE6
            ):
                chars.add(ch)
    return chars


def extra_symbols() -> set[str]:
    """补齐常用全角标点 / 符号（与源码扫描互补，防漏）。"""
    return set('，。、；：？！…—·《》「」『』【】（）￥％×÷°℃%＋－＝　“”‘’·—…·①②③④⑤⑥⑦⑧⑨⑩√')


def build_charset() -> str:
    chars = gb2312_level1_chars() | scan_frontend_chars() | extra_symbols()
    # 排序稳定输出，便于 diff / 复现
    return ''.join(sorted(chars))


def subset_one(src_name: str, out_name: str, charset: str) -> None:
    """使用 fontTools API 裁剪单个字重（避免 CLI 参数在 Windows 盘符下的解析问题）。"""
    src = SOURCE_DIR / src_name
    if not src.exists():
        print(f'[skip] 源文件缺失: {src}')
        return
    print(f'[run] {src_name} -> {out_name}')
    font = TTFont(str(src), recalcBBoxes=False, recalcTimestamp=False)
    options = Options()
    options.flavor = 'woff2'
    options.text = charset
    options.layout_features = ['*']  # 保留 kern/mark 等排版特性
    options.drop_tables += ['GSUB']  # 中文界面一般无需复杂 GSUB 换形
    options.hinting = False  # 减小体积（屏幕渲染可接受）
    options.desubroutinize = True
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.name_IDs = ['*']
    subsetter = Subsetter(options=options)
    subsetter.populate(text=charset)
    subsetter.subset(font)
    out_path = OUT_DIR / out_name
    font.save(str(out_path))
    font.close()
    size = out_path.stat().st_size
    print(f'  -> {out_name}: {size / 1024:.1f} KB')


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    charset = build_charset()
    # 字表快照存脚本旁（可复现/审计用），不发布进 public
    charset_file = Path(__file__).with_name('misans-subset-charset.txt')
    charset_file.write_text(charset, encoding='utf-8')
    print(f'[charset] {len(charset)} chars -> {charset_file.name}')

    # 校验母本覆盖字表（缺字提醒，不阻断）
    probe = TTFont(str(SOURCE_DIR / 'MiSans-Regular.woff2'))
    cmap = probe.getBestCmap()
    missing = [ch for ch in charset if ord(ch) not in cmap]
    if missing:
        print(f'[warn] 母本缺字 {len(missing)} 个（将回退系统字体）：{"".join(missing[:50])}')
    probe.close()

    for src_name, out_name in WEIGHTS:
        subset_one(src_name, out_name, charset)
    print('[done] 子集产物输出至', OUT_DIR)


if __name__ == '__main__':
    main()
