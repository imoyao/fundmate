#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：入库的 MiSans 子集必须真的覆盖「GB2312 一级 + 二级」，不许悄悄退回一级。

WHY（源 GitHub imoyao/fundmate#2402，CNB 镜像卡见 cnb.cool/duoduobei/fundmate/-/issues/640）
----------------------------------------------------
用户截图报「荃」「鑫」渲染不对。卡面把原因猜成「按字频裁剪把生僻字切掉了」，
实测（本守卫的 `--report` 口径，读 `frontend/public/fonts/*.woff2` 的 cmap）：

    misans-subset-400.woff2  glyphs 3824  cmap 3823  ≈ 560 KB
    GB2312 一级 3755 → 覆盖 3755/3755（100%）
    GB2312 二级 3008 → 覆盖   21/3008（0.7%）
    荃 鑫 淼 犇 喆 堃 赟 燚 彧 玊 → 全部不在 cmap 里

`backend/scripts/subset_misans.py` 的字表是「GB2312 **一级**（区 16~55）+ 源码扫描 CJK +
手写符号」三块相加，**没有任何字频排序**。所以缺字的真实原因是：**二级（区 56~87，
按笔画排序）从来没进过字表**——工具没有「判断这个字罕用」，它压根没看二级。

这件事贵在两点：

1. **二级不是长尾**。3008 个字里绝大多数是姓氏 / 人名 / 地名用字，正好是
   **用户昵称、自选备注、账户名、导入文件名**每天会碰到的那一批；
2. **没有东西能回答「页面上出现了 MiSans 没有的字吗」**。`scan_frontend_chars()` 只能
   覆盖写死的文案，覆盖不了用户输入。`docs/design/font-design.md` §5.2 因此写着
   「生僻字回退系统字体，属可接受长尾」——按上面的实测，这句话是错的。

**用户举的例子有一半连二级都够不着**：实测 `犇 喆 堃 赟 燚 彧 玊` 七个字不在
GB2312 任何一级里（属 GBK 扩展区）。只补二级，这张卡一半的验收仍不达标——所以
判据的目标字符集取 **GBK 汉字全集（20,902）**，而不是 GB2312 一级+二级（6,763）。

判据（只比两个数，不拟合字表写法）
----------------------------------
读每个入库 woff2 的 cmap，算：

- GB2312 **一级必须 100%**——「界面文案不跳字体」的底线，掉一个就判红；
- GBK 汉字 **必须 ≥ `GBK_MIN_COVERAGE`（98%）**——留 2% 的余量给母本缺字
  （官方 woff2 分包会缺个别字），但不许退回现在的 18%。

**不判「字表是怎么写出来的」**：脚本以后换成 `cn-font-split` 分片、或改成全 CJK 区，
只要覆盖数还在，本判据仍然成立。这是刻意的——判据盯着结果，才不会被实现方式绑死。

**字表快照与产物必须一致**：`backend/scripts/misans-subset-charset.txt` 是子集的输入，
若它里面没有某个一级 / 二级字，说明产物是照着一份更浅的字表生成的（或产物与字表不同步）。
两者不一致同样判红——一个和产物对不上的快照，比没有快照更误导人。

已知不覆盖（写在这里，避免下一个人以为它在管）
----------------------------------------------
- **不检查字形是否正确**：只比 cmap 有没有这个码位，画得对不对看不见。
- **不检查母本是否有该字**：母本缺字时子集也缺，此时请调整 `LEVEL2_MIN_COVERAGE`
  并在 PR 里写明缺哪些字——本守卫不替你判断「这个字重要不重要」。
- **不扫用户输入**：它比的是「整个 GB2312 该有的都有」，不是「用户真的会输入什么」。
- **不判体积**：补二级会让单字重从 ~560 KB 涨到 ~1 MB，首屏预算谈判属于另一件事
  （`docs/design/font-design.md` §5.3）。
- **不含 GB2312 之外**：扩展 A / B 区、GB18030 都不在判据内。

用法
----
    python scripts/guard_font_glyph_coverage.py            # 校验（CI）
    python scripts/guard_font_glyph_coverage.py --report   # 打印逐字重覆盖率 + 缺失样本

