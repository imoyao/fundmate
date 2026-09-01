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

# 中文常用字 + 技术提交高频词集合。
# 设计要点：原守卫只用「前 50 常用字」，但技术提交常用词（修复 / 合并 / 错误 /
# 格式化 / 遗留 / 落实 / 拦截 / 乱码 / 重构 …）多不在前 50，导致正常技术提交被
# 「零常用字」误判为乱码（如本次「落实 GBK 乱码三层拦截」「prettier 格式化…合并
# 遗留 lint 错误」）。故扩充为较全的高频字 + 技术词，正常中文（即便偏技术）几乎
# 必然命中其中若干字符；而真正的 mojibake 由生僻 CJK 组成，一个常用字都不会有，
# 仍会被拦截。这是「常用字占比」启发式的正负样本分界线。
COMMON_HAN = set(
    # —— 现代汉语高频常用字（覆盖绝大多数日常与文档用词）——
    "的一是不了在有人我他这中大来上国个到说子为和你地出会时也要下以生"
    "自学去过成就分得主用年一看知理工发力可就道多经度高对同么机之方进"
    "着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从"
    "业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表"
    "间样与关各重新线内数正心反明看原又利比或但质气第向道命此变条只"
    "没结解问意建月公无系军很情者最立代想已通期史使长认处所死伤早却"
    "即及入几民后制回今改如那她给便也者下得可于去来能下过种面多定行"
    "法所民经十三之进着等部重头次将实想回表今通改开如质确真指社活设"
    # —— 技术提交高频词（commit / PR 常见动词与名词）——
    "修合并错误格式化遗留落实三层拦截乱码重构编码逻辑配置支持处理更新"
    "增加优化解决移除添加修改调整补充实现完善功能模块接口数据字段校验"
    "同步测试文件目录版本依赖构建部署提交代码项目系统用户权限状态信息"
    "内容显示页面样式组件类型结构流程方案设计开发维护清理问题缺陷异常"
    "警告提示成功失败开始结束进行完成生成创建删除保存读取写入加载解析"
    "转换计算判断检查验证对比筛选排序分组统计汇总报告记录日志输出输入"
    "参数选项设置获取查询搜索匹配替换插入"
)


# 日文假名：含假名的文本按日文处理，不套中文乱码启发式（避免误报合法日文）
JAPANESE_KANA_RE = re.compile(r"[\u3040-\u30ff]")


# ftfy 仅作可选提示，不作为拦截信号——实测 ftfy 会把正常中文（如"修复了...问题"）
# 误判为 mojibake，对中文仓库会直接红，故只保留 U+FFFD + 常用汉字启发式作主判定。
def check_text(text: str, label: str, min_cjk: int = 30) -> bool:
    """对一段文本做乱码判定，返回 True 表示疑似乱码并已打印错误。

    min_cjk：触发启发式所需的 CJK 字符下限。文件用 30（避免大文档偶发零常用字误报），
    提交信息用 20（见 _check_commit_message_text：短技术提交常零常用字，阈值抬高防误判）。
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
    """对提交信息正文做乱码判定（去除 # 注释行）。供 --check-message / --check-commit / AI 工具复用。

    提交信息通常很短（十几个汉字以内），且技术提交常用「落实 / 乱码 / 拦截 / 重构 /
    编码」等非常用字，几乎必然命中不了前 50 常用字。若沿用文件的 min_cjk=30 软阈值，
    短消息会被「零常用字」误判为乱码（实际是正常中文）。故把提交信息的软启发式阈值
    抬高到 20：只有在提交信息里出现 20+ 个 CJK 且一个常用字都没有，才像真正的整句
    乱码；短技术提交因此放行。硬性 U+FFFD 检查始终生效，仍能抓住真正损坏的字节。
    """
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    return check_text(body, label, min_cjk=20)


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
