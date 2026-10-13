#!/usr/bin/env python3
"""镜像卡「状态回流」：把 GitHub 侧的关闭事实带到 CNB 镜像卡上（CNB #117 硬要求 ②）。

为什么需要它
------------
`github_cnb_issues.py` 只做**建卡**，建完即止。于是镜像卡的溯源块里写着
「状态：`open`」——那是**建卡当时的快照**，之后 GitHub 把卡关了，CNB 侧一个字都不变。
读者在 CNB 看到一张「还活着」的卡，实际那件事早已结案。这正是 CNB #117 报的问题：
**只同步卡面、不同步状态，比两侧明显不一致更难察觉。**

本脚本把「GitHub 已关闭」这个事实**单向回流**到镜像卡上，形态是：

1. 在该卡评论区追加一条结构化的「状态回流」评论（带隐藏幂等键，只发一次）；
2. 给该卡挂上 `CNB_STATUS_LABEL`（默认 `GitHub 已关闭`）标签，供看板一眼筛出。

为什么是「标记」而不是「自动关卡」
----------------------------------
原取舍（`github_cnb_issues.py` 文件头）写的是「不同步关闭态」，理由是
「CNB 关了会被误读成『这事不做了』，而关闭与否该由人拍板」（CNB #117 硬要求 ①：
人工回路必须保留）。这条理由现在仍然成立——**CNB 侧的追问往往发生在 GitHub 关掉之后**，
直接把卡关掉会把那些讨论一起埋掉。

所以本脚本采取**标记法**：把关闭事实**说清楚**（评论 + 标签），但**不替人做关闭这个决定**。
要把卡真正关掉，请人工执行 `cnb issues close --number <n>`。

边界（与既有两条管道一致）
--------------------------
- **单向**：只 GitHub → CNB，绝不回写 GitHub；
- **只增不覆盖**：不碰镜像卡正文，不改标题 / 优先级 / 里程碑（那是建卡时的口径）；
- **幂等**：同一条状态回流的键是 `状态键：<sha1 前 12 位>`，重复执行只发一次；
- **只认镜像卡**：拒绝往人工卡写（与 `mirror_correction.py` 同一条闸门）；
- **纯标准库**：复用 `github_cnb_issues.py` 的 `cnb_api`，无需 pip install。

用法
----
    export CNB_TOKEN=<你的 token>

    # ① 只报告：两侧状态漂移有多少（不写任何东西）
    python scripts/bridge/mirror_state_sync.py --report

    # ② 真正回流（默认 dry-run，只打印将发布的评论）
    python scripts/bridge/mirror_state_sync.py --apply

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
) -> str:
    """拼状态回流评论：固定标题 + 事实 + 「不自动关」的明示 + 隐藏幂等键。"""
    date = today or datetime.now(UTC).strftime('%Y-%m-%d')
    verb = {'closed': '已关闭', 'open': '已重新打开'}.get(gh_state, f'状态为 `{gh_state}`')
    lines = [
        f'## 状态回流（{date}）',
        '',
        f'- GitHub 原卡 #{gh_number} **{verb}**（GitHub 侧最后更新：{_as_date(gh_updated)}）',
        f'- 依据：https://github.com/{repo}/issues/{gh_number}',
        '',
        '> ⚠️ 本卡**不会被自动关闭**——CNB 侧的追问常发生在 GitHub 结案之后，',
        '> 关掉会把那些讨论一起埋掉（CNB #117 硬要求 ①）。',
        '> 若确认此处已无讨论价值，请人工执行 `cnb issues close --number <本卡编号>`。',
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


def mirrored_cards(*, repo: str | None, state: dict[str, Any]) -> list[dict[str, Any]]:
    """从状态文件 + CNB 列表拼出所有镜像卡的 {cnb, gh, cnb_state}。

    状态文件的真权威仍是镜像卡正文里的 `GitHub 编号：#N`，这里用状态文件只是**加速**
    （它是缓存，删掉可自愈——与 `github_cnb_issues.py` 的口径一致）。
    """
    cards: list[dict[str, Any]] = []
    for cnb_state in ('open', 'closed'):
        for item in list_cnb_issues(cnb_state):
            labels = [lb.get('name') if isinstance(lb, dict) else str(lb) for lb in (item.get('labels') or [])]
            if MIRROR_LABEL not in labels:
                continue
            number = int(item['number'])
            gh_number = _gh_number_from_state(state, number)
            if gh_number is None:
                continue
            cards.append(
                {
                    'cnb': number,
                    'gh': gh_number,
                    'cnb_state': item.get('state', cnb_state),
                }
            )
    return cards


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
    """
    import json
    import urllib.error

    from github_cnb_issues import _github_repo, _request

    out: dict[int, dict[str, Any]] = {}
    complete = True
    page = 1
    while True:
        qs = urllib.parse.urlencode({'state': 'all', 'per_page': 100, 'page': page, 'sort': 'updated'})
        url = f'https://api.github.com/repos/{_github_repo()}/issues?{qs}'
        try:
            batch = json.loads(_request(url, headers=_github_headers()))
        except urllib.error.HTTPError as exc:
            complete = False
            if exc.code == 403:
                print(f'❌ GitHub 限额用尽（403），只拿到前 {page - 1} 页共 {len(out)} 张 —— 数据不完整。')
                print('   根因多为未注入 GITHUB_TOKEN（匿名 60 次/时/IP）；本轮结论不可信。')
            else:
                print(f'❌ GitHub 返回 {exc.code}，中断在 page {page}；本轮已拿 {len(out)} 张 —— 数据不完整。')
            break
        if not batch:
            break
        for item in batch:
            if 'pull_request' not in item:
                out[int(item['number'])] = item
        if len(batch) < 100:
            break
        page += 1
        if page > 20:  # 2000 张卡的天花板，防呆
            complete = False
            print(f'❌ 分页超过 {page - 1} 页天花板 —— 数据可能不完整。')
            break
    return out, complete


