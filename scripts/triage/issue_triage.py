#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue 分诊：把「该不该动、谁来动、要不要决策」变成**可复核的判据**，而不是一句话。

为什么需要它
------------
本仓的开放卡里，**真正卡住的是「没人决定该不该动它」**，不是「没人写代码」：
一张卡同时可能已经交付、已经过时、需要产品拍板、或者只是某张大车的子项。
分诊要做的第一件事是**把这几类分开**，让人只花时间在真正需要他的那一类上。

三件事，边界分明
----------------
1. **回路（回流）**  GitHub 已关、CNB 还开着 ⇒ 交给 `mirror_state_sync.py` 关掉。
   本脚本**不自带写 CNB 关闭的能力**（那条路径已经存在且有回归网），只报出口径，
   避免同一动作长成两套实现。
2. **分诊（贴标签 + 一条评论）**  本脚本自己的活。一卡一次，产出**固定枚举**，
   不写自由文本、**绝不改代码**。
3. **派活闸门**  「能不能交给 NPC 自动推进」是一个**布尔函数**，不是模型感觉。
   闸门不通过就不派；闸门通过也**只是允许派**，不贴 `automerge`（见下）。

为什么「可以派活」也不贴 automerge（用户 2026-10-18 拍板）
----------------------------------------------------------
绿灯 ≠ 审查通过：`.ai-review-deep.yaml` 在 `upstream_unavailable` 时把判定 job 判成
**skipped**（不是 pass），门禁分不清「审查通过」和「审查没跑」。人工合入是最后一道
能看见这件事的关口，故**自动化到此为止**：脚本只表达「这张卡适合派」，合入永远是人。

固定枚举（写死，不许自由发挥）
------------------------------
    kind   : task | discuss | tracker | decision | stale
    size   : S | M | L
    risk   : low | medium | high
    next   : dispatch_npc | human_review | product_gate | close | archive

判据全部**机械可算**（正则 / 集合 / 计数），不调 LLM。理由与本仓一贯口径一致：
判据必须能被证伪、能被探针咬住；语义判断留给读到评论的人。

边界（写清楚，免得下一个人以为它管得更多）
------------------------------------------
- **只读 GitHub**：写 CNB 走 `--apply`，写 GitHub（标签/评论）**本脚本不做**——
  双端写入的闸门在 `claim_detect.py` / `mirror_correction.py` 那边，不在这里重开一份。
- **不判「这张卡说得清不清」**（那需要读语义）；只判「有没有验收标准 / 有没有 blocker /
  碰不碰高风险面」这类**结构信号**。
- **拿不到输入不猜**：任何一次拉取失败 ⇒ 退出码 2 且明说「结论不可信」。
  本仓 #171 / CNB #450 两次假绿的根因都是「空映射被当成没有」。
- **单轮有上限**（默认 3 张，用户拍板「每次 3 个、每天两轮」）：不是省额度，
  是**人的 review 带宽才是真瓶颈**——一次 10 张一起看，等于无差别接受。

用法
----
    python scripts/triage/issue_triage.py --report            # 只报告（默认）
    python scripts/triage/issue_triage.py --report --cnb 560  # 只看一张
    python scripts/triage/issue_triage.py --apply             # 真正贴标签 + 写评论
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / 'bridge'))

from github_cnb_issues import cnb_api  # noqa: E402

GH_REPO_DEFAULT = 'imoyao/fundmate'
CNB_REPO_DEFAULT = 'duoduobei/fundmate'

# 镜像卡的标识标签（与 `github_cnb_issues.MIRROR_LABEL` 同一口径，这里显式对齐并断言钉住）
MIRROR_LABEL = 'GitHub 同步'
LOCAL_LABEL = 'CNB 本地'

# 单轮派活上限：用户 2026-10-18 拍板「每次 3 个，每天两轮」。
#
# ⚠️ 「3」这个数**在用户 2026-10-18 当天第二次拍板前**的语义是「规模必须 S」的替代口径：
# 那天实测 198 张卡里可派 **0** 张（低风险且有验收的 17 张**全部卡在 size=M**）。
# 当时的判断是「不得为了跑满额度降标准」，于是整条派活通道一直空转——
# **按标准的派活吞吐 = 0**，而「每轮 3 张」的前提（存在可派的卡）从未成立。
# 用户随后明确要放开那条规模限制：M 也可以派，**但容量与验收口径照旧**。
# 故现在的形状是「准入放宽 + 额度不变 + 每张 PR 仍要人 review」：
# 放宽的是**能进候场的资格**，不是**同时能跑多少**。
DEFAULT_BATCH = 3
# 分诊每轮最多写**多少张卡的评论**。与派活件数解耦：分诊是「贴标签 + 一条评论」，
# 无副作用、可随时改判；派活要开分支写码，才需要卡在 3 张/轮。
# 实测（2026-10-18，198 张 open 卡）分诊要写约 130 张，3 张/轮 × 2 轮/天要跑三周，
# 期间看板仍是脏的——而**脏看板上做出的判断是不值钱的**，所以分诊先跑完是前提。
DEFAULT_TRIAGE_PER_RUN = 50

# ---------------------------------------------------------------------------
# 标签（CNB 侧；名字只允许中英文/数字/`._:-/\` 与内部空格，长度 ≤50）
# ---------------------------------------------------------------------------
TAG_KIND = {  # kind → 标签名
    'task': '分诊:可执行',
    'discuss': '分诊:需讨论',
    'tracker': '分诊:系列卡',
    'decision': '分诊:需决策',
    'stale': '分诊:疑似过时',
}
# 「需要人拍板」的标签**单独存在**：它要能被筛选器一眼捞出来，混进 kind 里做不到
# （一张卡既可以是 `分诊:可执行`，又卡在一个产品决策上）。
TAG_DECISION = '需决策'
TAG_DISPATCHED = '已派活'

# 评论幂等键：同一张卡同一份结论只发一次；结论变了（指纹变）才补一条。
MARKER_RE = re.compile(r'<!--\s*cnb-triage:\s*([0-9a-f]{12})\s*-->')

