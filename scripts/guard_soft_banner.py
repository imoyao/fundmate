#!/usr/bin/env python3
"""守卫：禁止在业务代码里新写「自绘柔性提示条壳」（#2725，源 #2716 批次 3）。

WHY（源 issue #2716 / #2725）
-----------------------------
#2716 抽出了 ``frontend/src/components/SoftBanner/index.vue``，但**没有任何机制拦住第 6 份
手写**：组件存在 ≠ 有人用。本仓已有前车之鉴——视图层 ``.commit()`` 收敛过一拨，没有守卫时
又长回来（#1606 / #1620）。把「请用 SoftBanner」写进 AGENTS.md / 设计文档是**默认无效**的：
写进文档的规则会被绕开，只有钩子/CI 级判据才算机制。

判据（刻意窄，宁可漏判不可错判）
--------------------------------
一个**样式规则块**同时满足下面三条即命中：

1. 选择器（含 SCSS 嵌套拼接后的完整选择器）里出现 ``banner``（不分大小写）；
2. 声明体里有 ``display: flex``；
3. 声明体里有**真实的**背景或边框——``background`` / ``background-color`` 的值不是
   ``none`` / ``transparent`` / ``unset`` / ``initial``，或 ``border`` / ``border-*`` 的值不是
   ``none`` / ``0`` / ``0px``。

⇒ 这正好放过**迁移后**的消费方：它们保留了 ``class="recon-banner"`` 这类 e2e 锚点类名，
但样式里只剩 ``flex: 1`` / ``font-size`` / ``color`` 排版声明（``flex: 1`` 不是
``display: flex``；``border-radius`` 不匹配 ``border``）。也就是说，
**「锚点类名还在」这件事本身不会让守卫变红**——这是本判据能落地的前提。

已知不覆盖（写下来免得下一个人以为是漏判）
------------------------------------------
- **不叫 banner 的自绘提示条**：``.notice-bar`` / ``.tip-block`` / ``.hint-box`` 一律不命中。
  判据一旦放宽到「有底色 + flex 的块」，就会把卡片、标签、按钮组全部命中，误判即弃用
  （#2725 正文的「误判即弃用」风险）。这类靠 code review，不靠本守卫。
- **壳与配色分块写的**：``.soft-banner { display: flex }`` +
  ``.soft-banner--info { background/border }`` 这种 BEM 拆法，单块内不同时具备三要素，
  **不命中**——包括 SoftBanner 自身（故它在 ALLOWLIST 里只是双保险）。
  代价：照抄组件内部实现、另起一份拆成「基础块 + 修饰块」的写法拦不住。
  接受这个代价的理由：真实的手写第 N 份几乎都是**一块写完**（本仓 6 处命中全部如此），
  而「复制组件内部实现」属另一类问题，靠 review 看得见。跨块聚合要按类名前缀猜族，
  误判面会大过收益。
- **模板内联 style**（``:style="{ background: ... }"``）：只扫 ``<style>`` 段与 ``.scss``/``.css``。
  ``<script>`` 里的 CSS 字符串同样不参与——把「讲解用的字符串」当代码判会自崩
  （``guard_control_clip.py`` 的同类教训）。
- **``el-alert`` 包壳**：类名不含 banner，本守卫不管（那是 #2723 的存量判定）。
- **跨行 / 简写组合**：``border: 1px solid`` 与 ``border-left: 1px solid`` 都认；
  ``border-width`` + ``border-style`` 分开写也认；但**没有**背景与边框、只靠
  ``box-shadow`` 撑出「底盘」的块不命中。

豁免
----
1. ``ALLOWLIST``：**永久合理**的豁免，逐条给理由（SoftBanner 自身、§2 定性排除的形态）。
2. ``BASELINE``：**待清的技术债**，按**具体文件路径**枚举（不准写通配、不准只写个数），
   每条要指回 issue。目标状态是空字典——``#2724`` 合并后此处应为空。
3. 行内豁免：在声明块**本行或相邻行**写 ``banner-guard-allow`` 并注理由。
   刻意不提供「目录级豁免」——整目录放行会让判据在真实代码上失去意义。

用法
----
    python scripts/guard_soft_banner.py                    # 扫描 frontend/src 全量（CI）
    python scripts/guard_soft_banner.py a.vue b.scss       # 只扫指定文件（pre-commit / 局部验证）
    python scripts/guard_soft_banner.py --report           # 打印命中清单与判据自检

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".css", ".scss", ".sass"}

# 判据本体
_SELECTOR_HIT_RE = re.compile(r"banner", re.IGNORECASE)
_FLEX_RE = re.compile(r"display\s*:\s*flex\b", re.IGNORECASE)
_BACKGROUND_RE = re.compile(
    r"(?<![\w-])background(?:-color)?\s*:\s*([^;}]+)", re.IGNORECASE
)
# `border` 简写与 `border-top/right/bottom/left` 及 `-width/-style/-color` 长写都认；
# `border-radius` 因长写组不含 `radius` 而不匹配（`border` 后紧跟 `-radius` 时 `\s*:` 对不上）。
_BORDER_RE = re.compile(
    r"(?<![\w-])border(?:-(?:top|right|bottom|left))?(?:-(?:width|style|color))?\s*:\s*([^;}]+)",
    re.IGNORECASE,
)
_NULL_VALUES = {"none", "transparent", "unset", "initial", "inherit", "0", "0px", ""}

# 永久豁免：形态上**不属**「柔性提示条」家族（docs/spec/soft-banner.md §2 已定性排除），
# 或就是组件自身。新增条目必须写明理由，否则等于把守卫关掉一半。
ALLOWLIST: dict[str, str] = {
    "components/SoftBanner/index.vue": (
        "组件自身——它就是「一份壳」的唯一定义处，判据在此必然命中"
    ),
    "views/explore/exploreView/ExploreConvBanner.vue": (
        "匿名转化**营销卡**（品牌渐变底 + 大 CTA），docs/spec/soft-banner.md §2 已定性排除："
        "它不是「非阻断警示条」，套提示条壳会削弱转化入口"
    ),
    "views/status/components/StatusBanner.vue": (
        "系统状态页**大卡**（bg-card 底 + 左 4px 色条 + radius-lg + 阴影），同 §2 定性排除："
        "形态是内容区块而非行内提示条"
    ),
}

# 待清技术债（按 `相对路径::归一化选择器` 精确到**块**，目标为空）。
#
# 为什么精确到选择器而不是只写文件：只写文件等于「这个文件里随便再加几处都放行」，
# 那才是真放松。精确到块后，同一文件新增第 2 处仍然会红。
#
# **当前为空（#2730 已清空，2026-10-29）**：曾有 3 处存量，是 #2725 全仓普查时新发现的
# （#2724 的人工普查漏了它们），形态属本家族但超出 SoftBanner 当时的表达力：
#   · `.conflict-banner` / `.orphan-banner`：`brand-100` 品牌色底（组件无 brand 档）；
#   · `.soft-reconcile-banner`：还带 `border-left: 3px` 语义色条。
# #2730 已给组件补 `brand` 档与 `role` prop，三处全部迁完，基线条目随之删除。
# 纪律不变：日后若要暂存存量，仍须按 `path::selector` 逐条枚举 + 写明理由；
# 条目「已无对应命中」会报 STALE 红灯（防基线僵化）。
BASELINE: dict[str, str] = {}

_INLINE_ALLOW = "banner-guard-allow"

_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)


class Hit:
    __slots__ = ("line", "path", "reason", "selector")

    def __init__(self, path: str, line: int, selector: str, reason: str) -> None:
        self.path = path
        self.line = line
        self.selector = selector
        self.reason = reason


def _strip_comments(text: str) -> str:
    """去掉 CSS 注释，**保留换行**以维持行号可读。"""
    return re.sub(
        r"/\*.*?\*/",
        lambda m: "\n" * m.group(0).count("\n"),
        text,
        flags=re.DOTALL,
    )


def _compose(parent: str, raw: str) -> str:
    """SCSS 嵌套选择器拼接。at-rule（@media/@supports/@keyframes…）不进入选择器链。"""
    raw = " ".join(raw.split())
    if not raw:
        return parent
    if raw.startswith("@"):
        return parent
    if not parent:
        return raw
    if "&" in raw:
        return raw.replace("&", parent)
    return f"{parent} {raw}"


def _iter_style_chunks(rel: str, text: str) -> list[tuple[str, int]]:
    """返回 [(style 文本, 该文本首行的文件行号)]。"""
    if rel.endswith(".vue"):
        chunks = []
        for m in _STYLE_BLOCK_RE.finditer(text):
            start_line = text.count("\n", 0, m.start(1)) + 1
            chunks.append((m.group(1), start_line))
        return chunks
    return [(text, 1)]


def _iter_rules(css: str, base_line: int):
    """遍历样式文本里的规则块，yield (selector, decl, 文件行号)。

    手工配对花括号而非正则：SCSS 有嵌套，`[^{}]*{[^{}]*}` 这类正则会在第一个内层 `}`
    处误闭合（同 `guard_control_clip.py` 的教训）。
    """
    stack: list[tuple[str, int, int]] = []  # (完整选择器, 声明起点, 选择器起点)
    seg_start = 0
    for i, ch in enumerate(css):
        if ch == "{":
            raw = css[seg_start:i]
            parent = stack[-1][0] if stack else ""
            stack.append((_compose(parent, raw), i + 1, seg_start))
            seg_start = i + 1
        elif ch == "}":
            if stack:
                selector, decl_start, _ = stack.pop()
                decl = css[decl_start:i]
                line = base_line + css.count("\n", 0, decl_start)
                yield selector, decl, line
            seg_start = i + 1
        elif ch == ";":
            # `;` 结束一条声明，之后的文本要么是新声明、要么是子块的选择器——
            # 两种情况下「选择器起点」都该前移。SCSS 允许块内声明与子块混排
            # （`.conv-banner { max-width: …; .conv-banner__inner { … } }`），
            # 不在这里前移会把前面的声明文本当成子块选择器的一部分。
            seg_start = i + 1


def _has_real_background(decl: str) -> bool:
    for m in _BACKGROUND_RE.finditer(decl):
        value = m.group(1).strip().lower()
        if value and value not in _NULL_VALUES:
            return True
    return False


def _has_real_border(decl: str) -> bool:
    for m in _BORDER_RE.finditer(decl):
        value = m.group(1).strip().lower()
        if value and value not in _NULL_VALUES:
            return True
    return False


def scan_file(path: Path, root: Path) -> list[Hit]:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        # 仓外样本（回归测试写在 tmpdir）：用绝对路径当标识——它天然不匹配任何
        # 相对路径的白名单/基线，于是测的是**判据本身**而不是「有没有登记」。
        rel = path.as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (
        OSError,
        UnicodeDecodeError,
    ) as exc:  # 读不到 = 结论不可信，交给调用方按 2 退出
        raise RuntimeError(f"{rel}: 读取失败（{exc}）") from exc

    hits: list[Hit] = []
    lines = text.splitlines()
    for chunk, base_line in _iter_style_chunks(rel, text):
        for selector, decl, line in _iter_rules(_strip_comments(chunk), base_line):
            if not _SELECTOR_HIT_RE.search(selector):
                continue
            if not _FLEX_RE.search(decl):
                continue
            if not (_has_real_background(decl) or _has_real_border(decl)):
                continue
            # 行内豁免：本行或相邻行有 banner-guard-allow
            window = lines[max(0, line - 2) : line + 1]
            if any(_INLINE_ALLOW in ln for ln in window):
                continue
            hits.append(Hit(rel, line, " ".join(selector.split()), "自绘提示条壳"))
    return hits


def _iter_targets(explicit: list[str], root: Path):
    if explicit:
        for arg in explicit:
            p = Path(arg)
            if not p.is_absolute():
                p = (REPO_ROOT / arg) if not p.exists() else p
            yield p.resolve()
        return
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in SCAN_SUFFIXES:
            yield p


def main(argv: list[str]) -> int:
    report = "--report" in argv
    explicit = [a for a in argv if not a.startswith("-")]

    try:
        targets = list(_iter_targets(explicit, DEFAULT_ROOT))
    except Exception as exc:  # noqa: BLE001 - 任何取数失败都不得当成通过
        print(f"无法确定扫描目标：{exc}", file=sys.stderr)
        return 2
    if not targets:
        print("未找到可扫描文件（结论不可信）", file=sys.stderr)
        return 2

    hits: list[Hit] = []
    try:
        for path in targets:
            hits.extend(scan_file(path, DEFAULT_ROOT))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    blocked: list[Hit] = []
    used_baseline: set[str] = set()
    for hit in hits:
        if hit.path in ALLOWLIST:
            continue
        key = f"{hit.path}::{hit.selector}"
        if key in BASELINE:
            used_baseline.add(key)
            continue
        blocked.append(hit)

    # 僵尸基线：登记了却再没有任何命中——说明那块代码改了形状（或已修掉），
    # 条目留着会让判据在这块**静默失效**，而读登记表的人以为它还在拦。
    #
    # **只在全量扫描时判定**：局部扫描（pre-commit 只扫本次改动文件）时基线条目
    # 当然不在扫描范围内，那不是「失效」而是「没扫到」。混为一谈会让守卫在
    # 最需要它安静的地方天天误报。
    full_scan = not explicit
    stale = sorted(set(BASELINE) - used_baseline) if full_scan else []

    if report:
        print(
            f"扫描 {len(targets)} 个文件；原始命中 {len(hits)} 处；阻断 {len(blocked)} 处"
        )
        for hit in hits:
            key = f"{hit.path}::{hit.selector}"
            if hit.path in ALLOWLIST:
                tag = "ALLOW"
            elif key in BASELINE:
                tag = "BASE "
            else:
                tag = "BLOCK"
            print(f"  [{tag}] {hit.path}:{hit.line}  {hit.selector}")
        if not hits:
            print("  （无命中）")
        for key in stale:
            print(f"  [STALE] {key}  ← 基线条目已无对应命中，请删除")

    if stale:
        print("\nBASELINE 里有已失效的条目（只减不增）：", file=sys.stderr)
        for key in stale:
            print(f"  {key}", file=sys.stderr)
        print(
            "  这说明该处代码已改形状或已迁走——请删除对应条目，"
            "否则判据在这一块静默失效。",
            file=sys.stderr,
        )
        return 1

    if blocked:
        print("\n命中「自绘柔性提示条壳」——请改用 SoftBanner：", file=sys.stderr)
        for hit in blocked:
            print(f"  {hit.path}:{hit.line}  {hit.selector}", file=sys.stderr)
        print(
            "\n  统一做法：frontend/src/components/SoftBanner/index.vue"
            "（设计依据 docs/spec/soft-banner.md）。"
            "\n  确实不是提示条（如营销卡 / 状态大卡）时，在 ALLOWLIST 里逐条登记理由；"
            "\n  临时放行在声明本行或相邻行写 `banner-guard-allow` 并注原因。",
            file=sys.stderr,
        )
        return 1

    if report:
        print("通过：无未登记的自绘提示条壳。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