def _github_headers() -> dict[str, str]:
    """GitHub API 请求头；`GITHUB_TOKEN` 有则带上（匿名只有 60 次/时/IP）。"""
    import os

    headers: dict[str, str] = {'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def run(*, apply: bool, only_cnb: int | None, repo: str | None) -> int:
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
        print(
            f'❌ 数据不完整，本次结论不可信'
            f'（已判定漂移 {len(todo)} 张，但这既不能证明有、也不能证明没有）。'
        )
        if not todo:
            print('   注意：这里本该打印「无漂移」——但因数据不完整，该结论不成立。')
    elif not todo:
        print('✅ 无状态漂移，两侧已对齐')
        return 0

    print(f'🆕 待回流 {len(todo)} 张')
    done = 0
    for card in todo:
        key = make_state_key(card['cnb'], card['gh'], card['gh_state'], card['gh_updated'])
        published = existing_state_keys(list_issue_comments(card['cnb'], repo=repo))
        body = build_state_comment(card['gh'], card['gh_state'], card['gh_updated'], key, repo=_gh_repo_name())
        if key in published:
            print(f'  ⏭️  CNB #{card["cnb"]}（GitHub #{card["gh"]}）状态已回流过，跳过')
            continue
        if not apply:
            print(f'  [DRY-RUN] CNB #{card["cnb"]} ← GitHub #{card["gh"]} {card["gh_state"]}')
            continue
        if not is_mirror_card(card['cnb'], repo=repo):
            print(f'  ❌ CNB #{card["cnb"]} 不是镜像卡，拒绝写入')
            continue
        post_comment(card['cnb'], body, repo=repo)
        try:
            add_status_label(card['cnb'], repo=repo)
        except Exception as exc:  # noqa: BLE001  # 挂标签失败不该丢评论
            print(f'  ⚠️ CNB #{card["cnb"]} 挂标签失败（评论已发）：{exc}')
        done += 1
        print(f'  ✅ CNB #{card["cnb"]} ← GitHub #{card["gh"]} 已标记「{CNB_STATUS_LABEL}」')

    if apply:
        print(f'🎉 完成：回流 {done} 张，跳过 {len(todo) - done} 张')
    else:
        print(f'[DRY-RUN] 将回流 {len(todo)} 张（加 --apply 真正执行）')
    # 退出码即信号：数据不完整 ⇒ 非 0，让 cron 侧能看出「这次没真的跑成」。
    return 1 if not complete else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='镜像卡状态回流：GitHub 已关闭 → 在 CNB 标记（CNB #117 硬要求 ②）')
    parser.add_argument('--repo', default=None, help='CNB 仓库，默认从 CNB_REPO_SLUG 环境变量识别')
    parser.add_argument('--cnb', type=int, default=None, help='只处理某张 CNB 镜像卡（演练用）')
    parser.add_argument('--report', action='store_true', help='只报告不写（等同默认的 dry-run）')
    parser.add_argument('--apply', action='store_true', help='真正写入（默认 dry-run）')
    args = parser.parse_args(argv)
    return run(apply=args.apply and not args.report, only_cnb=args.cnb, repo=args.repo)


if __name__ == '__main__':
    sys.exit(main())