# ---------------------------------------------------------------------------
# 结构信号（全部机械可算）
# ---------------------------------------------------------------------------
# 验收标准：checkbox，或「验收 / 完成标准 / 要做的事」这类小标题
CHECKBOX_RE = re.compile(r'^\s*[-*]\s+\[( |x|X)\]', re.MULTILINE)
ACCEPTANCE_HEAD_RE = re.compile(r'^#{2,4}\s*.*(?:验收|完成标准|要做的事|交付标准)', re.MULTILINE)

# 「需要人拍板」的显式标记：写在卡面上才算，读不出来就不算。
DECISION_RE = re.compile(r'需(?:要)?(?:人)?(?:拍板|决策)|待拍板|需用户确认|产品决策|方案二选一|需(?:要)?选择')

# 「系列卡 / 大车」：正文引用 ≥2 个其他卡号（AGENTS.md 判据：正文含指向 ≥2 张其他卡的引用）
REF_RE = re.compile(r'(?<![\w/])#(\d+)')

# 「已过时」：归档标签，或正文/标题里明说「已废弃 / 不再做 / 被替代」
STALE_LABEL = '归档'
STALE_RE = re.compile(r'不再(?:做|实施|推进)|已(?:废弃|过时|被替代)|superseded')

# 高风险面：动它们需要人看，不是 AI 顺手改一行。命中即 risk=high。
#
# ⚠️ **先在正文里切掉镜像卡的溯源块再判**（`strip_mirror_header`）。实测反例：
# 10 张镜像卡的溯源块全都写着「依据 AGENTS.md」与 `scripts/bridge/…`，
# 若不切，它们会被整批判成 high —— 这正是「判据被背景文字污染」的典型形态。
HIGH_RISK_PATHS = (
    'money.py',
    'db_factory.py',
    'DATA_DOMAIN_REGISTRY',
    'conventions.md',
    'AGENTS.md',
    '.cnb.yml',
    'scripts/guard_',
    '错误信封',
    'error_code',
    'API 契约',
    '金额',
    '份额',
    '迁移',
)
# 中风险：前后端都能碰，但不动契约与钱。
#
# ⚠️ **不含「样式」二字**：实测命中率过高（「视觉」已覆盖真正需要 design 口径的卡），
# 而 DESIGN_HINT_RE 里留着它是因为那里判的是「能不能自动派」，宁可从严——两处口径
# 有意不同，不是笔误。
MEDIUM_RISK_HINTS = ('api/', 'views.py', 'models.py', 'schemas.py', '前端', 'frontend/', '数据库')

# 派活闸门**额外排除**的一类：改文案 / 改视觉必须同步 `design.md`。
# 这类活看着最小，实际是「产品口径」判断，AI 猜口味等于把设计债换成审美债——
# 与「不碰钱 / 不碰契约」同一条道理：它需要人拍板的东西是**品味**。
DESIGN_HINT_RE = re.compile(r'design\.md|design\.dark\.md|文案|措辞|配色|视觉|字号|间距|图标')

# 派活闸门**明确排除**的路径（AGENTS.md 第 2 档硬闸门）
DISPATCH_FORBIDDEN_PATHS = (
    'money.py',
    'core/money',
    'db_factory.py',
    'conventions.md',
    'AGENTS.md',
    '.cnb.yml',
    'scripts/guard_',
    'migrations/',
)


@dataclass
class Card:
    """一张 CNB 卡在分诊时需要看的全部事实（不再回头读网络）。"""

    number: int
    title: str
    body: str
    labels: list[str] = field(default_factory=list)
    state: str = 'open'
    comments: int = 0
    github_number: int | None = None

    @property
    def is_mirror(self) -> bool:
        return MIRROR_LABEL in self.labels or self.github_number is not None


@dataclass
class Verdict:
    """结论：固定枚举 + 一句人话理由（理由要能被下一个人复核）。"""

    kind: str
    size: str
    risk: str
    next: str
    need_decision: bool
    reasons: list[str] = field(default_factory=list)

    def fingerprint(self) -> str:
        raw = '|'.join([self.kind, self.size, self.risk, self.next, str(int(self.need_decision))])
        return _sha12(raw)

    def labels(self) -> list[str]:
        out = [TAG_KIND[self.kind]]
        if self.need_decision:
            out.append(TAG_DECISION)
        return out


def _sha12(raw: str) -> str:
    import hashlib

    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]


# ---------------------------------------------------------------------------
# 判据（纯函数，被 scripts/tests/test_issue_triage.py 全量覆盖）
# ---------------------------------------------------------------------------


MIRROR_HINT = 'GitHub 编号：'
MIRROR_HEADER_RE = re.compile(r'\A.*?\n---\n', re.DOTALL)


def strip_mirror_header(body: str | None) -> str:
    """切掉镜像卡顶部的溯源块（`> 🔁 …` 到第一条 `---`），只留 GitHub 原卡的正文。

    三条边界，缺一条就会误伤：

    - **只在「首个 `---` 之前出现 `GitHub 编号：`」时才切**——人工写的卡里也可能有 `---`
      分隔线，无脑切会把正文整段吃掉；
    - **没有 `---` 时原样返回**（模板改版 / 手贴的镜像卡），宁可少切也不吞正文；
    - 切**一次**（`count=1`），正文里后续的 `---` 不动。

    为什么必须切：溯源块是**建卡脚本写的模板文字**（含 `AGENTS.md`、`scripts/bridge/…`），
    把它算进判据等于「让模板决定结论」——实测会让 10+ 张无关的卡一起判成 high。
    """
    text = body or ''
    if '\n---\n' not in text:
        return text
    head = text.split('\n---\n', 1)[0]
    if MIRROR_HINT not in head:
        return text
    return MIRROR_HEADER_RE.sub('', text, count=1).lstrip('\n')


def count_refs(body: str | None, own: int) -> int:
    """正文里引用了**其他卡**的个数（排除自己）。系列卡的判据之一。

    `own` 的取值域随卡号空间而变，调用方必须传对（否则「排除自己」会失效）：
    - CNB 卡（镜像卡）：正文是 GitHub 卡的副本 ⇒ 里面的 `#N` 是 **GitHub** 编号，
      故 `own` 传 `github_number`（见 `Card.is_mirror` 与 `classify`）；
    - 非镜像卡：传自己的 CNB 编号，排除 `-1`（不排除任何卡）。
    """
    return len({int(m.group(1)) for m in REF_RE.finditer(body or '')} - {own})


