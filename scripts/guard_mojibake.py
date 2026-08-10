#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：检测提交中的中文乱码（mojibake）。

乱码症状：原 GBK 中文被当成 Latin-1/其它编码误解码后按 UTF-8 存回，
导致"文档导航"变成"鏂囨。瀵艰埅"等不可读字符。

事故复盘：2026-08-09 一批 26 个 legacy/ 前端重构笔记（.md）由远程 agent
「Claw」写入时编码错误，全部变为不可读乱码，无干净副本可还原。此守卫即为此而设。

检测策略：统计文件中的 CJK 统一表意文字（U+4E00–U+9FFF），
若数量较多（>30）但完全不含任何高频常用汉字，则判定为疑似 mojibake 并拒绝提交。

高频常用汉字（前 30）：的一是不了在有人我他这中大来上国个到说子为和
你地出会时也要下以生自学去过成就分得主用年一看知理工发力可
"""

import re
import sys
from pathlib import Path

# CJK 统一表意文字范围
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 中文高频常用字（前 50，覆盖 >50% 的正常中文文本）。
# 正常的 .md 中文段落几乎必然包含其中若干字符；mojibake 则一个都不会出现。
COMMON_HAN = set(
    "的一是不了在有人我他这中大来上国个到说子为和你地出会时也要下以生"
    "自学去过成就分得主用年一看知理工发力可就道多经度高对同么机之方"
)


def is_likely_mojibake(filepath: Path) -> bool:
    """返回 True 表示该文件疑似中文乱码。"""
    try:
        text = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 文件根本不是 UTF-8，本身就是编码错误，直接拦下
        return True  # pragma: no cover — 此分支依赖文件系统编码，单元测试难覆盖

    cjk_chars = CJK_RE.findall(text)
    if len(cjk_chars) < 30:
        # CJK 字符太少，可能是英文文档带零星中文字符，不判为乱码
        return False

    found_common = COMMON_HAN & set(cjk_chars)
    if found_common:
        return False  # 包含常用汉字，正常文本

    sample = "".join(cjk_chars[:20])
    print(
        "ERROR: %s 疑似中文乱码（%d 个 CJK 字符但无任何常用汉字）"
        % (filepath, len(cjk_chars)),
        file=sys.stderr,
    )
    print(
        "       样本字符：%s" % sample,
        file=sys.stderr,
    )
    print(
        "       乱码特征：原 GBK 中文被错误编码后不可读，提交被拒绝。",
        file=sys.stderr,
    )
    print(
        "       请用正确编码重写此文件内容后重新提交。",
        file=sys.stderr,
    )
    return True


def main() -> int:
    failed = 0
    for arg in sys.argv[1:]:
        fp = Path(arg)
        if not fp.is_file():
            continue
        if is_likely_mojibake(fp):
            failed += 1
    if failed:
        return 1
    print("OK: 提交文件中文内容正常（无 mojibake）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