退出码：0 = 通过；1 = 覆盖不足 / 快照与产物不一致；2 = 拿不到输入（结论不可信，**不得**
当成通过）。
"""

from __future__ import annotations

import argparse
import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = REPO_ROOT / 'frontend' / 'public' / 'fonts'
CHARSET_FILE = REPO_ROOT / 'backend' / 'scripts' / 'misans-subset-charset.txt'

FONT_GLOB = 'misans-subset-*.woff2'

# GBK 汉字覆盖率下限。不取 100%：官方母本 woff2 分包可能本来就缺个别字。
# 现状是 18%（3823/20902），与 98% 之间没有歧义区间，故这条线够用。
GBK_MIN_COVERAGE = 0.98

# ---------------------------------------------------------------- woff2 解析
#
# **刻意不手写 cmap 解析**。首版本守卫手工解 woff2 + cmap format 4，结果在
# `idRangeOffset` 段（那几个 `ro != 0` 的段）上算错了索引，把 3823 个码位读成
# 2667 个 —— 而它**不抛异常**，输出照样"成功"，只是数字全假。这正是 CNB #450
# 「缓存被当成判据」的同族失败：判据自己错了，日志只会更响亮地复述错结论。
#
# 结论：解字体的活交给 `fontTools`（它已经是 `subset_misans.py` 的依赖，CI 里装
# 一个包即可），本守卫只负责**判据**——「一级是否 100%、二级是否 ≥95%」。
# 少写 100 行自研二进制解析，就少 100 行会错且不报错的代码。


def woff2_cmap_codepoints(path: Path) -> set[int]:
    """返回 woff2 的 cmap 覆盖的码位集合（交给 fontTools，不自研解析）。"""
    from fontTools.ttLib import TTFont

    font = TTFont(str(path), lazy=True)
    try:
        best = font.getBestCmap() or {}
        return {cp for cp in best if cp <= 0xFFFF}
    finally:
        font.close()


# ---------------------------------------------------------------- 字符集目标
@lru_cache(maxsize=1)
def gb2312_level1_chars() -> frozenset[str]:
    """GB2312 一级汉字（区 16~55，3755 个，按拼音排序）——底线，必须 100%。"""
    chars: set[str] = set()
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            if hi == 0xD7 and lo > 0xF9:
                break
            try:
                chars.add(bytes([hi, lo]).decode('gb2312'))
            except UnicodeDecodeError:
                continue
    return frozenset(chars)


@lru_cache(maxsize=1)
def gbk_hanzi_chars() -> frozenset[str]:
    """GBK 汉字全集（20,902 个）——目标字符集。

    这是「用户可能输入什么」的合理上界：与 Windows 中文代码页 936 一致。
    只取 CJK 统一表意区（U+4E00~U+9FFF），GBK 里的符号 / 西里尔 / 希腊字母不在此列
    （那些由 Inter 与符号集合覆盖，混进来会把覆盖率算虚）。
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
    return frozenset(chars)


# ---------------------------------------------------------------- 判据
def load_charset_snapshot(charset_file: Path | None = None) -> str | None:
    path = charset_file or CHARSET_FILE
    if not path.exists():
        return None
    return path.read_text(encoding='utf-8')