def has_acceptance(body: str | None) -> bool:
    """有没有可逐条对照的验收标准（checkbox / 验收小标题）。"""
    text = body or ''
    return bool(CHECKBOX_RE.search(text)) or bool(ACCEPTANCE_HEAD_RE.search(text))


def explicit_decision(body: str | None) -> bool:
    """卡面上有没有**明写**「需拍板 / 待决策」。读不出来就不算——不猜。"""
    return bool(DECISION_RE.search(body or ''))


def looks_stale(card_body: str, title: str, labels: list[str]) -> bool:
    if STALE_LABEL in labels:
        return True
    return bool(STALE_RE.search(title)) or bool(STALE_RE.search(card_body))


# S 的判据必须是**自述的小改动**，不能是「正文里出现过一次『一行』」：
# 实测反例是 #513（同一段里既说「单行显示」又说「折两行」），照字面匹配会把它
# 判成 S 并送进派活闸门——那是一个跨两个组件的交互修复。故改用明确的自述短语。
ANYWHERE_SIZE_S_RE = re.compile(r'单(?:文件|点改动)|只(?:需)?改(?:一|单|个)处?|一行改动|typo|笔误')


def size_of(body: str | None, title: str | None, *, own: int = -1) -> str:
    """粗粒度规模：只用来决定「能不能派」，不追求精确。

    S 的判据是「卡面自己说了是改一处」——`单行` / `一处` / `一行` / 明确写了单文件路径。
    **刻意不从行数估**：卡面里的行号引用（`views.py:214`）是**引用**不是**改动面**，
    实测里两者经常差一个数量级（本仓 CNB #56 引用的文件只有 166 行）。

    `own` 与 `count_refs` 的排除对象同源（见其 docstring）——`size_of` 是唯一
    调用它的非 `classify` 路径，两处必须传同一个值，否则 `size` 与 `refs` 会各说各话。
    """
    text = f'{title or ""}\n{body or ""}'
    if ANYWHERE_SIZE_S_RE.search(text):
        return 'S'
    if count_refs(body, own) >= 2:
        return 'L'
    if len(body or '') > 4000:
        return 'L'
    return 'M'


def risk_of(body: str | None, title: str | None, labels: list[str]) -> str:
    """风险面：碰钱 / 契约 / 数据域 / 守卫 = high；碰接口与模型 = medium；其余 low。"""
    text = f'{title or ""}\n{body or ""}'
    if any(p in text for p in HIGH_RISK_PATHS):
        return 'high'
    if any(lbl in ('安全', 'auth') for lbl in labels):
        return 'high'
    if any(p in text for p in MEDIUM_RISK_HINTS):
        return 'medium'
    return 'low'


# 「整体加粗」：标题整行被 `**…**` 包住，或正文前若干行里整行加粗——
# 这是作者在说「这是一件还没想清楚的事 / 一张议题」，按 tracker 处理比按 task 处理安全。
# 代价是「标题加粗的 bug 卡」也会进 tracker：宁可少派，不可错派（错了等于替人做决定）。
WHOLE_BOLD_TITLE_RE = re.compile(r'^\s*\*\*[^*]{4,}\*\*\s*$', re.MULTILINE)


def whole_card_bold(body: str | None, title: str | None = None) -> bool:
    """「整行加粗」= 标题整行被 `**…**` 包住，或正文前 400 字里有一整行被包住。

    标题也要看：议题式写法经常**只**把标题加粗（实测样本：`**这是一件还没想清楚的事**`）。
    """
    head = (title or '').strip()
    if head.startswith('**') and head.endswith('**') and len(head) > 6:
        return True
    return bool(WHOLE_BOLD_TITLE_RE.search((body or '')[:400]))


# 派活准入档：`S` / `M`（`S` = 小改动，`M` = 中等改动）。
#
# 为什么 `L` 不在枚举里（这是唯一剩下的规模限制，且**只能由人放宽**）：
# 实测（2026-10-18，198 张）`L` 的两条判据是「正文引用 ≥2 张其他卡」与「正文 >4000 字」
# ——前者在那张卡被判成 `tracker` 之前就已经拦下了，所以**落到 `L` 且 kind=task 的卡，
# 几乎只有「正文超长」这一种**。超长正文恰恰是「一件事写不清、还挂了五件事」的卡，
# 派 AI 去做它 = 让 AI 替人补写范围，与「不替人做决定」直接冲突。
# 故 `L` 不自动放开；要放得由人在卡面上说清楚「就是这一小块」（写进验收标准即可降为可派）。
#
# ⚠️ 档位名就是 `size_of()` 的取值（`S` / `M` / `L`），**不要**发明 `SM` 这种组合名：
#    首版写成 `('S', 'SM')` 的时候，`size_of()` 只会返回 `'M'`，于是**没有一张卡命中**，
#    而看板上表现为「已放开限制、可派仍然是 0」——一个不会红的假信号。
DISPATCH_SIZE_ALLOWED = ('S', 'M')

# 派活准入的**默认**口径（`classify` / `plan` 的默认参数）：仍然最严。
# 放开是**显式动作**（调用点传 `DISPATCH_SIZE_ALLOWED` 或 `--sizes`），不是默认行为——
# 判据的默认值一旦松掉，下次没人记得「它曾经是严的」，也就没人知道该不该改回去。
DEFAULT_DISPATCH_SIZES = ('S',)


