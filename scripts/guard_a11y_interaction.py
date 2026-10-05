# -*- coding: utf-8 -*-
"""交互可达性守门（#1842）：三类可机械识别的模式。

1) 纯图标按钮无可访问名称：``<el-button>`` / ``<button>`` 内**只有图标**、没有文字，
   且开标签没有 ``aria-label`` / ``title``。
   （``el-tooltip`` **不构成**可访问名称——屏幕阅读器不读它。）
2) ``@click`` 绑在非交互元素（div / span / li）上，且没有 ``role`` + ``tabindex`` + ``@keydown``。
3) hover 显隐缺兜底：某元素**只靠 ``:hover`` 才显现**（同选择器 hover 规则里把
   ``opacity`` / ``visibility`` 改成可见值），却既没有 ``:focus-within`` 兜底，
   也不在 ``@media (hover: none)`` 里给出静态可见态。

这三类正是前端交互排查（#1834）里 P1 的主体。人工 review 会漏，机械判据不会。

用法
----
    python scripts/guard_a11y_interaction.py             # 扫 frontend/src 全量
    python scripts/guard_a11y_interaction.py a.vue b.vue # 只扫指定文件（pre-commit）
    python scripts/guard_a11y_interaction.py --warn      # 只报告不阻断（存量清理期用）

豁免
----
    确需例外的，在**同一行**加 ``a11y-allow`` 并写明理由。

退出码：0 = 通过；1 = 命中。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

TEMPLATE_RE = re.compile(r"<template>(.*?)</template>", re.S)
STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)

TEXT_RE = re.compile(r">[^<>{}]*\S[^<>{}]*<|\{\{[^}]*\}\}")  # 元素间文本或插值
TAG_RE = re.compile(r"</?[A-Za-z][^>]*>|<!--.*?-->", re.S)

BUTTON_OPEN_RE = re.compile(r"<(el-button|button)\b(?P<attrs>[^>]*?)(?P<self>/?)>", re.S)
HAS_NAME_RE = re.compile(r"(aria-label|:aria-label|title)\s*=")
HAS_SLOT_RE = re.compile(r"\bslot\s*=")

CLICK_TAG_RE = re.compile(r"<(div|span|li)\b(?P<attrs>[^>]*)>", re.I)
HAS_ROLE_RE = re.compile(r"\brole\s*=")
HAS_TABINDEX_RE = re.compile(r"\btabindex\s*=")
HAS_KEYBOARD_RE = re.compile(r"@keydown|v-on:keydown", re.I)
HAS_CLICK_RE = re.compile(r"@click|v-on:click")

# 图标识别：本地/在线图标组件 + Element Plus 的 el-icon 容器 + 内联 svg + <i> 图标字体，
# 再加 Element Plus 图标组件的**直用**（<el-button><Plus /></el-button> 这种裸写法）。
# 裸写 element-plus 图标也必须算图标，否则「纯图标按钮」会被当成「无图标无文字」静默放过。
# 不能用「PascalCase 自闭合 = 图标」的启发式：仓内 <TransactionTable/>、<SummaryStats/>
# 等业务组件同样是 PascalCase 自闭合，会把规则 1 变成噪声源。故取包内实证名单。
EP_ICON_NAMES = frozenset(
    """
    AddLocation Aim AlarmClock Apple ArrowDown ArrowDownBold ArrowLeft ArrowLeftBold ArrowRight ArrowRightBold
    ArrowUp ArrowUpBold Avatar Back Baseball Basketball Bell BellFilled Bicycle Bottom
    BottomLeft BottomRight Bowl Box Briefcase Brush BrushFilled Burger Calendar Camera
    CameraFilled CaretBottom CaretLeft CaretRight CaretTop Cellphone ChatDotRound ChatDotSquare ChatLineRound ChatLineSquare
    ChatRound ChatSquare Check Checked Cherry Chicken ChromeFilled CircleCheck CircleCheckFilled CircleClose
    CircleCloseFilled CirclePlus CirclePlusFilled Clock Close CloseBold Cloudy Coffee CoffeeCup Coin
    ColdDrink Collection CollectionTag Comment Compass Connection Coordinate CopyDocument Cpu CreditCard
    Crop DArrowLeft DArrowRight DCaret DataAnalysis DataBoard DataLine Delete DeleteFilled DeleteLocation
    Dessert Discount Dish DishDot Document DocumentAdd DocumentChecked DocumentCopy DocumentDelete DocumentRemove
    Download Drizzling Edit EditPen Eleme ElemeFilled ElementPlus Expand Failed Female
    Files Film Filter Finished FirstAidKit Flag Fold Folder FolderAdd FolderChecked
    FolderDelete FolderOpened FolderRemove Food Football ForkSpoon Fries FullScreen Goblet GobletFull
    GobletSquare GobletSquareFull GoldMedal Goods GoodsFilled Grape Grid Guide Handbag Headset
    Help HelpFilled Hide Histogram HomeFilled HotWater House IceCream IceCreamRound IceCreamSquare
    IceDrink IceTea InfoFilled Iphone Key KnifeFork Lightning Link List Loading
    Location LocationFilled LocationInformation Lock Lollipop MagicStick Magnet Male Management MapLocation
    Medal Memo Menu Message MessageBox Mic Microphone MilkTea Minus Money
    Monitor Moon MoonNight More MoreFilled MostlyCloudy Mouse Mug Mute MuteNotification
    NoSmoking Notebook Notification Odometer OfficeBuilding Open Operation Opportunity Orange Paperclip
    PartlyCloudy Pear Phone PhoneFilled Picture PictureFilled PictureRounded PieChart Place Platform
    Plus Pointer Position Postcard Pouring Present PriceTag Printer Promotion QuartzWatch
    QuestionFilled Rank Reading ReadingLamp Refresh RefreshLeft RefreshRight Refrigerator Remove RemoveFilled
    Right ScaleToOriginal School Scissor Search Select Sell SemiSelect Service SetUp
    Setting Share Ship Shop ShoppingBag ShoppingCart ShoppingCartFull ShoppingTrolley Smoking Soccer
    SoldOut Sort SortDown SortUp Stamp Star StarFilled Stopwatch SuccessFilled Sugar
    Suitcase SuitcaseLine Sunny Sunrise Sunset Switch SwitchButton SwitchFilled TakeawayBox Ticket
    Tickets Timer ToiletPaper Tools Top TopLeft TopRight TrendCharts Trophy TrophyBase
    TurnOff Umbrella Unlock Upload UploadFilled User UserFilled Van VideoCamera VideoCameraFilled
    VideoPause VideoPlay View Wallet WalletFilled WarnTriangleFilled Warning WarningFilled Watch Watermelon
    WindPower ZoomIn ZoomOut
    """.split()
)
_EP_ICON_RE = re.compile(r"<(" + "|".join(sorted(EP_ICON_NAMES)) + r")\b")
_KNOWN_ICON_RE = re.compile(r"<(IconifyIconOffline|iconify-icon-online|el-icon|svg|i)\b", re.I)

# --- 规则 3：CSS 块解析 -------------------------------------------------
VISIBLE_IN_HOVER_RE = re.compile(r"(?:opacity\s*:\s*(?!0(?:\D|$))\s*[1-9]|opacity\s*:\s*1\b"
                                 r"|visibility\s*:\s*visible)")
VISIBLE_DECL_RE = re.compile(r"(opacity\s*:\s*(?:1(?:\D|$)|0?\.\d+)|visibility\s*:\s*visible)")
# 基态「真隐藏」：只认 0 与 hidden，0.5 这类半透明不算（元素本来就看得见）
HIDDEN_ZERO_RE = re.compile(r"(?:^|[;{\s])opacity\s*:\s*0\s*(?:;|$)|visibility\s*:\s*hidden\s*;")
_AT_RULE_SKIP = ("keyframes", "font-face", "supports", "page", "property", "charset")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _exempt(lines: list[str], lineno: int) -> bool:
    """同行（或其后两行，覆盖跨行属性续写）出现 a11y-allow 即豁免。"""
    return "a11y-allow" in " ".join(lines[lineno - 1 : lineno + 2])


def _has_icon(inner: str) -> bool:
    return _KNOWN_ICON_RE.search(inner) is not None or _EP_ICON_RE.search(inner) is not None


def _has_text(inner: str) -> bool:
    """按钮内是否有可读文字（含插值）。有则按钮已有可访问名称。"""
    stripped = TAG_RE.sub(" ", inner)
    return TEXT_RE.search(stripped) is not None or "{{" in inner


def check_buttons(text: str, rel: str, lines: list[str]) -> list[str]:
    hits = []
    for m in BUTTON_OPEN_RE.finditer(text):
        if m.group("self") == "/":
            continue
        tag, attrs = m.group(1), m.group("attrs")
        close = text.find(f"</{tag}>", m.end())
        if close < 0:
            continue
        inner = text[m.end() : close]
        if "<template" in inner or HAS_SLOT_RE.search(attrs):
            continue  # 插槽内容由调用方决定，静态判不了
        if not _has_icon(inner) or _has_text(inner):
            continue  # 没有图标、或已有文字（文字本身就是可访问名称）
        if HAS_NAME_RE.search(attrs):
            continue
        lineno = _line_of(text, m.start())
        if _exempt(lines, lineno):
            continue
        hits.append(f"{rel}:{lineno}  纯图标 <{tag}> 无 aria-label/title")
    return hits


def check_click_tags(text: str, rel: str, lines: list[str]) -> list[str]:
    hits = []
    for m in CLICK_TAG_RE.finditer(text):
        attrs = m.group("attrs")
        if not HAS_CLICK_RE.search(attrs):
            continue
        if HAS_ROLE_RE.search(attrs) and HAS_TABINDEX_RE.search(attrs) and HAS_KEYBOARD_RE.search(attrs):
            continue
        lineno = _line_of(text, m.start())
        if _exempt(lines, lineno):
            continue
        hits.append(f"{rel}:{lineno}  <{m.group(1)} @click> 缺 role / tabindex / @keydown")
    return hits


def _iter_css_blocks(css: str):
    """浅层解析 CSS：产出 (selector, body, media_chain)。只跟一层花括号，够用且不引依赖。

    ``@keyframes`` / ``@font-face`` 等内部块整体跳过——``from { opacity: 0 }`` 是动画
    起点，不是「元素默认隐藏」，早期版本正是把它误报成 hover 缺兜底。
    """
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    stack: list[tuple[str, list[str]]] = []
    media: list[str] = []
    buf = []
    for ch in css:
        if ch == "{":
            head = "".join(buf).strip()
            buf = []
            if head.startswith("@"):
                at = head.split(None, 1)[0].lower()
                if at == "@media":
                    media.append(head)
                    stack.append(("@media", media))
                    continue
                if any(at.endswith(k) or k in at for k in _AT_RULE_SKIP):
                    stack.append(("@skip", media))
                    continue
                stack.append((head, media))
                continue
            stack.append((head, media))
        elif ch == "}":
            if not stack:
                buf = []
                continue
            head, med = stack.pop()
            if head == "@media":
                if media:
                    media.pop()
                buf = []
                continue
            if head == "@skip":
                buf = []
                continue
            yield head, "".join(buf), list(med)
            buf = []
        else:
            buf.append(ch)


def _base_selector(selector: str) -> str:
    """取受 hover 影响的元素选择器：``.row:hover .act`` -> ``.act``；``.act:hover`` -> ``.act``。"""
    parts = [p.strip() for p in re.split(r"\s+|>", selector) if p.strip()]
    keep = []
    for part in parts:
        if part.startswith(":"):
            break
        keep.append(part)
    tail = parts[len(keep):]
    tail = [p for p in tail if p and not p.startswith(":")]
    return (tail[0] if tail else (keep[-1] if keep else "")).lstrip("&").strip()


def _split_selectors(selector: str) -> list[str]:
    """把 ``.row:hover .a, .b`` 拆成 ``['.a', '.b']``。

    只保留无伪类的类 / id / 属性选择器——``.row:hover``、``[data-x]:hover`` 这类
    状态选择器不是「元素是谁」，拿它去匹配基态隐藏集合必然对不上。
    """
    out = []
    for group in selector.split(","):
        for part in re.split(r"[\s>+~]+", group):
            part = part.strip()
            if part and part[0] in ".#[" and ":" not in part:
                out.append(part)
    return out


def check_hover_fallback(text: str, rel: str, lines: list[str]) -> list[str]:
    """只抓「基态真隐藏、只靠 hover 才显现」的元素。

    早期版本是「文件里出现一次 opacity:0 就要求全文件有 focus-within / hover:none」，
    三处都错：漏（一个类有兜底、另一个没有也放行）、误报一（``@keyframes`` 的 from、
    ``.is-folded`` 折叠态、装饰背景层被当成 hover 显隐）、误报二（``opacity: 0.5``
    这种「常驻半透明 + hover 提亮」也报，而它本来就看得见）。

    正确判据是三条同时成立：
      ① 该选择器在非 hover 规则里**基态就是隐藏**（``opacity: 0`` / ``visibility: hidden``）；
      ② 它的 hover 规则把它改成可见；
      ③ 既没有 ``:focus-within`` 兜底，也不在 ``@media (hover: none)`` 里给静态可见态。
    """
    blocks = list(_iter_css_blocks("\n".join(STYLE_RE.findall(text))))

    # 1) 基态隐藏的选择器
    hidden: set[str] = set()
    for selector, body, med in blocks:
        if ":hover" in selector or not body.strip():
            continue
        if any("hover" in m and "none" in m for m in med):
            continue  # 触屏媒体查询里的显隐是另一回事，不算基态
        if HIDDEN_ZERO_RE.search(body):
            hidden.update(_split_selectors(selector))

    if not hidden:
        return []

    # 2) 收集 hover 才显现的选择器（必须与「基态隐藏」取交集）
    hover_only: dict[str, str] = {}
    for selector, body, _med in blocks:
        if ":hover" not in selector or not body.strip():
            continue
        if not VISIBLE_IN_HOVER_RE.search(body):
            continue
        for part in _split_selectors(selector):
            if part in hidden:
                hover_only.setdefault(part, selector)

    if not hover_only:
        return []

    # 2) 收集已补兜底的选择器：:focus-within 显影，或 @media (hover:none) 里给静态可见态
    focus_ok: set[str] = set()
    touch_ok: set[str] = set()
    for selector, body, med in blocks:
        if not body.strip():
            continue
        if ":focus-within" in selector or ":focus-visible" in selector:
            focus_ok.update(_split_selectors(selector))
        if any("hover" in m and "none" in m for m in med) and VISIBLE_DECL_RE.search(body):
            touch_ok.update(_split_selectors(selector))

    hits = []
    for base, selector in sorted(hover_only.items()):
        if base in focus_ok or base in touch_ok:
            continue
        lineno = 1
        idx = text.find(selector.split(":hover")[0].strip())
        if idx > 0:
            lineno = _line_of(text, idx)
        if _exempt(lines, lineno):
            continue
        hits.append(
            f"{rel}  「{selector}」靠 :hover 才显现，无 :focus-within 与 @media (hover: none) 兜底"
        )
    return hits


def main() -> int:
    argv = sys.argv[1:]
    warn_only = "--warn" in argv
    paths = [a for a in argv if not a.startswith("-")]
    files = [Path(p) for p in paths] if paths else sorted(SRC.rglob("*.vue"))

    hits: list[str] = []
    scanned = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        rel, lines = _rel(f), text.splitlines()
        hits += check_buttons(text, rel, lines)
        hits += check_click_tags(text, rel, lines)
        hits += check_hover_fallback(text, rel, lines)

    if not hits:
        print(f"OK: 扫描 {scanned} 个 .vue 文件，未命中三类交互可达性模式。")
        return 0

    print(f"发现 {len(hits)} 处交互可达性问题（扫描 {scanned} 个文件）：")
    for h in hits:
        print("  " + h)
    print()
    print("  修法：")
    print('    1) 纯图标按钮 → 加 aria-label（可复用 tooltip 文案，tooltip 不算可访问名称）')
    print('    2) div/span 当按钮 → 改用 <button type="button">，或补 role + tabindex + @keydown')
    print("    3) hover 显隐 → 补 :focus-within 与 @media (hover: none) 双兜底")
    print("  确需例外：同一行加 a11y-allow 并写明理由")
    if warn_only:
        print("（--warn：只报告，不阻断）")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