def check(font_dir: Path = FONT_DIR, charset: str | None = None, charset_file: Path | None = None) -> dict:
    """主判据。返回 {ok, rows, problems}。"""
    fonts = sorted(font_dir.glob(FONT_GLOB))
    if not fonts:
        return {'ok': False, 'unreachable': True, 'rows': [], 'problems': []}

    level1 = gb2312_level1_chars()
    gbk = gbk_hanzi_chars()
    charset_path = charset_file or CHARSET_FILE
    if charset is None:
        charset = load_charset_snapshot(charset_path)

    rows = []
    problems: list[str] = []
    for font in fonts:
        cps = woff2_cmap_codepoints(font)
        miss1 = [c for c in sorted(level1) if ord(c) not in cps]
        miss_gbk = [c for c in sorted(gbk) if ord(c) not in cps]
        cov1 = 1 - len(miss1) / len(level1)
        cov_gbk = 1 - len(miss_gbk) / len(gbk)
        rows.append(
            {
                'font': font.name,
                'cmap': len(cps),
                'level1': (len(level1) - len(miss1), len(level1), cov1),
                'gbk': (len(gbk) - len(miss_gbk), len(gbk), cov_gbk),
                'miss1': miss1,
                'miss_gbk': miss_gbk,
            }
        )
        if miss1:
            problems.append(
                f'{font.name}: GB2312 一级缺 {len(miss1)} 字（覆盖率 {cov1:.1%}）——'
                f'一级必须 100%，样本：{"".join(miss1[:24])}'
            )
        if cov_gbk < GBK_MIN_COVERAGE:
            problems.append(
                f'{font.name}: GBK 汉字覆盖率 {cov_gbk:.1%} < 下限 '
                f'{GBK_MIN_COVERAGE:.0%}（缺 {len(miss_gbk)}/{len(gbk)}），'
                f'样本：{"".join(miss_gbk[:24])}'
            )

    if charset is None:
        problems.append(f'字表快照缺失：{_rel(charset_path)}（子集产物的输入不可审计）')
    else:
        present = set(charset)
        no1 = [c for c in sorted(level1) if c not in present]
        no_gbk = [c for c in sorted(gbk) if c not in present]
        if no1:
            problems.append(f'字表快照缺 GB2312 一级 {len(no1)} 字——产物与字表不同步，样本：{"".join(no1[:24])}')
        cov_gbk_snap = 1 - len(no_gbk) / len(gbk)
        if cov_gbk_snap < GBK_MIN_COVERAGE:
            problems.append(
                f'字表快照 GBK 覆盖 {cov_gbk_snap:.1%} < 下限 {GBK_MIN_COVERAGE:.0%}'
                f'（缺 {len(no_gbk)}/{len(gbk)}）——'
                f'`backend/scripts/subset_misans.py` 的 `build_charset()` 还没扩到 GBK'
            )

    return {'ok': not problems, 'rows': rows, 'problems': problems}


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace('\\', '/')
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='MiSans 子集字形覆盖守卫')
    parser.add_argument('--report', action='store_true', help='打印逐字重覆盖率明细')
    parser.add_argument('--font-dir', type=Path, default=FONT_DIR, help=argparse.SUPPRESS)
    parser.add_argument('--charset-file', type=Path, default=CHARSET_FILE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        result = check(args.font_dir, charset_file=args.charset_file)
    except Exception as exc:  # 解析失败 = 结论不可信，不是「通过」
        print(f'无法读取字体产物，结论不可信：{exc}', file=sys.stderr)
        return 2

    if result.get('unreachable'):
        print(f'字体产物不可达：{_rel(args.font_dir)}/{FONT_GLOB} 一个都没找到', file=sys.stderr)
        return 2

    if args.report:
        for row in result['rows']:
            ok1, tot1, cov1 = row['level1']
            okg, totg, covg = row['gbk']
            print(
                f'{row["font"]:<28} cmap {row["cmap"]:>5}  '
                f'一级 {ok1}/{tot1} ({cov1:.1%})  GBK {okg}/{totg} ({covg:.1%})'
            )

    if result['ok']:
        print(
            f'MiSans 子集字形覆盖通过（{len(result["rows"])} 个字重；GB2312 一级 100%、GBK ≥ {GBK_MIN_COVERAGE:.0%}）。'
        )
        return 0

    print(f'MiSans 子集字形覆盖不足（{len(result["problems"])} 项）：', file=sys.stderr)
    for p in result['problems']:
        print(f'  - {p}', file=sys.stderr)
    print('', file=sys.stderr)
    print(
        '修法：`backend/scripts/subset_misans.py` 的 `build_charset()` 用\n'
        '`gbk_hanzi_chars()` 做字符集，再用本地官方母本重生成 4 个字重产物\n'
        '（母本不在仓库里，见 docs/design/font-design.md §5.2）。\n'
        '若母本本身缺某些字，请调整 GBK_MIN_COVERAGE 并在 PR 里写明缺哪些。',
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    sys.exit(main())