def classify(card: Card, *, sizes: tuple[str, ...] = DEFAULT_DISPATCH_SIZES) -> Verdict:
    """一张卡 → 固定枚举结论。**顺序有意义**：先判「该不该关」，再判「该不该动」。

    判据一律读 `strip_mirror_header(card.body)`（正文），不读镜像溯源块——
    否则模板文字会污染每一个结论。

    `sizes` 是**派活准入档**（默认最严 `('S',)`），只影响 `next` 是否落到
    `dispatch_npc`，不影响 kind / size / risk 三个事实判据——准入放宽不能改变
    「这张卡是什么」，只改变「这一轮允不允许派」。
    """
    body = strip_mirror_header(card.body)
    reasons: list[str] = []
    # 卡号空间：镜像卡正文是 GitHub 卡的副本，`#N` 是 GitHub 编号；
    # GitHub 卡自己就是 GitHub 编号。只有「非镜像的 CNB 卡」才用 CNB 编号排除自己。
    # 判错的后果是具体的：镜像卡若拿 CNB 编号去排除，正文里那句 `#N` 会被当成
    # 「引用了另一张卡」⇒ 系列卡误判 + 规模虚高到 L。
    # ⚠️ `or card.number`：镜像卡若**认不出** GitHub 编号（正文里没写幂等键），
    # 退化成 CNB 编号——宁可「排除对象可能不对」，也不要 `None`（那会让排除失效）。
    own = (card.github_number or card.number) if card.is_mirror else card.number
    refs = count_refs(body, own)
    need_decision = explicit_decision(body)

    # ① 疑似过时：先排除「已经在归档里的」，否则永远有人去动一张死卡
    if looks_stale(body, card.title, card.labels):
        return Verdict(
            kind='stale',
            size='S',
            risk='low',
            next='close',
            need_decision=False,
            reasons=['命中过时信号（归档标签 / 正文写着不再做 / 已被替代）'],
        )

    # ② 系列卡：正文引用 ≥2 张其他卡 ⇒ 它的价值在「保持一张能读完的总表」，
    #    派活去拆它只会把总表撕成碎片（AGENTS.md 第 3 档：完全不碰）
    if refs >= 2 or '系列' in card.title or whole_card_bold(body, card.title):
        return Verdict(
            kind='tracker',
            size='L',
            risk=risk_of(body, card.title, card.labels),
            next='archive',
            need_decision=True,
            reasons=[
                f'正文引用了 {refs} 张其他卡 / 标题自称系列卡 / 卡面整体加粗（议题式写法）：'
                '它的价值在「一张能读完的总表」，派活会把它撕成碎片'
            ],
        )

    # ③ 需决策：卡面明写「待拍板」，或本身没有任何可执行面
    acceptance = has_acceptance(body)
    if need_decision:
        return Verdict(
            kind='decision',
            size=size_of(body, card.title, own=own),
            risk=risk_of(body, card.title, card.labels),
            next='product_gate',
            need_decision=True,
            reasons=['卡面写明需要拍板/决策；拍板之前动它等于替人做决定'],
        )

    # ④ 可执行 vs 需讨论：唯一的分界是「有没有可逐条对照的验收标准」
    if acceptance:
        kind, nxt = 'task', 'dispatch_npc'
        reasons.append('有可逐条对照的验收标准（checkbox / 验收小标题）')
    else:
        kind, nxt = 'discuss', 'human_review'
        reasons.append('卡面没有可逐条对照的验收标准：先讨论清楚范围，别急着动手')

    verdict = Verdict(
        kind=kind,
        size=size_of(body, card.title, own=own),
        risk=risk_of(body, card.title, card.labels),
        next=nxt,
        need_decision=False,
        reasons=reasons,
    )

    # ⑤ 派活闸门：明确任务 + 准入规模 + 低风险 + 无护栏文件，四条全过才允许自动推进。
    #    拒绝理由要**逐条写出来**：布尔只说「没派」，说不出是规模卡住还是风险卡住。
    if verdict.next == 'dispatch_npc':
        rejects = dispatch_rejects(card, verdict, sizes=sizes)
        if rejects:
            verdict.next = 'human_review'
            verdict.reasons.extend(f'派活闸门未通过：{r}' for r in rejects)
    return verdict


def dispatch_rejects(card: Card, verdict: Verdict, *, sizes: tuple[str, ...]) -> list[str]:
    """准入判据 → **被拒理由清单**（空 = 放行）。

    返回理由而不是布尔，是因为「为什么没派」与「派了」一样需要能被复核：
    布尔只能告诉你没派，说不出是规模卡住、风险卡住，还是护栏文件卡住。

    准入（顺序即优先级）：

    1. 结论是「明确任务」（有可逐条对照的验收标准）；
    2. `size` ∈ `sizes`（默认只有 `S`；放开后为 `S` + `M`；`L` 见 `DISPATCH_SIZE_ALLOWED` 上方说明）；
    3. `risk == low`（不碰钱 / 契约 / 数据域 / 守卫）；
    4. 卡面与标题里**不出现** `DISPATCH_FORBIDDEN_PATHS` 任何一个；
    5. 不碰 `design.md` 那类**产品口径**（改文案 / 改视觉属于品味，AI 猜口味等于把设计债
       换成审美债）。
    """
    reasons: list[str] = []
    if verdict.kind != 'task':
        reasons.append(f'不是明确任务（kind={verdict.kind}）')
    if verdict.size not in sizes:
        reasons.append(f'规模 {verdict.size} 超出本轮准入 {"/".join(sizes)}')
    if verdict.risk != 'low':
        reasons.append(f'风险面 {verdict.risk}（碰钱 / 契约 / 数据域 / 守卫）')
    text = f'{card.title}\n{strip_mirror_header(card.body)}\n{" ".join(card.labels)}'
    hits = [p for p in DISPATCH_FORBIDDEN_PATHS if p in text]
    if hits:
        reasons.append(f'卡面出现护栏文件 {hits}')
    elif DESIGN_HINT_RE.search(text):
        reasons.append('改文案 / 改视觉属于产品口径（需同步 design.md），不自动派')
    return reasons


def can_dispatch(card: Card, verdict: Verdict, *, sizes: tuple[str, ...] = ('S',)) -> bool:
    """**派活闸门**（布尔，不掺感觉）：严格的四问全过。

    默认仍取 `sizes=('S',)`（最严口径）；运行时想放开规模时，请用
    `dispatch_rejects(..., sizes=DISPATCH_SIZE_ALLOWED)`——**放开只发生在调用点**，
    这样「今天凭什么多派了一类」写在一处、可被 diff 审出来，而不是散进判据里。
    """
    return not dispatch_rejects(card, verdict, sizes=sizes)


