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

import os
import re
import subprocess
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


def _check_commit_message_text(text: str, label: str) -> bool:
    """对提交信息正文做乱码判定（去除 # 注释行）。供 --check-message / --check-commit / AI 工具复用。"""
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    return check_text(body, label, min_cjk=3)


def _iter_commit_files(sha: str):
    """逐文件 yield 某次提交改动的文件相对路径（合并提交默认无 diff，自动跳过）。"""
    out = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    for rel in out.splitlines():
        rel = rel.strip()
        if rel:
            yield rel


def _check_commit(sha: str) -> bool:
    """检查单个提交的中文提交信息是否疑似乱码。返回 True 表示发现问题。"""
    msg = subprocess.run(
        ["git", "show", "-s", "--format=%B", sha],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    return _check_commit_message_text(msg, f"commit {sha[:8]} message")


def _check_commit_files(sha: str, root: Path) -> bool:
    """检查单个提交改动的文件是否含乱码。返回 True 表示发现问题。"""
    # 二进制 / 非文本后缀直接跳过，避免误报
    binary_suffixes = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".webp",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".pdf",
        ".zip",
        ".gz",
        ".tgz",
        ".bin",
        ".exe",
        ".dll",
        ".db",
        ".sqlite",
        ".pyc",
        ".lock",
        ".so",
    }
    bad = False
    for rel in _iter_commit_files(sha):
        fp = root / rel
        if not fp.is_file():
            continue
        if fp.suffix.lower() in binary_suffixes:
            continue
        if is_likely_mojibake(fp):
            bad = True
    return bad


def _pre_push() -> int:
    """pre-push 阶段：扫描本次待推送提交的文件与中文提交信息，发现乱码即拦截。

    读取标准 pre-push 输入：`<local-ref> <local-sha> <remote-ref> <remote-sha>`。
    这是「AI Tool Hooks」层的推送前闸门：无论是否装了 pre-commit，任何 `git push`
    （含 AI 工具的 commit_changes.py --push）都会先过这一关。
    """
    line = sys.stdin.read().strip()
    if not line:
        return 0
    parts = line.split()
    if len(parts) < 4:
        return 0
    local_sha, remote_sha = parts[1], parts[3]
    root = Path(os.getcwd())

    if set(remote_sha) == {"0"}:  # 新分支：远端无该引用
        revs = subprocess.run(
            ["git", "rev-list", local_sha],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ).stdout.split()
    else:
        revs = subprocess.run(
            ["git", "rev-list", f"{remote_sha}..{local_sha}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ).stdout.split()
    if not revs:
        return 0

    bad = False
    for sha in revs:
        sha = sha.strip()
        if not sha:
            continue
        if _check_commit(sha):
            bad = True
        if _check_commit_files(sha, root):
            bad = True

    if bad:
        print(
            "ERROR: 推送被拦截——待推送提交中存在 GBK 乱码（提交信息或文件）。"
            "请修复（commit --amend 或重新填写）后重新推送。",
            file=sys.stderr,
        )
        return 1
    print("OK: 待推送内容中文编码正常（无 mojibake）")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--check-message":
        if len(args) < 2:
            print("ERROR: --check-message 需要一个提交信息文件路径", file=sys.stderr)
            return 2
        return (
            1
            if _check_commit_message_text(
                Path(args[1]).read_text(encoding="utf-8", errors="replace"),
                "commit-message",
            )
            else 0
        )
    if args and args[0] == "--check-commit":
        if len(args) < 2:
            print("ERROR: --check-commit 需要一个提交 sha", file=sys.stderr)
            return 2
        return 1 if _check_commit(args[1]) else 0
    if args and args[0] == "--pre-push":
        return _pre_push()

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
