#!/usr/bin/env python3
"""镜像卡「状态回流」：把 GitHub 侧的关闭事实带到 CNB 镜像卡上（CNB `#117` 硬要求 ②）。

为什么需要它
------------
`github_cnb_issues.py` 只做**建卡**，建完即止。于是镜像卡的溯源块里写着
「状态：`open`」——那是**建卡当时的快照**，之后 GitHub 把卡关了，CNB 侧一个字都不变。
读者在 CNB 看到一张「还活着」的卡，实际那件事早已结案。这正是 CNB #117 报的问题：
**只同步卡面、不同步状态，比两侧明显不一致更难察觉。**

本脚本把「GitHub 已关闭」这个事实**单向回流**到镜像卡上，形态是三件一起做：

1. 在该卡评论区追加一条结构化的「状态回流」评论（带隐藏幂等键，只发一次）；
2. 给该卡挂上 `CNB_STATUS_LABEL`（默认 `GitHub 已关闭`）标签，供看板一眼筛出；
3. **把 CNB 镜像卡关掉**（B 口径，2026-10-13 用户拍板）。

为什么从「标记不关」改成「真的关」（口径变更史）
------------------------------------------------
D48（CNB #117 硬要求 ②）原口径是**标记不关**：说清楚、但不替人关卡，
理由是「CNB 侧的追问常发生在 GitHub 关掉之后，关掉会把那些讨论一起埋掉」，
并保留人工回路（硬要求 ①）。

用户 2026-10-13 在 CNB `#171` 明确选了 **B：GitHub 关了，CNB 也自动关**——
理由是**两边长期不一致的代价更高**：镜像卡的读者在 CNB 看到的是一张「还活着」的卡，
而它在 GitHub 早已结案；「标记不关」把「卡片状态」和「事实状态」永久劈成两半，
看板越用越不可信。讨论被埋是可接受的代价（评论**不会被删**，只是卡变灰）。

**没有丢的是人工回路**：反向不回流（见下），以及 `--no-close` 逃生阀——
若某轮想只看不关，加这个开关即可。

边界（与既有两条管道一致）
--------------------------
- **单向**：只 GitHub → CNB，绝不回写 GitHub；
- **只增不覆盖**：不碰镜像卡正文，不改标题 / 优先级 / 里程碑（那是建卡时的口径）；
- **幂等**：同一条状态回流的键是 `状态键：<sha1 前 12 位>`，重复执行只发一次；
- **只认镜像卡**：拒绝往人工卡写（与 `mirror_correction.py` 同一条闸门）；
- **纯标准库**：复用 `github_cnb_issues.py` 的 `cnb_api`，无需 pip install。

**「评论已发过」不阻断「关卡」**：D48 时代已有 13 张卡发过回流评论却仍是 `open`，
本口径切换后它们**必须被补关**——否则口径改了、那些卡还漂着，等于换了个说法继续不一致。
故 `run()` 里评论走幂等键、关卡走 `cnb_state`，两条判据**分开**。

用法
----
    export CNB_TOKEN=<你的 token>

    # ① 只报告：两侧状态漂移有多少（不写任何东西）
    python scripts/bridge/mirror_state_sync.py --report

    # ② 真正回流（默认 dry-run，只打印将执行的动作）
    python scripts/bridge/mirror_state_sync.py --apply

    # ③ 只想标记、不想自动关（逃生阀，用于人工 triage）
    python scripts/bridge/mirror_state_sync.py --apply --no-close

    # 单张卡演练
    python scripts/bridge/mirror_state_sync.py --cnb 106 --apply
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_cnb_issues import (
    MIRROR_LABEL,
    cnb_api,
    extract_github_number,
    get_cnb_issue,
    list_cnb_issues,
    load_state,
)

# 状态回流的幂等键：写在评论正文末尾的 HTML 注释里（读者看不见，脚本看得见）。
STATE_KEY_RE = re.compile(r'状态键：([0-9a-f]{12})')
STATE_KEY_LINE = '<!-- 状态键：{} -->'

# 关闭事实的标签：看板可据此一眼筛出「GitHub 侧已结案」的镜像卡。
# CNB 标签名只允许中英文/数字/`._:-/\` 与内部空格，本名合法。
CNB_STATUS_LABEL = 'GitHub 已关闭'


def make_state_key(cnb_number: int, gh_number: int, gh_state: str, gh_updated: str) -> str:
    """幂等键 = sha1(CNB 编号 + GitHub 编号 + 状态 + GitHub 侧最后更新时刻)。

    带上 `gh_updated` 是刻意的：同一张卡「关闭 → 重开 → 再关闭」应当各发一条，
    否则第二次关闭会被当成重复而静默吞掉。
    """
    raw = f'{cnb_number}|{gh_number}|{gh_state}|{gh_updated}'
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def build_state_comment(
    gh_number: int,
    gh_state: str,
    gh_updated: str,
    key: str,
    *,
    repo: str,
    today: str | None = None,
    closed: bool = True,
) -> str:
    """拼状态回流评论：固定标题 + 事实 + 「本卡已随之关闭」的明示 + 隐藏幂等键。

    `closed=False`（`--no-close` 逃生阀）时正文改成「本卡仍开着、需人工确认」，
    **不能**在没关的卡上说「已自动关闭」——那是又一种说了等于没说的假绿。
    """
    date = today or datetime.now(UTC).strftime('%Y-%m-%d')
    verb = {'closed': '已关闭', 'open': '已重新打开'}.get(gh_state, f'状态为 `{gh_state}`')
    if closed:
        tail = [
            '> ✅ 本卡**已随 GitHub 同步关闭**（B 口径，CNB `#171` 用户拍板）。',
            '> 评论不会被删除，只是卡片转为已关闭；需要继续讨论时直接重新打开：',
            '> `cnb issues open --number <本卡编号>`。',
        ]
    else:
        tail = [
            '> ⚠️ 本轮**未自动关闭**本卡（`--no-close` 逃生阀）。GitHub 侧已结案，',
            '> 请人工确认此处是否还有讨论价值：`cnb issues close --number <本卡编号>`。',
        ]
    lines = [
        f'## 状态回流（{date}）',
        '',
        f'- GitHub 原卡 #{gh_number} **{verb}**（GitHub 侧最后更新：{_as_date(gh_updated)}）',
        f'- 依据：https://github.com/{repo}/issues/{gh_number}',
        '',
        *tail,
        '',
        STATE_KEY_LINE.format(key),
    ]
    return '\n'.join(lines)


def _as_date(value: str) -> str:
    """把 GitHub 的 ISO 时间截成日期；空值给「未知」，不要静默留空。"""
    return value[:10] if value else '未知'


def parse_comments(raw: Any) -> list[dict[str, str]]:
    """把 CNB 评论列表归一化成 [{body, id}]（与 mirror_correction.parse_comments 同形）。"""
    if isinstance(raw, dict):
        raw = raw.get('comments') or raw.get('items') or []
    out: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                'id': str(item.get('id') or item.get('note_id') or ''),
                'body': str(item.get('body') or item.get('note') or ''),
            }
        )
    return out


def list_issue_comments(cnb_number: int, *, repo: str | None = None) -> list[dict[str, str]]:
    from github_cnb_issues import _cnb_repo

    out: list[dict[str, str]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({'page': page, 'page_size': 100})
        batch = parse_comments(cnb_api(f'/{repo or _cnb_repo()}/-/issues/{cnb_number}/comments?{qs}'))
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def existing_state_keys(comments: list[dict[str, str]]) -> set[str]:
    return {m.group(1) for c in comments for m in STATE_KEY_RE.finditer(c['body'])}


def post_comment(cnb_number: int, body: str, *, repo: str | None = None) -> Any:
    from github_cnb_issues import _cnb_repo

    return cnb_api(
        f'/{repo or _cnb_repo()}/-/issues/{cnb_number}/comments',
        method='POST',
        payload={'body': body},
    )


def add_status_label(cnb_number: int, *, repo: str | None = None) -> None:
    """给镜像卡挂 `GitHub 已关闭` 标签（已挂则 CNB 幂等，不会重复）。"""
    from github_cnb_issues import _cnb_repo

    cnb_api(
        f'/{repo or _cnb_repo()}/-/issues/{cnb_number}/labels',
        method='POST',
        payload={'labels': [CNB_STATUS_LABEL]},
    )


def close_issue(cnb_number: int, *, repo: str | None = None) -> None:
    """关闭 CNB 镜像卡（B 口径）。

    端点形状经 `cnb-cli` 实现核实：`PATCH /{repo}/-/issues/{number}`，
    体为 `{"state": "closed", "state_reason": "completed"}`（与 `cnb issues close` 同路）。
    CNB 侧对「已关闭的卡再关一次」是幂等的，故不需要额外的「关没关过」判据——
    但调用方仍应先看 `cnb_state`，避免无谓请求与日志噪音。
    """
    from github_cnb_issues import _cnb_repo

    cnb_api(
        f'/{repo or _cnb_repo()}/-/issues/{cnb_number}',
        method='PATCH',
        payload={'state': 'closed', 'state_reason': 'completed'},
    )


def is_mirror_card(cnb_number: int, *, repo: str | None = None) -> bool:
    """确认是 GitHub 镜像卡（与 mirror_correction 同一条闸门，避免写到人工卡）。"""
    from github_cnb_issues import _cnb_repo, extract_github_number

    detail = cnb_api(f'/{repo or _cnb_repo()}/-/issues/{cnb_number}') or {}
    labels = [lb.get('name') if isinstance(lb, dict) else str(lb) for lb in (detail.get('labels') or [])]
    return MIRROR_LABEL in labels or extract_github_number(detail.get('body')) is not None


# ---------------------------------------------------------------------------
# 漂移判定（纯函数，回归网直接钉这里）
# ---------------------------------------------------------------------------


def state_drift(cnb_state: str, gh_state: str) -> bool:
    """两侧状态是否漂移。

    「漂移」只算一种：**GitHub 已关，CNB 还开着**。
    - CNB 关了、GitHub 还开着 ⇒ 是人主动关的（人工回路），不算漂移、不回退；
    - 两侧都关 ⇒ 已对齐。

    之所以只认这一个方向：反向「重新打开」不该由脚本替人决定——
    CNB 侧关掉一张卡往往是因为讨论已结束，GitHub 后来重开原卡不代表
    CNB 侧那些讨论又活了。
    """
    return gh_state == 'closed' and cnb_state != 'closed'


def plan(cards: list[dict[str, Any]], gh_by_number: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """算出「哪些镜像卡需要状态回流」。纯函数，不碰网络。

    `cards` = [{cnb, gh, cnb_state}]；`gh_by_number` = GitHub 编号 → issue 载荷。
    """
    out: list[dict[str, Any]] = []
    for card in cards:
        gh = gh_by_number.get(card['gh'])
        if gh is None:
            continue  # GitHub 侧拉不到（限额/删除），跳过而不是猜
        if state_drift(card['cnb_state'], gh.get('state', 'open')):
            out.append(
                {
                    **card,
                    'gh_state': gh['state'],
                    'gh_updated': gh.get('updated_at', ''),
                }
            )
    return out


def mirrored_cards(*, repo: str | None, state: dict[str, Any], resolve_body: bool = True) -> list[dict[str, Any]]:
    """从 CNB 列表 + 状态文件拼出所有镜像卡的 {cnb, gh, cnb_state}。

    **两条路都要认**（2026-10-18 补齐第二路，源 CNB `#564`）：

    1. **状态文件** `github_cnb_state.json`：`github_cnb_issues.py` 写它，是加速路径；
    2. **卡面正文**：`labels` 含 `GitHub 同步` 但**状态文件没记**的卡，直接抠正文里的
       `GitHub 编号：#N`。

    为什么必须加第二条：状态文件是**缓存**，只在建卡成功的路径写入。实测（2026-10-18）
    CNB 侧 **48 张** `GitHub 同步` 标签的 open 卡不在状态文件里 —— 它们**永远进不了
    `plan()`**，于是一条永远不会被执行的代码被当成了「已经对齐」。这正是本仓反复踩的
    「缓存当成全集」（CNB `#450` 的 224 张重复卡同因）。

    `resolve_body=False` 时**不**读正文（只走状态文件），供回归网钉住「只认标签不够」。

    两处防御，都被实测数据逼出来：

    - **优先按 `github.com/<repo>/issues/N` 的 URL 抠，抠不到再用 `GitHub 编号：#N`**：
      实测两种正文形态并存（见 CNB `#113` 与 `#187` 的卡面），只认一种会漏掉一半。
      但 URL 优先是有理由的：自检卡 `#113` 的编号行写的是 `#888888`（不存在的编号），
      按它抠会让脚本去追一张永远不存在的卡；按 URL 抠则落进「认不出」，可被报出来。
    - 认不出 GitHub 编号的镜像卡**不静默跳过**，计数后由 `run()` 报出来。
    """
    cards: list[dict[str, Any]] = []
    unresolved: list[int] = []
    open_numbers = {int(i['number']) for i in list_cnb_issues('open')}
    for cnb_state in ('open', 'closed'):
        for item in list_cnb_issues(cnb_state):
            labels = [lb.get('name') if isinstance(lb, dict) else str(lb) for lb in (item.get('labels') or [])]
            if MIRROR_LABEL not in labels:
                continue
            number = int(item['number'])
            gh_number = _gh_number_from_state(state, number)
            if gh_number is None and resolve_body:
                try:
                    detail = get_cnb_issue(number)
                except Exception as exc:  # noqa: BLE001  # 单张读不到不该丢整轮
                    print(f'  ⚠️ CNB #{number} 正文读取失败，本轮跳过：{exc}')
                    continue
                body = detail.get('body')
                gh_number = _github_url_number_of(body) or extract_github_number(body)
                if gh_number is not None:
                    print(f'  ℹ️  CNB #{number} 不在状态文件里，按卡面正文认出 GitHub #{gh_number}')
            if gh_number is None:
                unresolved.append(number)
                continue
            cards.append(
                {
                    'cnb': number,
                    'gh': gh_number,
                    'cnb_state': item.get('state', cnb_state),
                }
            )
    if unresolved:
        # 只报**还开着**的那些：已关的卡不需要任何动作，把它们列出来只会淹没真问题
        # （实测 198 张 open + 283 张 closed 里，真正「认不出且还开着」的只有 1 张）。
        still_open = sorted(n for n in unresolved if n in open_numbers)
        if still_open:
            print(f'⚠️ {len(still_open)} 张 open 的 `{MIRROR_LABEL}` 卡认不出 GitHub 编号：{still_open}')
        closed_unknown = len(unresolved) - len(still_open)
        if closed_unknown:
            print(f'   （另有 {closed_unknown} 张**已关闭**的卡认不出编号，无需动作）')
    return cards


def _github_url_number_of(body: str | None) -> int | None:
    """从镜像卡正文的**来源 URL** 抠 GitHub 编号（`.../issues/N`）。

    刻意不走「`GitHub 编号：#N`」那一行：自检卡（CNB `#113`）那行里是 `#888888`，
    按它抠会让脚本去追一张不存在的卡。URL 是建卡脚本按真实编号写的，更可信。
    """
    import re as _re

    m = _re.search(r'https://github\.com/[\w.-]+/[\w.-]+/issues/(\d+)', body or '')
    return int(m.group(1)) if m else None


def _gh_repo_name() -> str:
    from github_cnb_issues import _github_repo

    return _github_repo()


def _gh_number_from_state(state: dict[str, Any], cnb_number: int) -> int | None:
    for gh, meta in (state.get('mirrored') or {}).items():
        if str(meta.get('cnb')) == str(cnb_number):
            return int(gh)
    return None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def fetch_github_issues_by_number() -> dict[int, dict[str, Any]]:
    """GitHub 编号 → (issue 映射, 是否拉全)。

    `fetch_github_open_issues` 只拉 open，故这里另走一遍带 `state=all` 的查询。

    **为什么要返回「是否拉全」这个布尔（issue #171）**：本函数以前只返回映射，
    拿不到就 `break`，而调用方 `run()` 把「空映射」等同成「没有漂移」，于是打印
    `✅ 无状态漂移，两侧已对齐`——**一张卡都没拉到，却给出一个完全错误的结论**。
    这不是假阴性，是假阳性里最坏的一种：机制从此隐身，红也看不见（整段还带 `|| true`）。

    实测（2026-10-13，本仓 CNB cron 环境）：`state=all` 要连拉 3 页，而匿名限额
    60 次/时/IP 被建卡 job 先耗掉，第 3 页 403 ⇒ 本函数返回 0 张 ⇒ 报告说「已对齐」。

    故现在**把「完整性」作为一等返回值交出去**：调用方在拿不全时不得宣称对齐。
    之所以仍然不抛异常（而是返回部分结果），是为了让「能做的回流照做」——
    `plan()` 对拿不到的卡是**跳过而不是猜**，故部分结果只会少标记、不会误标。

    ⚠️ 翻页**跟 `Link` 头走**（源 CNB #586，2026-10-19 实测）：本函数原先自己拼 `page=`，
    而 GitHub 对**大结果集**（本仓已超 1000 张卡）已关闭 `page` 分页，第 11 页直接 422：

        Pagination with the page parameter is not supported for large datasets,
        please use cursor based pagination (after/before)

    后果不是「少几张」，而是**只剩前 1000 张**：实测那一轮判定出 1 张漂移，
    而本地 `--report` 是 **42 张** —— 422 把结论砍成了 1/42。现在统一走
    `github_cnb_issues.fetch_github_issues()`，那条路径读 `Link` 头、跟着游标翻。
    """
    from github_cnb_issues import fetch_github_issues

    items, complete, note = fetch_github_issues('all', sort='updated', direction=None)
    if not complete:
        print(f'❌ {note}；本轮已拿 {len(items)} 张 —— 数据不完整。')
        print('   根因多为未注入 GITHUB_TOKEN（匿名 60 次/时/IP）；本轮结论不可信。')
    out: dict[int, dict[str, Any]] = {}
    for item in items:
        if 'pull_request' not in item:
            out[int(item['number'])] = item
    return out, complete


def _github_headers() -> dict[str, str]:
    """GitHub API 请求头；`GITHUB_TOKEN` 有则带上（匿名只有 60 次/时/IP）。"""
    import os

    headers: dict[str, str] = {'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def run(*, apply: bool, only_cnb: int | None, repo: str | None, auto_close: bool = True) -> int:
    state = load_state()
    cards = mirrored_cards(repo=repo, state=state)
    if only_cnb is not None:
        cards = [c for c in cards if c['cnb'] == only_cnb]
        if not cards:
            print(f'❌ CNB #{only_cnb} 不在镜像卡映射里（状态文件无记录，或它不是镜像卡）')
            return 1

    gh_by_number, complete = fetch_github_issues_by_number()
    print(f'📥 GitHub issue {len(gh_by_number)} 张；CNB 镜像卡 {len(cards)} 张')

    todo = plan(cards, gh_by_number)

    # 「拉不到」不等于「没漂移」（issue #171）。
    # 只要数据不完整（限额 / 网络错 / 分页天花板），**一律不得宣称对齐**——
    # 拿到 0 张却报「✅ 两侧已对齐」是本机制最坏的失败形态：错误结论 + 红灯不可见。
    # 有漂移时部分数据仍能安全回流（plan 对拿不到的卡是跳过），故「照做但不背书」。
    if not complete:
        print(f'❌ 数据不完整，本次结论不可信（已判定漂移 {len(todo)} 张，但这既不能证明有、也不能证明没有）。')
        if not todo:
            print('   注意：这里本该打印「无漂移」——但因数据不完整，该结论不成立。')
    elif not todo:
        print('✅ 无状态漂移，两侧已对齐')
        return 0

    print(f'🆕 待回流 {len(todo)} 张（自动关闭：{"开" if auto_close else "关（--no-close）"}）')
    commented = 0
    closed = 0
    for card in todo:
        key = make_state_key(card['cnb'], card['gh'], card['gh_state'], card['gh_updated'])
        published = existing_state_keys(list_issue_comments(card['cnb'], repo=repo))
        need_comment = key not in published
        # 关卡与评论**分开判**：D48 时代发过评论却没关的卡（13 张），口径切到 B 后必须补关，
        # 否则「口径改了、那些卡还漂着」。
        #
        # 这里不再重复判 `card['cnb_state'] != 'closed'`——`plan()` 只交出漂移卡，
        # 而 `state_drift()` 的定义已经排除「两侧都关」。加一道等价判断是**死代码**：
        # 它永远不会为假，守门也咬不住它（实测 S5 探针 MISSED），留着只会让人以为
        # 它承担了「不重复关」的职责。真正保证幂等的地方在 `plan()`，回归网钉在那边。
        need_close = auto_close
        body = build_state_comment(
            card['gh'], card['gh_state'], card['gh_updated'], key, repo=_gh_repo_name(), closed=need_close
        )

        if not need_comment and not need_close:
            print(f'  ⏭️  CNB #{card["cnb"]}（GitHub #{card["gh"]}）已回流且已关闭，跳过')
            continue
        if not apply:
            acts = []
            if need_comment:
                acts.append('发回流评论')
            if need_close:
                acts.append('关闭卡片')
            print(f'  [DRY-RUN] CNB #{card["cnb"]} ← GitHub #{card["gh"]} {card["gh_state"]}：{"、".join(acts)}')
            continue
        if not is_mirror_card(card['cnb'], repo=repo):
            print(f'  ❌ CNB #{card["cnb"]} 不是镜像卡，拒绝写入')
            continue
        if need_comment:
            post_comment(card['cnb'], body, repo=repo)
            commented += 1
        else:
            print(f'  ⏭️  CNB #{card["cnb"]} 回流评论已存在（幂等键命中），跳过评论')
        try:
            add_status_label(card['cnb'], repo=repo)
        except Exception as exc:  # noqa: BLE001  # 挂标签失败不该丢评论
            print(f'  ⚠️ CNB #{card["cnb"]} 挂标签失败：{exc}')
        if need_close:
            try:
                close_issue(card['cnb'], repo=repo)
                closed += 1
            except Exception as exc:  # noqa: BLE001  # 关卡失败要显式报，不能静默
                print(f'  ❌ CNB #{card["cnb"]} 关闭失败：{exc}')
                continue
        marks = []
        if need_comment:
            marks.append('已回流')
        if need_close:
            marks.append('已关闭')
        print(f'  ✅ CNB #{card["cnb"]} ← GitHub #{card["gh"]}：{"、".join(marks)}（标签「{CNB_STATUS_LABEL}」）')

    if apply:
        print(f'🎉 完成：评论 {commented} 张、关闭 {closed} 张（共待处理 {len(todo)} 张）')
    else:
        print(f'[DRY-RUN] 将处理 {len(todo)} 张（加 --apply 真正执行）')
    # 退出码即信号：数据不完整 ⇒ 非 0，让 cron 侧能看出「这次没真的跑成」。
    return 1 if not complete else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='镜像卡状态回流：GitHub 已关闭 → CNB 标记并自动关闭（B 口径，CNB `#171`）'
    )
    parser.add_argument('--repo', default=None, help='CNB 仓库，默认从 CNB_REPO_SLUG 环境变量识别')
    parser.add_argument('--cnb', type=int, default=None, help='只处理某张 CNB 镜像卡（演练用）')
    parser.add_argument('--report', action='store_true', help='只报告不写（等同默认的 dry-run）')
    parser.add_argument('--apply', action='store_true', help='真正写入（默认 dry-run）')
    parser.add_argument(
        '--no-close',
        dest='no_close',
        action='store_true',
        help='逃生阀：只发回流评论 + 挂标签，不自动关闭卡片（默认自动关）',
    )
    args = parser.parse_args(argv)
    return run(
        apply=args.apply and not args.report,
        only_cnb=args.cnb,
        repo=args.repo,
        auto_close=not args.no_close,
    )


if __name__ == '__main__':
    sys.exit(main())