def plan(
    cards: list[Card],
    *,
    per_run: int = DEFAULT_TRIAGE_PER_RUN,
    dispatch_cap: int = DEFAULT_BATCH,
    sizes: tuple[str, ...] = DEFAULT_DISPATCH_SIZES,
    written: set[int] | None = None,
) -> tuple[list[tuple[Card, Verdict]], int, int]:
    """算出这一轮要写哪些卡，`(todo, skipped_by_quota, skipped_already_written)`。

    两条上限**分开**（这是本条口径的关键）：

    - `per_run`：**分诊写入**的卡数上限（默认 50）——贴标签 + 一条评论，无副作用；
    - `dispatch_cap`：**派活**的卡数上限（默认 3，用户拍板「每次 3 个」）——
      派活要开分支写码，且每张 PR 都要人 review，超了就变成无差别接受。

    `written`：**卡面上已有结论**（评论里带着指纹 + 标签齐全）的卡号集合。
    传了它，额度就按「**真正要写的张数**」计，而不是按「挑了几张」计。

    排序按编号升序：老的卡拖得最久。

    `skipped_by_quota` 必须被调用方**报出来**：被额度挡掉不等于「没有更多要分诊的卡」
    ——把两者混为一谈，就是「拿不到 ≠ 没有」的又一个变体。

    ⚠️ 为什么额度必须按**写入**计（2026-10-19 实测踩过）
    ---------------------------------------------------
    首版按「挑了几张」计，于是：第一批卡写完之后，下一轮仍从编号最小的 50 张挑起，
    它们全部「结论未变，跳过」⇒ `picked` 已经满 50 ⇒ **后面所有卡都被判「因额度未处理」**，
    而实际写入是 0。实测输出：

        🎉 本轮检查 153 张，写入 0 张（分诊上限 50、派活上限 3）
        ⏸️  另有 103 张因额度未处理（不是「已分诊完」，下一轮继续）

    这行字**每个字都是真的**，结论却是假的：卡住的不是额度，是「回头挑已经写过的卡」。
    看板从此永远停在 50 张，而那 103 张永远不会被处理——与 CNB #450「缓存当判据」
    同一形态：**判据错的时候，输出只会更响亮地复述错结论。**

    另：被「结论未变」跳过的卡不该算进 `skipped_by_quota`——那是排队与实质的分界，
    混在一起就分不清「该加额度」还是「该修判据」。
    """
    done = written or set()
    todo = [(c, classify(c, sizes=sizes)) for c in cards if c.state == 'open']
    todo.sort(key=lambda cv: cv[0].number)
    dispatched = 0
    wrote = 0
    picked: list[tuple[Card, Verdict]] = []
    skipped = 0
    already = 0
    for card, verdict in todo:
        if card.number in done:
            # 已写过：不占额度，也不必排队——它下一轮根本不会被写。
            already += 1
            continue
        if wrote >= per_run:
            # 先判分诊上限，再判派活上限：被分诊额度挡掉的卡**还没被写**，
            # 若先给派活计数，下一轮它会既没写入又占掉一个派活名额。
            skipped += 1
            continue
        if verdict.next == 'dispatch_npc':
            if dispatched >= dispatch_cap:
                verdict = _downgrade_for_quota(verdict, reason=f'本轮派活额度已用尽（{dispatch_cap} 张）')
            else:
                dispatched += 1
        picked.append((card, verdict))
        wrote += 1
    return picked, skipped, already


def _downgrade_for_quota(verdict: Verdict, *, reason: str) -> Verdict:
    """额度用尽时**降级成 human_review**，而不是照写 `dispatch_npc`。

    为什么不直接跳过：跳过的卡下一轮还会以「可派」的面貌出现，看板上一直挂着
    「等派活」其实是「排队中」，读的人分不清。降级并写明理由，卡面就说了真话。
    """
    return Verdict(
        kind=verdict.kind,
        size=verdict.size,
        risk=verdict.risk,
        next='human_review',
        need_decision=verdict.need_decision,
        reasons=[*verdict.reasons, reason],
    )


def needs_write(card: Card, verdict: Verdict, existing_markers: set[str]) -> bool:
    """结论相对「卡面上已有的东西」是否有变化——变了才写，避免刷屏。"""
    if verdict.fingerprint() not in existing_markers:
        return True
    missing = [lbl for lbl in verdict.labels() if lbl not in card.labels]
    return bool(missing)


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def render_comment(card: Card, verdict: Verdict) -> str:
    """一卡一条评论：结论展开、明细折叠（同 #563 的回写口径）。"""
    tag = '、'.join(f'`{lbl}`' for lbl in verdict.labels())
    rows = '\n'.join(f'- {r}' for r in verdict.reasons)
    decision_block = ''
    if verdict.need_decision:
        decision_block = (
            '\n## ⚠️ 这张卡需要人拍板\n\n'
            '已挂 `需决策` 标签。**拍板之前不要动手**——动手等于替人做决定，'
            '回头还要返工，比先问你一句贵得多。\n\n'
            '请直接在评论区写结论（选哪个方案 / 做还是不做），我会按结论继续。\n'
        )
    dispatch_block = ''
    if verdict.next == 'dispatch_npc':
        dispatch_block = (
            '\n## 可以派活\n\n'
            '这张卡过了派活闸门（明确任务 + 规模 S + 低风险 + 不碰护栏文件）。'
            '**但不会自动合入**：PR 出来后仍要人工 merge（用户 2026-10-18 拍板）。\n'
        )
    return '\n'.join(
        [
            f'## 分诊结论（{datetime.now(UTC):%Y-%m-%d}）',
            '',
            '| kind | size | risk | next |',
            '| --- | --- | --- | --- |',
            f'| `{verdict.kind}` | `{verdict.size}` | `{verdict.risk}` | `{verdict.next}` |',
            '',
            f'建议标签：{tag}',
            '',
            rows,
            decision_block,
            dispatch_block,
            '<details><summary>判据是什么（点开看）</summary>',
            '',
            '- `kind=task` 的唯一判据是**卡面有可逐条对照的验收标准**（checkbox / 验收小标题）；',
            '  没有就是 `discuss`——先讨论清楚范围，而不是猜着做。',
            '- `kind=tracker` 的判据是**正文引用 ≥2 张其他卡**：它是汇总表，派活会把它撕成碎片。',
            '- `risk=high` 的判据是**卡面出现钱 / 契约 / 数据域 / 守卫文件名**。',
            '- 派活闸门 = `task` + `size=S` + `risk=low` + 不碰护栏文件，四问全过。',
            '- 本结论由脚本机械算出（`scripts/triage/issue_triage.py`），**不调 LLM**，可复核。',
            '',
            '</details>',
            '',
            f'<!-- cnb-triage: {verdict.fingerprint()} -->',
        ]
    ).replace('\n\n\n', '\n\n')


# ---------------------------------------------------------------------------
# 网络
# ---------------------------------------------------------------------------


