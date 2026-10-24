# -*- coding: utf-8 -*-
"""
Mi Sans 首屏子集化脚本（多多贝 应用站字体资产）。

用途：从本地官方 MiSans 母本（woff2 分包）裁剪出前端首屏子集 woff2，
产物入库 frontend/public/fonts/，由 EdgeOne/Cloudflare/Vercel 分发（自托管）。

字表策略（首屏子集）：
  1. GBK 汉字全集（20,902 个，含 GB2312 一级 / 二级 / 扩展区）；
  2. frontend/src 源码实际用到的 CJK 字符（扫描补全，覆盖业务特有字）；
  3. 常用全角标点 / 符号（CJK 符号区 + 全角 ASCII 区）；
半角数字 / 拉丁字母由 Inter（latin 子集）承担，不落入本子集。

为什么从「GB2312 一级」扩到「GBK 全集」（#2402 / CNB #640）
-----------------------------------------------------------
首版字表只取了 GB2312 **一级**（3755 个），于是「荃」「鑫」这类**名字用字**全部缺失
（用户截图实测渲染不良）。当时的判断是「生僻字属可接受长尾」——这个判断是错的：

- GB2312 二级的 3008 个字**不是**低频字表，它按**笔画**排序，装的是姓氏 / 人名 /
  地名用字（亓、仉、芮、覃、邬、睢……），恰好是**用户昵称 / 自选备注 / 账户名 /
  导入文件名**每天都要碰到的那一批；
- 而且用户举的例子有**一半连二级都不在**：实测 `犇 喆 堃 赟 燚 彧 玊` 七个字
  不在 GB2312 任何一级里（它们属 GBK 扩展区）。只补二级，这张卡一半的验收仍不达标。
- 这不是「工具按字频裁掉了」，是**字表边界画错了**——工具没做判断，它只是没往上看。

所以直接以 **GBK 汉字全集**为边界：它是当前中文环境的事实可用字符集（与 Windows
中文代码页 936 一致），也是「用户可能输入什么」的合理上界。

代价要说清楚：字表 3755 → 20,902（5.6 倍），按实测 ~150 B/字估算单字重约 2.8 MB，
首屏 preload 的 400 直接翻数倍。**因此伴生体积治理由 `cn-font-split` 分片承担**
（见 docs/design/font-design.md §11.2），本脚本只负责「字表不缺字」这一半。
这个交换的账必须记在 PR 里，不许默默合并。

判据：`scripts/guard_font_glyph_coverage.py`（GBK 覆盖 ≥ 98%，且 GB2312 一级必须 100%）。

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
    """生成 GB2312 一级汉字（区 16~55，3755 个常用字，按拼音排序）。"""
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


def gbk_hanzi_chars() -> set[str]:
    """生成 GBK 汉字全集（20,902 个，含 GB2312 一级 / 二级 / 扩展区）。

    GBK 双字节区：首字节 0x81~0xFE，次字节 0x40~0xFE（跳过 0x7F）。解码为单字符
    且落在 CJK 统一表意区（U+4E00~U+9FFF）的即是汉字。
    """
    chars: set[str] = set()
    for hi in range(0x81, 0xFF):
        for lo in range(0x40, 0xFF):
            if lo == 0x7F:
                continue
            try:
                ch = bytes([hi, lo]).decode('gbk')
            except UnicodeDecodeError:
                continue
            if len(ch) == 1 and 0x4E00 <= ord(ch) <= 0x9FFF:
                chars.add(ch)
    return chars


def gb2312_level2_chars() -> set[str]:
    """生成 GB2312 二级汉字（区 56~87，3008 个，按笔画排序）。

    这批是**姓氏 / 人名 / 地名用字**（荃、鑫、淼、犇、喆、堃、赟、燚…），
    不是低频长尾——详见模块 docstring。区 56 起始字节 0xD8，到 0xF7 结束。
    """
    chars: set[str] = set()
    for hi in range(0xD8, 0xF8):  # 0xD8A1 ~ 0xF7FE
        for lo in range(0xA1, 0xFF):
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
    chars = gbk_hanzi_chars() | scan_frontend_chars() | extra_symbols()
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
    # 仅保留中文排版所需 GPOS 特性，避免 layout_features=['*'] 与 drop GSUB 自相矛盾
    # （GSUB 承载的复杂换形中文界面用不到；'*' 会把 GSUB/GPOS 全特性引入，放大产物）
    options.layout_features = ['kern', 'mark', 'mkmk']
    options.drop_tables += ['GSUB']
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
    try:
        font.save(str(out_path))
    finally:
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

    # 校验母本覆盖字表（缺字提醒，不阻断；母本缺失则跳过校验，与 subset_one 跳过逻辑一致）
    probe_path = SOURCE_DIR / 'MiSans-Regular.woff2'
    if probe_path.exists():
        probe = TTFont(str(probe_path))
        try:
            cmap = probe.getBestCmap()
            missing = [ch for ch in charset if ord(ch) not in cmap]
            if missing:
                print(f'[warn] 母本缺字 {len(missing)} 个（将回退系统字体）：{"".join(missing[:50])}')
        finally:
            probe.close()
    else:
        print(f'[warn] 母本缺失，跳过缺字校验: {probe_path}')

    for src_name, out_name in WEIGHTS:
        subset_one(src_name, out_name, charset)
    print('[done] 子集产物输出至', OUT_DIR)


if __name__ == '__main__':
    main()
