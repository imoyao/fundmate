#!/usr/bin/env python3
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

try:
    import ftfy
except ImportError:  # ftfy 仅在 CI / pre-commit 附加依赖中提供；本地无依赖时降级
    ftfy = None

# CJK 统一表意文字范围
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 中文高频常用字（前 50，覆盖 >50% 的正常中文文本）。
# 正常的 .md 中文段落几乎必然包含其中若干字符；mojibake 则一个都不会出现。
COMMON_HAN = set(
    "的一是不了在有人我他这中大来上国个到说子为和你地出会时也要下以生"
    "自学去过成就分得主用年一看知理工发力可就道多经度高对同么机之方"
)


# 日文假名：含假名的文本按日文处理，不套中文乱码启发式（避免误报合法日文）
JAPANESE_KANA_RE = re.compile(r"[\u3040-\u30ff]")


# ftfy 仅作可选提示，不作为拦截信号——实测 ftfy 会把正常中文（如"修复了...问题"）
# 误判为 mojibake，对中文仓库会直接红，故只保留 U+FFFD + 常用汉字启发式作主判定。
def check_text(text: str, label: str, min_cjk: int = 30) -> bool:
    """对一段文本做乱码判定，返回 True 表示疑似乱码并已打印错误。

    min_cjk：触发启发式所需的 CJK 字符下限。文件用 30（避免大文档偶发零常用字误报），
    提交信息用 3（标题通常短，短乱码如「鍗囩骇」也需抓住）。
    """
    # 1. 硬性拦截：替换字符 U+FFFD 绝不应出现在源码/提交信息中
    if "\ufffd" in text:
        print(
            f"ERROR: {label} 包含损坏字符 U+FFFD（替换符），请检查编码！",
            file=sys.stderr,
        )
        return True

    # 2. 含日文假名则视为合法日文，跳过中文启发式
    if JAPANESE_KANA_RE.search(text):
        return False

    # 3. 启发式主判定：含足够多 CJK 但零常用汉字 → 疑似乱码（正常中文必含常用字）
    cjk_chars = CJK_RE.findall(text)
    if len(cjk_chars) >= min_cjk and not (COMMON_HAN & set(cjk_chars)):
        sample = "".join(cjk_chars[:20])
        print(
            f"ERROR: {label} 疑似中文乱码（{len(cjk_chars)} 个 CJK 字符但无任何常用汉字）",
            file=sys.stderr,
        )
        print(f"       样本字符：{sample}", file=sys.stderr)
        print(
            "       乱码特征：原 GBK 中文被错误编码后不可读，提交被拒绝。",
            file=sys.stderr,
        )
        return True

    return False


def is_likely_mojibake(filepath: Path) -> bool:
    """返回 True 表示该文件疑似中文乱码。"""
    try:
        text = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 文件根本不是 UTF-8，本身就是编码错误，直接拦下
        print(
            f"ERROR: {filepath} 不是合法 UTF-8 文件，编码错误，提交被拒绝。",
            file=sys.stderr,
        )
        return True  # pragma: no cover — 此分支依赖文件系统编码，单元测试难覆盖
    return check_text(text, str(filepath))


def _check_commit_message(msg_path: str) -> int:
    """pre-commit commit-msg 阶段：检查提交信息文件，乱码则拒绝。"""
    text = Path(msg_path).read_text(encoding="utf-8", errors="replace")
    # 去除注释行（以 # 开头的 diff 摘要等），仅对正文本体判定
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    if check_text(body, "commit-message", min_cjk=3):
        print(
            "请修正提交信息中的乱码后重新提交（commit --amend 或重新填写）。",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--check-message":
        if len(args) < 2:
            print("ERROR: --check-message 需要一个提交信息文件路径", file=sys.stderr)
            return 2
        return _check_commit_message(args[1])

    failed = 0
    for arg in args:
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