def _cnb_repo() -> str:
    return os.environ.get('CNB_REPO') or os.environ.get('CNB_REPO_SLUG') or CNB_REPO_DEFAULT


def list_open_cards() -> list[dict[str, Any]]:
    """列 CNB open 卡（分页拉全）。**任何一页拉失败都要抛**——调用方必须能区分
    「没有卡」与「拿不到卡」（本仓 #171 / CNB #450 两次假绿都是把后者当成前者）。

    `github_cnb_issues.list_cnb_issues()` 没有失败态（它把异常吞掉返回部分结果），
    故这里不复用它，而是自带一份**不吞异常**的分页。
    """
    repo = _cnb_repo()
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        # 查询参数是下划线的 `page_size`（连字符会被静默忽略成默认 10）
        qs = urllib.parse.urlencode({'page': page, 'page_size': 100, 'state': 'open'})
        try:
            batch = cnb_api(f'/{repo}/-/issues?{qs}') or []
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            print(f'⚠️ CNB open 卡列表拉取失败（page={page}）：{exc}')
            raise
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def get_card(number: int) -> dict[str, Any]:
    """取单卡详情。**必须走这里才有 `body`**（CNB 列表接口不返回正文）。"""
    return cnb_api(f'/{_cnb_repo()}/-/issues/{number}') or {}


def list_comments(number: int) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode({'page': 1, 'page_size': 100})
    try:
        data = cnb_api(f'/{_cnb_repo()}/-/issues/{number}/comments?{qs}')
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f'⚠️ 读 CNB #{number} 评论失败：{exc}')
        raise
    if isinstance(data, dict):
        for key in ('data', 'items', 'list'):
            if isinstance(data.get(key), list):
                return list(data[key])
        return []
    return list(data or [])


def existing_markers(comments: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for c in comments:
        for m in MARKER_RE.finditer(str(c.get('body') or '')):
            out.add(m.group(1))
    return out


def _write(path: str, payload: dict[str, Any] | None = None) -> None:
    """CNB 写接口（POST）。凭据 = 构建内注入的 `CNB_TOKEN`。"""
    token = os.environ.get('CNB_TOKEN')
    if not token:
        raise RuntimeError('缺少 CNB_TOKEN：--apply 需要写凭据（本地跑请 export）')
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(f'https://api.cnb.cool{path}', data=body, method='POST')
    req.add_header('Accept', 'application/vnd.cnb.api+json')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


# ---------------------------------------------------------------------------
# GitHub 侧（兜底通道；`--backend github`）
# ---------------------------------------------------------------------------
#
# WHY 要有第二条通道（2026-10-19）
# --------------------------------
# 看板上「一张标签都没落」的原因是**调度链断了**（cron 只剩建卡），不是判据错。
# 而 CNB 的 cron 只能挂一个分支、只能在 cnb.cool 跑——断一次就静默停摆，且它挂着的
# 全部作业一起停。分诊的输入（卡面正文）在 **GitHub 主仓**，输出（标签 / 评论）落在
# **CNB 镜像卡**，所以真正必要的只有「标签落在某处」。两条通道各自独立：
#
#   - `--backend cnb`（默认）：写给 CNB 镜像卡，给人在这里读；
#   - `--backend github`：写给 GitHub 原卡，**同一个指纹、同一份内容**，靠
#     `<!-- cnb-triage: hash -->` 去重（两侧各写一次，互不影响）。
#
# 边界不变：**只写标签与评论，绝不改代码、不建分支、不贴 automerge。**


def _gh_repo() -> str:
    return os.environ.get('GITHUB_REPO') or GH_REPO_DEFAULT


def gh_api(path: str, *, method: str = 'GET', payload: dict[str, Any] | None = None) -> Any:
    """调 GitHub REST。分页参数是 GitHub 自己的 `page` / `per_page`。

    **读不要凭据、写必须要凭据**（与 `--apply` 的语义一致）：
    - 没有 token 时只允许 GET（匿名 60 次/时/IP）——`--report` 才能在本地/CI 上跑；
    - 要写（POST）而没 token ⇒ **显式报错**，不静默降级成「读到了、没写」。
      `--apply --backend github` 少了这个检查，会变成「贴了标签」的假绿：日志一路 ✅，
      实际一个 401 都没发出去。
    """
    token = os.environ.get('GITHUB_TOKEN')
    if method != 'GET' and not token:
        raise RuntimeError('缺少 GITHUB_TOKEN：`--apply --backend github` 需要写凭据')
    url = f'https://api.github.com{path}'
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'fundmate-issue-triage')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def list_github_open_cards() -> list[dict[str, Any]]:
    """列 GitHub open issue（分页拉全）。**任何一页失败都要抛**——见 `list_open_cards()`。"""
    repo = _gh_repo()
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = gh_api(f'/repos/{repo}/issues?state=open&per_page=100&page={page}') or []
        # ⚠️ GitHub 的 `issues` 端点**把 PR 也当 issue 返回**：只留真卡。
        batch = [it for it in batch if 'pull_request' not in it]
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        if page > 50:  # 5000 张上限，防跑飞
            print('⚠️ GitHub open 卡超过 5000 张，本轮只处理前 5000 张 —— 结论不完整')
            raise RuntimeError('too many github issues')
    return out


def _github_number_in(body: str | None) -> int | None:
    """镜像卡正文里的 `GitHub 编号：#N`（建卡脚本写的幂等键）。

    ⚠️ 实际正文是 ``GitHub 编号：`#2348` `` —— 编号外面套着**反引号**。
    首版只写 ``GitHub 编号：\\s*#(\\d+)``，于是**一张都认不出来**（实测 0/106），
    而认不出的后果是静默的：`is_mirror` 退化成看标签、卡号空间拿错、
    `check_duplicate_mirrors` / 回流也一起失效。故这里容一个可选的 `` ` ``。
    """
    m = re.search(r'GitHub 编号：\s*`?#(\d+)', body or '')
    return int(m.group(1)) if m else None


