#!/usr/bin/env python3
"""「认领」识别：CNB 侧正在动的卡 / PR → GitHub 侧挂标签（源 CNB #179）。  <!-- cross-repo-ref-allow -->

为什么需要它
------------
CNB 与 GitHub 是两个独立的话题空间，**同一张卡在两侧可以同时被人动手**：

    GitHub 侧的人：打开 fundmate 的 issue 列表，看见一张没被 assign 的卡 →
                   开始改它的代码 → 改到一半
    CNB 侧的人  ：在同一张卡的 CNB 镜像卡上讨论 / 在 CNB 上开分支写代码

两边都在改同一件事，**而没有任何一方能看见另一方**。实测已经发生过一次：
CNB 侧的 PR #180 与 PR #181 是同一张卡（CNB #179）的**两套并行解法**，
都从 `dev` 切出来、改了同一批文件，最后要人工逐处消解冲突（`724e5add`）。

为什么不能靠「实时事件」
------------------------
用户最初的诉求是「**实时感知**，不能靠每个小时去拉或推」。这个诉求在**当前凭据拓扑下
做不到**，而且不是「还没做」，是**结构上做不到**：

| 方向 | 有没有凭据 | 结论 |
|---|---|---|
| CNB 构建 → 写 GitHub | ❌ 构建 `env` 里只有 `CNB_*`，`api.github.com` 匿名 POST 返 401 | CNB **不能**在有人动卡时立刻去 GitHub 挂标签 |
| GitHub Actions → 读 CNB | ✅ `GITHUB_TOKEN` 自动注入（且 CNB 公开仓匿名可读） | **这条通**，但它只由 GitHub 侧的事件 / cron 触发 |
| GitHub 事件 → 反向叫醒 CNB 流水线 | ❌ 本仓没有装 GitHub App，也没有 webhook 中继 | 做不到 |

所以能做的是**把延迟压到分钟级、并让「过期」这件事自己说话**：

- **主通道（GitHub 侧，事件驱动）**：`.github/workflows/claim-sync.yml` 订
  `issues` / `pull_request` 的 `opened` / `synchronize` / `reopened` / `assigned` /
  `labeled`。**GitHub 上有人一动那张卡，几十秒内就挂上 `CNB 处理中`。**
  这是真正「实时」的那一半，且不需要 CNB 干任何事。
- **兜底通道（CNB 侧，`$` 段 push）**：把上面的结论写回 CNB 镜像卡的评论区。
  它跑在 push 上（不是定时），所以有人推代码就会触发——**「干了活就顺手报一次」，
  不是「每小时巡逻一次」**。
- **反方向的真缺口（本轮补齐）**：CNB 侧正在干活时**怎么让同一次 push 顺手挂上 GitHub
  标签**——就是本脚本。凭据来自 Secret 仓库的 `GITHUB_PAT`（与 git-sync 同一份），
  挂在**插件任务级**（见 `.cnb.yml` 的 `claim-sync` 收尾阶段）。
  没有它，CNB 侧的改动必须等 GitHub 侧下一个事件，最长延迟 = 下一次 GitHub 有人动手。

「实时」的诚实口径
------------------
- GitHub 侧：**事件驱动，秒级**（挂标签那个方向）；
- CNB 侧：**push 驱动，分钟级**，且**没有新 push 就不会刷新**——这不是「巡逻」；
- 所以标签带**认领时间**，且 GitHub 侧 workflow 在每次事件里**重新评估**
  （见 `reopen` 判定）：标签过期会**自己消失**，而不是一直挂着骗人。

认领的语义（一个人话版的判据）
------------------------------
不看「谁说了什么」，只看**已经发生的事实**：

1. **CNB 侧存在 head 或 base 指向这张卡的 PR**（PR 正文写 `#179` / 完整 URL / 镜像卡编号）
   —— 有人在 CNB 上开分支干活了；
2. **CNB 镜像卡本身就是 open**，且**不是**「人工卡」——镜像卡 open 说明 GitHub 原卡 open。

满足 1 ⇒ 判定「CNB 处理中」，在 GitHub 原卡挂 `CNB 处理中` 标签 + 一条**只发一次**的认领评论。

**刻意不做的判定**：不看「有没有人 `assigned`」——assignee 是意图不是事实，
而且 GitHub 侧的 `assigned` 已经由 GitHub 自己的事件管；也不看「评论里有没有说在改」，
那句话现在说的人下次就不算数了。**事实优先于声明**（与 AGENTS.md 一贯口径一致）。

幂等
----
两条独立幂等键：

- **标签**：`POST /labels`（GitHub 原生幂等，重复挂不报错、不会重复）；
- **评论**：正文末尾带隐藏标记 `<!-- cnb-claim: github=N prs=… -->`，
  回写前先把目标 issue 的评论扫一遍收标记——**认领评论不改写、不重发**。
  认领解除时**不删评论**（历史留着），只摘标签。

用法
----
    # 只报告（默认，不写任何东西）
    python scripts/bridge/claim_detect.py --report

    # 真正执行（需要 GITHUB_PAT）
    python scripts/bridge/claim_detect.py --apply

    # 仅本轮：只看这张 CNB 卡（调试）
    python scripts/bridge/claim_detect.py --report --cnb 179

依赖：纯标准库（urllib），与同目录其它 bridge 脚本一致。
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
from typing import Any

SCRIPT_DIR = __import__('pathlib').Path(__file__).resolve().parent

CNB_REPO_DEFAULT = 'duoduobei/fundmate'
GITHUB_REPO_DEFAULT = 'imoyao/fundmate'

# GitHub 侧的认领标签名。**不可改**——改名等于所有已挂的标签变成孤儿，
# 且解除逻辑再也认不出自己挂过的那些。
CLAIM_LABEL = 'CNB 处理中'

# 认领评论的隐藏幂等标记。**不可改**（同 `cnb-backfill:` 的道理）。
MARKER_PREFIX = '<!-- cnb-claim:'
MARKER_RE = re.compile(r'<!--\s*cnb-claim:\s*github=(\d+)\s+prs=([0-9,\s]*)\s*-->')

# 镜像卡正文里的 GitHub 编号（与 github_cnb_issues.py 同一形状，**不抄第二份正则**会
# 引入 import 耦合，故此处显式对齐并加断言钉住——见 scripts/tests/test_claim_detect.py）。
GITHUB_NUMBER_RE = re.compile(r'GitHub 编号：`#(\d+)`')

# 镜像卡正文里的原链接（`resolve_github_number` 用的那条）。
# ⚠️ 仓库名要**钉成本仓**，不能只匹配 `github.com/<任意>/<任意>/issues/N`：
# 卡面正文里常有别的仓库链接（上游项目、依赖仓库），泛匹配会把**别人的 issue 编号**
# 当成这张卡的 GitHub 编号，于是标签挂到不相干的卡上——那是写路径最贵的一种错。
GITHUB_URL_RE = re.compile(rf'https://github\.com/{re.escape(GITHUB_REPO_DEFAULT)}/issues/(\d+)')

# 本地卡正文声明（D52）——本地卡不镜像，也就没有 GitHub 侧可挂标签的地方
LOCAL_MARKER_RE = re.compile(r'^\s*>\s*(?:📍\s*)?\*\*CNB 本地卡\*\*', re.MULTILINE)
LOCAL_LABEL = 'CNB 本地'
MIRROR_LABEL = 'GitHub 同步'

# ---- 从 PR 里认「它在做哪张卡」的三条形态 -------------------------------------
#
# ⚠️ **认不出就跳过（宁可漏，不可错）**：认错了会把 `CNB 处理中` 挂到一张不相干的卡上，
# 而那张卡的下一位读者会因此**不去动它**——比漏挂一个标签贵得多。
#
# 三条形态按可靠性排序：
#
#   1. **完整 URL** `https://cnb.cool/<slug>/-/issues/N` —— 唯一无歧义；
#   2. **限定写法** `CNB #N` / `CNB 的 #N` / `CNB 侧 #N` / `CNB 卡 #N` —— 明确挂了源；
#   3. **标题里的裸 `#N`** —— 标题就是「这件事是什么」，故这里可以直接收。
#
# 而**正文里的裸 `#N` 一律不收**。这条是实测逼出来的：初版收正文裸号，
# 在 5 个真实 PR（CNB #180 / #181 / #182 / #210 / #238）上逐行核对后，
# 抽出的 7 个裸号里 **4 个是别的东西**：
#
#   | 真实原文 | 抽出的 | 那其实是 |
#   |---|---|---|
#   | ``上一张 PR #210 已合入 dev`` | 210 | **CNB PR** 编号，不是卡 |
#   | ``（#1403 的形态）`` | 1403 | **GitHub** 侧卡号 |  <!-- cross-repo-ref-allow -->
#   | ``撞 #1403 同族限流`` | 1403 | GitHub 侧卡号 |  <!-- cross-repo-ref-allow -->
#   | ``#2034 口径 tooltip`` | 2034 | GitHub 侧卡号 |  <!-- cross-repo-ref-allow -->
#
# 而 CNB 编号连续、镜像卡从 #5 起 ⇒ 这些号在 CNB 侧**确实存在同号卡** ⇒ 挂错。
#
# **为什么不再加行级启发式**：试过四条（行内 `PR #N` / GitHub 字样 / 行内代码 / 加粗），
# 都不够——真实行文里 `**（#1403 的形态）`（加粗没闭合）、`撞 #1403 同族限流`（纯散文）
# 都躲得过去。继续加就是在拟合今天这 5 个样本，正是本仓「判据要能被证伪、不要拟合」
# 所反对的。故改用**结构性**判据：**标题 = 这件事是什么，正文 = 怎么做的**。
#
# **已知假阴性**：正文写裸 `#106`、且标题没写卡号的 PR 会被漏掉 ⇒ 少挂一个标签，
# 下一个人仍能从 PR 里看到这件事。可以接受。
CNB_URL_RE = re.compile(r'https://cnb\.cool/([\w.-]+/[\w.-]+)/-/issues/(\d+)')
CNB_QUALIFIED_RE = re.compile(r'CNB\s*(?:的|侧|卡)?\s*#(\d+)')
# 裸 `#N`：前缀不是字母 / 数字 / `/`，避免命中 `abc#1`、`a/b#1` 与 URL 片段。
BARE_REF_RE = re.compile(r'(?<![\w/])#(\d+)')

# 一句话解释标签含义，挂在认领评论里，免得下一个人去猜 `CNB 处理中` 是谁挂的。
CLAIM_EXPLAIN = (
    f'`{CLAIM_LABEL}` = **CNB 侧已经有人在动手了**（有人在 CNB 上为这张卡开了 PR）。\n'
    '它不是「已完成」，也不是「不要动」——是**去重信号**：同一个问题两边同时改，'
    '最后要人工消解冲突（本仓实测过一次：CNB PR #180 与 PR #181 是同一张卡的两套并行解法）。\n'
    '要接手的话，先在 CNB 那张镜像卡的评论区说一声。'
)


# ---------------------------------------------------------------------------
# 纯函数（被 scripts/tests/test_claim_detect.py 覆盖）
# ---------------------------------------------------------------------------


def now_utc() -> str:
    return datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def extract_github_number(body: str | None) -> int | None:
    """从镜像卡正文里抠 GitHub 编号（幂等键行）。"""
    m = GITHUB_NUMBER_RE.search(body or '')
    return int(m.group(1)) if m else None


def extract_github_url_number(body: str | None) -> int | None:
    """从镜像卡正文的「来源」行抠 GitHub 编号。"""
    m = GITHUB_URL_RE.search(body or '')
    return int(m.group(1)) if m else None


def _labels_of(card: dict[str, Any]) -> list[str]:
    """取标签名列表（列表接口给 dict，有的地方给裸字符串）。"""
    return [((lbl or {}).get('name') if isinstance(lbl, dict) else str(lbl)) for lbl in card.get('labels') or []]


def is_local_card(card: dict[str, Any]) -> bool:
    """是不是 CNB 本地卡（D52）：本地卡不进 GitHub，也就没有可挂标签的对象。

    两种声明都认（与 `github_cnb_issues.local_card_kind` 同口径），
    **兜底猜测不在这里做**——这个脚本的写路径宁可少判不可错判。
    """
    if LOCAL_LABEL in _labels_of(card):
        return True
    return bool(LOCAL_MARKER_RE.search(card.get('body') or ''))


def is_mirror_card(card: dict[str, Any]) -> bool:
    """是不是镜像卡：有 `GitHub 同步` 标签，或正文里能抠到 GitHub 编号/链接。"""
    if MIRROR_LABEL in _labels_of(card):
        return True
    return (
        extract_github_number(card.get('body')) is not None or extract_github_url_number(card.get('body')) is not None
    )


def github_number_of(card: dict[str, Any]) -> int | None:
    """一张 CNB 镜像卡对应哪个 GitHub issue。两条路都认（编号行优先）。"""
    return extract_github_number(card.get('body')) or extract_github_url_number(card.get('body'))


def refs_in_title(title: str | None) -> set[int]:
    """从 **PR 标题**里抠卡号。标题就是「这件事是什么」，故裸号可以直接收。

    ⚠️ **裸号只在这里收。** 这是判据唯一可靠的地方，理由是实测出来的：

    初版让正文也收裸号，在 5 个真实 PR（#180 / #181 / #182 / #210 / #238）上
    逐行核对后，正文裸号的假阳性率极高——抽出的 7 个裸号里 4 个是**别的东西**：

      | 真实原文 | 抽出的 | 那其实是 |
      |---|---|---|
      | ``上一张 PR #210 已合入 dev`` | 210 | **CNB PR** 编号 |
      | ``（#1403 的形态）`` | 1403 | **GitHub** 侧卡号 |  <!-- cross-repo-ref-allow -->
      | ``撞 #1403 同族限流`` | 1403 | GitHub 侧卡号 |  <!-- cross-repo-ref-allow -->
      | ``#2034 口径 tooltip`` | 2034 | GitHub 侧卡号 |  <!-- cross-repo-ref-allow -->

    而 CNB 编号连续、镜像卡从 #5 起 ⇒ 这些号在 CNB 侧**确实存在同号卡**，
    于是标签会挂到一张完全不相干的卡上（本脚本最贵的一种错）。

    **试过的四条行级启发式（`PR #N` / GitHub 字样 / 行内代码 / 加粗）全部不够**：
    真实行文里 `**（#1403 的形态）`（加粗没闭合）、`撞 #1403 同族限流`（纯散文）
    这类形态都躲得过去；继续加启发式就是在拟合今天这 5 个样本——正是本仓
    「判据要能被证伪、不要拟合」所反对的。

    故改用**结构性**判据：**标题是「这件事是什么」，正文是「怎么做的」**。
    标题里的编号必然是本 PR 在做的卡（`feat(risk): …（#167）`）；
    正文里的编号多数是在引用别的东西。**只信标题。**
    """
    t = title or ''
    out = {int(m.group(2)) for m in CNB_URL_RE.finditer(t)}
    out |= {int(m.group(1)) for m in CNB_QUALIFIED_RE.finditer(t)}
    out |= {int(m.group(1)) for m in BARE_REF_RE.finditer(t)}
    return out


def refs_in_text(text: str | None) -> set[int]:
    """从 **PR 正文**里抠它引用的 CNB 卡号——**只认明确挂源的两种形态**。

    完整 URL 与 `CNB #N` 都是**人主动挂的源**，无歧义；裸号一律不收
    （理由见 `refs_in_title` 的 docstring）。

    **已知假阴性**：正文写裸 `#106`、而标题没写卡号的 PR 会被漏掉。
    那是「少挂一个标签」，下一个人仍能从 PR 里看到这件事；
    反过来（误挂到别人卡上）会让那张卡的下一位读者**不去动它**。**宁可漏。**
    """
    body = text or ''
    out: set[int] = set()
    for m in CNB_URL_RE.finditer(body):
        out.add(int(m.group(2)))
    for m in CNB_QUALIFIED_RE.finditer(body):
        out.add(int(m.group(1)))
    return out


def refs_of_pull(pull: dict[str, Any]) -> set[int]:
    """一个 PR 认领了哪些 CNB 卡：**标题（含裸号）∪ 正文（仅挂源形态）**。

    标题是权威来源（`（#167）` 就是本次在做的卡），正文是补充
    （`Closes CNB #179`、完整 URL）。两者取并集而不是只取标题：
    正文里的 `CNB #N` / 完整 URL 形态同样明确。
    """
    return refs_in_title(pull.get('title')) | refs_in_text(pull.get('body'))


@dataclass
class Claim:
    """一条认领事实：CNB 卡 → GitHub issue + 哪些 PR 在干它。"""

    cnb_number: int
    github_number: int
    prs: list[int] = field(default_factory=list)

    def marker(self) -> str:
        return f'{MARKER_PREFIX} github={self.github_number} prs={",".join(str(p) for p in sorted(self.prs))} -->'


def plan_claims(
    cnb_issues: list[dict[str, Any]],
    cnb_pulls: list[dict[str, Any]],
) -> tuple[list[Claim], list[int]]:
    """算出「哪些 GitHub 卡正在被 CNB 侧认领」。

    返回 `(claims, unknown_refs)`：

    - `claims`：只包含**能定位到 GitHub 卡**且**卡是镜像卡、当前 open** 的那些；
    - `unknown_refs`：PR 引用了、但 CNB 侧找不到对应卡的编号（引用写错 / 卡被删）。

    ⚠️ **`unknown_refs` 必须交给调用方报出来**，不得静默丢弃——那是「引用了不存在的卡」
    这个真实错误，而不是「没有认领」。本仓 #171 / #179 的教训：**拿不到输入不得退化成一个
    看起来正常的结论**。
    """
    by_number: dict[int, dict[str, Any]] = {}
    for issue in cnb_issues:
        num = issue.get('number')
        if num is not None:
            by_number[int(num)] = issue

    # PR → 它引用的 CNB 卡号（只在 CNB 侧 open 的 PR 算，关掉的不算「正在干」）
    refs_by_cnb: dict[int, list[int]] = {}
    unknown: set[int] = set()
    for pull in cnb_pulls:
        if (pull.get('state') or 'open') != 'open':
            continue
        num = pull.get('number')
        if num is None:
            continue
        refs = refs_of_pull(pull)
        if not refs:
            continue
        for r in refs:
            if r in by_number:
                refs_by_cnb.setdefault(r, []).append(int(num))
            else:
                unknown.add(r)

    claims: list[Claim] = []
    for cnb_number, prs in sorted(refs_by_cnb.items()):
        card = by_number[cnb_number]
        if (card.get('state') or 'open') != 'open':
            continue  # 卡已关，不叫「正在处理」
        if is_local_card(card):
            continue  # 本地卡没有 GitHub 侧可挂标签的对象（D52）
        if not is_mirror_card(card):
            continue  # 既非镜像也非本地 = 说不清，跳过（宁可漏）
        gh = github_number_of(card)
        if gh is None:
            continue
        claims.append(Claim(cnb_number=cnb_number, github_number=gh, prs=sorted(set(prs))))
    return claims, sorted(unknown)


def collect_markers(comments: list[dict[str, Any]]) -> set[int]:
    """收集已发过的认领评论标记（按 GitHub 编号）。"""
    out: set[int] = set()
    for c in comments:
        for m in MARKER_RE.finditer(c.get('body') or ''):
            out.add(int(m.group(1)))
    return out


def collect_marked_prs(comments: list[dict[str, Any]]) -> set[int]:
    """收集已认领评论里登记过的 CNB PR 编号（全体并集）。

    `collect_markers` 答的是「这张卡**有没有**被认领过」；本函数答的是
    「**哪些** PR 已经被登记过」——后者才能让「第 2 个 PR 加入」这件事被发现。
    """
    out: set[int] = set()
    for c in comments:
        for m in MARKER_RE.finditer(c.get('body') or ''):
            for piece in (m.group(2) or '').split(','):
                piece = piece.strip()
                if piece.isdigit():
                    out.add(int(piece))
    return out


def build_claim_comment(claim: Claim) -> str:
    """认领评论正文（幂等标记在末尾，渲染不可见）。"""
    prs = '、'.join(f'#{p}' for p in claim.prs) or '（未识别到 PR 编号）'
    return '\n'.join(
        [
            f'## CNB 侧已认领（{now_utc()[:10]}）',
            '',
            f'CNB 侧有人为这张卡开了 PR：{prs}（对应 CNB 镜像卡 #{claim.cnb_number}）。',
            '',
            CLAIM_EXPLAIN,
            '',
            '> 本评论由 `scripts/bridge/claim_detect.py` 自动发布，**只发一次、不改写**。',
            f'> 标签 `{CLAIM_LABEL}` 会在 CNB 侧没有在跑的 PR 时由 GitHub Action 自动摘除。',
            '',
            claim.marker(),
        ]
    )


# ---------------------------------------------------------------------------
# 网络
# ---------------------------------------------------------------------------


def _request(
    url: str,
    *,
    method: str = 'GET',
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> bytes:
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('User-Agent', 'fundmate-cnb-claim')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cnb_api(path: str) -> Any:
    """CNB 只读 OpenAPI（公开仓库匿名可读）。细节同 cnb_github_backfill.py。"""
    base = (os.environ.get('CNB_API_ENDPOINT') or 'https://api.cnb.cool').rstrip('/')
    headers = {'Accept': 'application/vnd.cnb.api+json'}
    token = os.environ.get('CNB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    raw = _request(f'{base}{path}', headers=headers)
    return json.loads(raw) if raw else None


def github_api(path: str, *, method: str = 'GET', payload: dict | None = None) -> Any:
    """GitHub REST API。**写必须带 token**（没 token 直接抛，不等到 401 才让人猜）。"""
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_PAT')
    if method != 'GET' and not token:
        raise RuntimeError('缺少 GITHUB_TOKEN（CNB 侧请用 Secret 仓库的 GITHUB_PAT；本地跑请 export）')
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    if data is not None:
        headers['Content-Type'] = 'application/json'
    raw = _request(f'https://api.github.com{path}', method=method, data=data, headers=headers)
    return json.loads(raw) if raw else None


def _cnb_repo() -> str:
    return os.environ.get('CNB_REPO') or os.environ.get('CNB_REPO_SLUG') or CNB_REPO_DEFAULT


def _github_repo() -> str:
    return os.environ.get('GITHUB_REPO') or GITHUB_REPO_DEFAULT


def list_cnb_issues() -> tuple[list[dict[str, Any]], bool]:
    """列 CNB 仓库全部 issue（open + closed）。

    返回 `(issues, complete)`：**`complete` 是这次拉取是否可信**。任何一页拉失败
    都不是「没有卡」，而是「拿不全」——调用方不得在 `complete=False` 时宣称
    「无认领，两侧已对齐」（本仓 #171 / #179 的假绿就是这么来的）。
    """
    repo = _cnb_repo()
    out: list[dict[str, Any]] = []
    complete = True
    for state in ('open', 'closed'):
        page = 1
        while True:
            qs = urllib.parse.urlencode({'page': page, 'page_size': 100, 'state': state})
            try:
                batch = cnb_api(f'/{repo}/-/issues?{qs}') or []
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                print(f'⚠️ CNB issue 列表拉取失败（state={state} page={page}）：{exc}')
                complete = False
                break
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return out, complete


def list_cnb_pulls() -> tuple[list[dict[str, Any]], bool]:
    """列 CNB 仓库的 PR（**只取 open**，因为「正在干」只由 open PR 定义）。

    ⚠️ 这里**有意不传 `state`**：CNB 的该接口 `state=open` 之外的行为未经实测，
    默认值即 open。改成 `all` 会让**已合并的 PR 也被算成「正在干」**——
    那就是「历史功劳被当成现状」的假认领。
    """
    repo = _cnb_repo()
    qs = urllib.parse.urlencode({'page_size': 100})
    try:
        data = cnb_api(f'/{repo}/-/pulls?{qs}')
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f'⚠️ CNB PR 列表拉取失败：{exc}')
        return [], False
    if isinstance(data, dict):
        # 有的接口把列表包在 items/data 里；两种都认，认不出就算不完整。
        for key in ('items', 'data'):
            if isinstance(data.get(key), list):
                return list(data[key]), True
        print('⚠️ CNB PR 列表返回了无法识别的结构，本轮结论不可信')
        return [], False
    return list(data or []), True


def get_cnb_issue(number: int) -> dict[str, Any]:
    """取单张 CNB 卡详情。

    ⚠️ **必须走这里才能拿到 `body`**——CNB 的 issue **列表**接口不返回正文
    （实测 2026-10-14：列表里没有 `body` 键，只有 `number` / `state` / `labels` …），
    而「这张卡对应哪个 GitHub issue」「是不是本地卡」两条判据都得读正文。
    该坑在 `github_cnb_issues.py` 与 `cnb_github_backfill.py` 里已各踩过一次，
    故此处**显式**把它写进 docstring，而不是靠下一个人重新发现。
    """
    repo = _cnb_repo()
    return cnb_api(f'/{repo}/-/issues/{number}') or {}


def list_github_issue_comments(number: int) -> list[dict[str, Any]]:
    """列 GitHub issue 的全部评论（用于收集认领标记）。"""
    repo = _github_repo()
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({'per_page': 100, 'page': page})
        batch = github_api(f'/repos/{repo}/issues/{number}/comments?{qs}')
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def github_issue_labels(number: int) -> set[str]:
    repo = _github_repo()
    issue = github_api(f'/repos/{repo}/issues/{number}')
    return {(lbl or {}).get('name') or '' for lbl in (issue or {}).get('labels') or []}


def add_github_label(number: int, label: str) -> None:
    """挂标签。GitHub 原生幂等：已存在时返回 200 且不重复。"""
    repo = _github_repo()
    github_api(f'/repos/{repo}/issues/{number}/labels', method='POST', payload={'labels': [label]})


def ensure_github_label_exists(label: str) -> None:
    """标签不存在时创建（颜色沿用本仓语义：橙色 = 进行中）。"""
    repo = _github_repo()
    try:
        github_api(f'/repos/{repo}/labels/{urllib.parse.quote(label)}')
        return
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    try:
        github_api(
            f'/repos/{repo}/labels',
            method='POST',
            payload={'name': label, 'color': 'fbca04', 'description': 'CNB 侧已有人为这张卡开了 PR'},
        )
    except urllib.error.HTTPError as exc:
        print(f'⚠️ 建标签 `{label}` 失败（不影响挂标签重试）：{exc}')


def remove_github_label(number: int, label: str) -> None:
    """摘标签。GitHub 原生幂等：标签本来就没有时返回 404，调用方按「已摘」处理。"""
    repo = _github_repo()
    github_api(f'/repos/{repo}/issues/{number}/labels/{urllib.parse.quote(label)}', method='DELETE')


def list_github_issues_with_label(label: str) -> tuple[list[int], bool]:
    """列出**带某个标签且仍 open** 的 issue 编号。

    这是「摘标签」那条路的输入：不拉全量 issue（会撞大结果集分页限制），
    只按标签查。

    返回 `(numbers, complete)`：**拉不全时不得宣称「没有过期标签」**——
    那正是本仓 #171 的假绿形态（拿不到 ⇒ 当成没有）。
    """
    repo = _github_repo()
    out: list[int] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({'labels': label, 'state': 'open', 'per_page': 100, 'page': page})
        try:
            batch = github_api(f'/repos/{repo}/issues?{qs}')
        except urllib.error.HTTPError as exc:
            print(f'⚠️ 按标签列 GitHub issue 失败（page={page}）：{exc}')
            return out, False
        if not batch:
            break
        out.extend(int(i['number']) for i in batch if 'pull_request' not in i)
        if len(batch) < 100:
            break
        page += 1
    return out, True


def post_github_comment(number: int, body: str) -> None:
    repo = _github_repo()
    github_api(f'/repos/{repo}/issues/{number}/comments', method='POST', payload={'body': body})


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def run(*, dry_run: bool, only_cnb: int | None) -> int:
    if not dry_run:
        token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_PAT')
        if not token:
            # 缺 token 直接失败：否则每条认领都只会在写的时候 401，
            # 而那会被 `|| true` 收尾吞掉 —— 又一次「一直绿、一直没干活」（本仓 #171）。
            print('❌ 缺少 GITHUB_TOKEN / GH_PAT，--apply 无凭据，提前失败')
            return 1

    issues, issues_ok = list_cnb_issues()
    pulls, pulls_ok = list_cnb_pulls()
    complete = issues_ok and pulls_ok

    if only_cnb is not None:
        issues = [i for i in issues if int(i.get('number') or -1) == only_cnb]

    # PR 引用了哪些卡 → 只对这些卡取详情（列表接口不返回 body，见 get_cnb_issue）。
    refs: set[int] = set()
    for pull in pulls:
        if (pull.get('state') or 'open') != 'open':
            continue
        refs |= refs_of_pull(pull)

    by_number: dict[int, dict[str, Any]] = {int(i['number']): i for i in issues if i.get('number') is not None}
    detailed: list[dict[str, Any]] = []
    for cnb_number in sorted(refs):
        card = by_number.get(cnb_number)
        if card is None:
            continue
        try:
            full = get_cnb_issue(cnb_number)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            print(f'⚠️ 取 CNB #{cnb_number} 详情失败：{exc} —— 该卡本轮不判（不猜）')
            complete = False
            continue
        # 详情可能不含 labels（接口差异），用列表里的那份兜底
        merged = {**card, **(full or {})}
        if not merged.get('labels'):
            merged['labels'] = card.get('labels') or []
        detailed.append(merged)

    claims, unknown = plan_claims(detailed, pulls)

    print(f'📥 CNB 卡 {len(issues)} 张；CNB open PR {len(pulls)} 个')
    if unknown:
        # 不是「没有认领」，是「引用了不存在的卡」——必须说出来。
        print(f'⚠️ PR 引用了 CNB 侧不存在的卡号（引用写错？）：{sorted(unknown)}')
    if not claims:
        # ⚠️ **不要在这里 return。** 「一条认领都没有」正是**最需要摘标签**的时刻——
        # 若提前返回，`CNB 处理中` 会永远挂在那张卡上，而它其实早已没人动。
        # （首版就是这么写的，被 `test_CNB侧没有PR时摘掉标签` 当场抓住。）
        if complete:
            print('✅ 无 CNB 侧认领（两侧已对齐）')
        else:
            print('⚠️ 数据不完整，本次结论不可信（上方有拉取失败记录）')

    print(f'🔎 判定 CNB 侧认领 {len(claims)} 条：')
    failed = False
    for claim in claims:
        prs = '、'.join(f'#{p}' for p in claim.prs)
        head = f'  CNB #{claim.cnb_number} → GitHub #{claim.github_number}（PR {prs}）'
        if dry_run:
            print(f'{head} [dry-run]')
            continue
        try:
            labels = github_issue_labels(claim.github_number)
        except urllib.error.HTTPError as exc:
            print(f'{head} ⚠️ 读 GitHub 卡失败：{exc}')
            failed = True
            continue
        if CLAIM_LABEL in labels:
            print(f'{head} 标签已存在，跳过')
            continue
        try:
            ensure_github_label_exists(CLAIM_LABEL)
            add_github_label(claim.github_number, CLAIM_LABEL)
        except urllib.error.HTTPError as exc:
            print(f'{head} ⚠️ 挂标签失败：{exc}')
            failed = True
            continue
        # 评论只发一次：先扫已有标记
        try:
            existing = collect_markers(list_github_issue_comments(claim.github_number))
            if claim.github_number not in existing:
                post_github_comment(claim.github_number, build_claim_comment(claim))
        except urllib.error.HTTPError as exc:
            print(f'{head} ⚠️ 发认领评论失败（标签已挂）：{exc}')
            failed = True
            continue
        print(f'{head} ✅ 已挂标签并留认领评论')

    # ---- 解除：CNB 侧已经没有在跑的 PR ⇒ 摘掉标签 ----
    # 「挂牌不摘」会让标签本身变成噪音（挂着的卡其实没人动），
    # 于是下一个人学到的教训是「别信那个标签」——那比不挂更坏。
    # 只在 `complete=True` 时摘：数据不全时**宁可多留**，也不误摘一张其实有人动的卡。
    if complete or dry_run:
        claimed_gh = {c.github_number for c in claims}
        if dry_run:
            print(f'🔓 解除检查 [dry-run]：CNB 侧认领 {len(claimed_gh)} 条，其余带标签的将被摘除')
        else:
            stale, ok = list_github_issues_with_label(CLAIM_LABEL)
            if not ok:
                print('⚠️ 无法列出带标签的卡，本轮不摘除任何标签（拿不到就不动手）')
                failed = True
            else:
                for gh_number in stale:
                    if gh_number in claimed_gh:
                        continue
                    try:
                        remove_github_label(gh_number, CLAIM_LABEL)
                    except urllib.error.HTTPError as exc:
                        print(f'  GitHub #{gh_number} ⚠️ 摘标签失败：{exc}')
                        failed = True
                        continue
                    print(f'  GitHub #{gh_number} 🔓 已摘除 `{CLAIM_LABEL}`（CNB 侧已无在跑的 PR）')
    else:
        print('⚠️ 数据不完整：本轮**不摘除**任何标签（宁可多留，也不误摘）')

    # 标签已挂、但本轮还额外识别到新的 PR → 补一条「新增 PR」评论（同样只发一次、按内容哈希）
    if not dry_run and complete:
        failed = _refresh_claim_comments(claims, dry_run=dry_run) or failed

    if not dry_run and not complete:
        print('⚠️ 数据不完整，本次结论不可信（可能漏判认领）')
    return 1 if (failed or not complete) else 0


def _refresh_claim_comments(claims: list[Claim], *, dry_run: bool) -> bool:
    """标签已存在、但认领的 PR 集合变了时，补一条说明（幂等键是**内容**，不是次数）。

    为什么需要：标签只能表达「有人在动」，表达不了「**哪些** PR 在动」。
    只挂标签的话，第 2、3 个 PR 加进来时 GitHub 侧毫无感知——
    而这恰恰是最需要被看见的时刻（同一件事已经有两条线在跑了）。
    """
    failed = False
    for claim in claims:
        try:
            comments = list_github_issue_comments(claim.github_number)
        except urllib.error.HTTPError as exc:
            print(f'  ⚠️ GitHub #{claim.github_number} 读评论失败：{exc}')
            failed = True
            continue
        seen_prs = collect_marked_prs(comments)
        if set(claim.prs) <= seen_prs:
            continue
        print(f'  GitHub #{claim.github_number} 📝 认领的 PR 集合有变化 → 补一条说明评论')
        if dry_run:
            continue
        try:
            post_github_comment(claim.github_number, build_claim_comment(claim))
        except urllib.error.HTTPError as exc:
            print(f'  ⚠️ GitHub #{claim.github_number} 补评论失败：{exc}')
            failed = True
    return failed


def main(argv: list[str] | None = None) -> int:
    # cross-repo-ref-allow：`#179` 是**本卡**（CNB 自己的编号）
    parser = argparse.ArgumentParser(description='CNB 侧认领 → GitHub 标签（源见文件头 docstring）')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--report', action='store_true', help='只报告（默认）')
    group.add_argument('--apply', action='store_true', help='真正挂标签 / 发评论')
    parser.add_argument('--cnb', type=int, default=None, help='只看这张 CNB 卡（调试用）')
    args = parser.parse_args(argv)
    return run(dry_run=not args.apply, only_cnb=args.cnb)


if __name__ == '__main__':
    sys.exit(main())