def build_github_cards(*, only: int | None = None, limit: int = 10_000) -> tuple[list[Card], bool]:
    """把 GitHub issue 装成同一套 `Card`，让他们走**同一份判据**。

    两个必须对齐的点，否则结论会和 CNB 侧不同（那就成两套真话）：

    1. **引用号归一**：镜像卡正文是 GitHub 卡的副本，里面的 `#N` **就是 GitHub 编号**；
       而 CNB 卡里写的是 CNB 编号（同一个 `#N` 在两侧指向不同卡）。故这里用
       `github_number` 做参照（`count_refs` 的排除对象）。
    2. **正文原样**：镜像卡切过溯源块，GitHub 原卡本来就没有，不需要补。
    """
    cards: list[Card] = []
    complete = True
    for item in list_github_open_cards():
        number = int(item['number'])
        if only is not None and number != only:
            continue
        labels = [str(lbl.get('name') or '') for lbl in (item.get('labels') or [])]
        cards.append(
            Card(
                number=number,
                title=item.get('title') or '',
                body=item.get('body') or '',
                labels=labels,
                state=str(item.get('state') or 'open'),
                comments=int(item.get('comments') or 0),
                github_number=number,
            )
        )
        if len(cards) >= limit:
            break
    return cards, complete


def _markers(card: Card, backend: str) -> set[str]:
    """卡面上已写过的结论指纹：CNB 读 CNB 评论，GitHub 读 GitHub 评论。"""
    if backend != 'github':
        return existing_markers(list_comments(card.number))
    out: set[str] = set()
    for page in (1, 2):
        batch = gh_api(f'/repos/{_gh_repo()}/issues/{card.number}/comments?per_page=100&page={page}') or []
        for c in batch:
            out |= existing_markers([c])
        if len(batch) < 100:
            break
    return out


def gh_ensure_labels(names: list[str]) -> None:
    """标签不存在就建（平台对已存在的标签返 422，忽略即可）。"""
    for name in names:
        try:
            gh_api(f'/repos/{_gh_repo()}/labels', method='POST', payload={'name': name})
        except urllib.error.HTTPError as exc:
            if exc.code != 422:
                raise


def gh_add_labels(number: int, labels: list[str]) -> None:
    if labels:
        gh_api(f'/repos/{_gh_repo()}/issues/{number}/labels', method='POST', payload={'labels': labels})


def gh_post_comment(number: int, body: str) -> None:
    gh_api(f'/repos/{_gh_repo()}/issues/{number}/comments', method='POST', payload={'body': body})


def ensure_label(name: str) -> None:
    """标签不存在就建（CNB 拒绝重复建时返回错误，忽略即可）。"""
    try:
        _write(f'/{_cnb_repo()}/-/labels', {'name': name, 'description': '分诊结论（自动挂）'})
    except urllib.error.HTTPError:
        pass


def add_labels(number: int, labels: list[str]) -> None:
    if not labels:
        return
    _write(f'/{_cnb_repo()}/-/issues/{number}/labels', {'labels': labels})


def post_comment(number: int, body: str) -> None:
    _write(f'/{_cnb_repo()}/-/issues/{number}/comments', {'body': body})


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def build_cards(*, only: int | None, limit: int, with_body: bool = True) -> tuple[list[Card], bool]:
    """拉 open 卡 → `(cards, complete)`。

    `with_body=False` 时退化成「只拿列表」（不取正文），行为会失真，
    故只用于自测；正式路径默认取正文。
    """
    cards: list[Card] = []
    complete = True
    raw = list_open_cards()
    for item in raw:
        number = int(item['number'])
        if only is not None and number != only:
            continue
        labels = [
            ((lbl or {}).get('name') if isinstance(lbl, dict) else str(lbl)) for lbl in (item.get('labels') or [])
        ]
        body = item.get('body')
        if with_body and body is None:
            try:
                detail = get_card(number)
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                print(f'⚠️ 取 CNB #{number} 正文失败：{exc} —— 该卡本轮不判（不猜）')
                complete = False
                continue
            body = detail.get('body')
            if not labels:
                labels = [
                    ((lbl or {}).get('name') if isinstance(lbl, dict) else str(lbl))
                    for lbl in (detail.get('labels') or [])
                ]
        cards.append(
            Card(
                number=number,
                title=item.get('title') or '',
                body=body or '',
                labels=labels,
                state=item.get('state') or 'open',
                comments=int(item.get('comments') or 0),
                github_number=_github_number_in(body),
            )
        )
        if len(cards) >= limit:
            break
    return cards, complete


def run(
    *,
    dry_run: bool,
    only: int | None,
    batch: int,
    per_run: int,
    sizes: tuple[str, ...] = DEFAULT_DISPATCH_SIZES,
    stamp_labels: bool = False,
    backend: str = 'cnb',
) -> int:
    gh = backend == 'github'
    if gh:
        cards, complete = build_github_cards(only=only, limit=10_000)
    else:
        cards, complete = build_cards(only=only, limit=10_000)
    if not cards:
        # ⚠️ 这里**不能**说「全部干净」：要么真的没有 open 卡，要么是拉取失败。
        if complete:
            print('✅ 没有需要分诊的 open 卡')
            return 0
        print('❌ 拉不到 open 卡，本次结论不可信（不得当成「没有卡需要分诊」）')
        return 2

    written = 0
    printed = 0
    # 先扫一遍「卡面上已有结论」的卡：额度必须按**实际要写的张数**计（见 `plan()` 的注释）。
    # 一次额外的评论读取换掉「永远回头挑同一批已写过的卡」——不扫就必然复现那个死循环。
    done: set[int] = set()
    if not dry_run:
        for c in cards:
            if c.state != 'open':
                continue
            try:
                if not needs_write(c, classify(c, sizes=sizes), _markers(c, backend)):
                    done.add(c.number)
            except (urllib.error.HTTPError, urllib.error.URLError):
                # 读不到评论 ⇒ 不当成「已写过」（宁可重写一条幂等评论，也不让它永远不处理），
                # 但整轮结论要标为不完整。
                complete = False
    todo, skipped, already = plan(
        cards, per_run=per_run, dispatch_cap=batch, sizes=sizes, written=done
    )
    # 被闸门（不是额度）挡掉的明确任务：**必须报数**。放开规模限制这件事的意义全在这里 ——
    # 「可派 0」与「有 17 张但全被规模挡住」看起来都是 0，只有报出后者才知道该不该动判据。
    blocked = [
        (c, v)
        for c, v in todo
        if v.kind == 'task' and v.next == 'human_review' and f'规模 {v.size}' in ' '.join(v.reasons)
    ]
    for card, verdict in todo:
        if dry_run:
            printed += 1
            print(
                f'  [DRY-RUN] #{card.number} {verdict.kind}/{verdict.size}/{verdict.risk}/{verdict.next}'
                f'{" +需决策" if verdict.need_decision else ""}  {(card.title or "")[:40]}'
            )
            continue
        try:
            marks = _markers(card, backend)
        except (urllib.error.HTTPError, urllib.error.URLError):
            complete = False
            continue
        if not needs_write(card, verdict, marks):
            print(f'  ⏭️  #{card.number} 结论未变，跳过')
            continue
        labels = verdict.labels()
        if stamp_labels and verdict.next == 'dispatch_npc':
            # `已派活` 是**排队标记**：额度用尽被降级的卡不挂（它还没排上），
            # 派出去之后下一轮仍会命中（标签不会让结论变，`needs_write` 因此把它算作「已写」）。
            labels = [*labels, TAG_DISPATCHED]
        if gh:
            gh_ensure_labels(labels)
            gh_add_labels(card.number, labels)
            gh_post_comment(card.number, render_comment(card, verdict))
        else:
            for lbl in labels:
                ensure_label(lbl)
            add_labels(card.number, labels)
            post_comment(card.number, render_comment(card, verdict))
        written += 1
        tag = 'GitHub #' if gh else '#'
        print(f'  ✅ {tag}{card.number} 已挂 {labels} 并留分诊评论')

    if dry_run:
        print(f'[DRY-RUN] 本轮检查 {len(cards)} 张，可分诊 {printed} 张（--apply 才会真写）')
    else:
        print(f'🎉 本轮检查 {len(cards)} 张，写入 {written} 张（分诊上限 {per_run}、派活上限 {batch}）')
    if already:
        # 与「额度」分开报：这三种「没动它」的原因完全不同，混在一起就分不清该加额度还是改判据。
        print(f'✅ 另有 {already} 张结论已在卡上，本轮无需重写')
    if skipped:
        # 必须说出来：被额度挡掉 ≠ 没有更多要分诊的卡
        print(f'⏸️  另有 {skipped} 张因额度未处理（不是「已分诊完」，下一轮继续）')
    if blocked:
        # 与「额度」分开报：额度是排队，闸门是判据。混在一起读，永远分不清该加人还是改判据。
        detail = '；'.join(f'#{c.number}({v.size})' for c, v in blocked[:10])
        more = '' if len(blocked) <= 10 else f' …共 {len(blocked)} 张'
        print(f'🚧 另有 {len(blocked)} 张明确任务被**派活闸门**挡下（非额度）：{detail}{more}')
        print(f'   本轮准入规模 = {" / ".join(sizes)}（`--sizes` 可调；L 需要人逐张判断，不自动放开）')
    if not complete:
        print('⚠️ 数据不完整，本次结论不可信（上方有拉取失败记录）')
        return 2
    return 0


# 规模档的合法取值。**`L` 不在默认准入里**，但允许显式传入（人逐张判断时用）。
_ALL_SIZES = ('S', 'M', 'L')


def parse_sizes(raw: str) -> tuple[str, ...]:
    """`'S/SM'` → `('S','SM')`；`'S/M'` → `('S','M')`（兼容逐档写法）。

    非法值**直接抛**而不是静默忽略：`--sizes=S,X` 若被忽略成 `S`，调用方会以为放开了，
    实际一张都没多派——那正是「拿不到 ≠ 没有」的同族形态（#171 / CNB #450）。
    """
    out: list[str] = []
    for token in str(raw or '').replace(',', '/').split('/'):
        t = token.strip().upper()
        if not t:
            continue
        if t in _ALL_SIZES:
            out.append(t)
        elif set(t) <= set(_ALL_SIZES):
            # `SM` / `LSM` 这类组合写法：拆成单档。**拆完必须是单字符档位**
            # （`size_of()` 的取值域），否则放开会静默不生效（见 DISPATCH_SIZE_ALLOWED 注释）。
            out.extend(sorted(set(t), key=_ALL_SIZES.index))
        else:
            raise ValueError(f'未知的规模档 `{t}`（只允许 S / M / L 或其组合，如 S、S/M、SM）')
    if not out:
        raise ValueError('`--sizes` 不能为空（空 = 一张都不许派，通常不是本意）')
    return tuple(dict.fromkeys(out))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Issue 分诊：固定枚举结论 + 只读判据（不调 LLM）')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--report', action='store_true', help='只报告（默认）')
    group.add_argument('--apply', action='store_true', help='真正贴标签 + 写评论')
    parser.add_argument('--cnb', type=int, default=None, help='只看这张卡（调试；编号按 --backend 解释）')
    parser.add_argument(
        '--backend',
        choices=('cnb', 'github'),
        default='cnb',
        help=(
            '写哪一侧（默认 cnb）：`cnb` 写 CNB 镜像卡（人在这里读），`github` 写 GitHub 原卡'
            '（CNB 调度断掉时的兜底通道）。判据与指纹两侧完全一致，互不覆盖。'
        ),
    )
    parser.add_argument('--batch', type=int, default=DEFAULT_BATCH, help=f'单轮**派活**上限（默认 {DEFAULT_BATCH}）')
    parser.add_argument(
        '--per-run',
        type=int,
        default=DEFAULT_TRIAGE_PER_RUN,
        help=f'单轮**分诊写入**上限（默认 {DEFAULT_TRIAGE_PER_RUN}）',
    )
    parser.add_argument(
        '--sizes',
        default='/'.join(DEFAULT_DISPATCH_SIZES),
        help=(
            '派活准入的规模档，`/` 分隔（默认 '
            f'{" / ".join(DEFAULT_DISPATCH_SIZES)}；可选 S / M / L）。'
            '`L` 需要人逐张判断，**不要**在流水线里打开'
        ),
    )
    parser.add_argument(
        '--stamp-dispatched',
        action='store_true',
        help=f'给本轮放行派活的卡挂 `{TAG_DISPATCHED}` 标签（排队标记，默认不挂）',
    )
    args = parser.parse_args(argv)
    return run(
        dry_run=not args.apply,
        only=args.cnb,
        batch=args.batch,
        per_run=args.per_run,
        sizes=parse_sizes(args.sizes),
        stamp_labels=args.stamp_dispatched,
        backend=args.backend,
    )


if __name__ == '__main__':
    sys.exit(main())
