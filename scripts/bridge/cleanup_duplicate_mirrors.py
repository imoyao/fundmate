#!/usr/bin/env python3
"""重复镜像卡清理：同一 GitHub 卡在 CNB 侧建了多张时，留一张、关其余（源 CNB #450）。  <!-- cross-repo-ref-allow -->

## 为什么是「关」而不是「删」

`check_duplicate_mirrors.py` 只负责**发现**（只读）。清理是人的决定，故本脚本
**默认 dry-run**，`--apply` 才动手。

**动作只有「关闭」一种**（`PATCH state=closed`）——实测 CNB OpenAPI **不支持删除 issue**：
`DELETE /{repo}/-/issues/{n}` 对真实存在的卡一律返 **404 Resource not found**
（2026-10-14 实测，拿真实卡试的），而 `PATCH state=closed` 返 200 生效。
所以「清除重复的 issues」在 CNB 侧的等价动作是**关闭**，不是删除。

关闭是**可逆**的（卡与正文都留着、随时可重开），这也是它的好处：
判错一张的代价只是「重开一下」，而不是「永久丢一张卡」。

> ⚠️ 但「零评论」是**当前实测**，不是**结构性保证**。若某张重复卡日后被人工评论过，
> 本脚本的判据（见下）会**优先保留有评论的那张**——所以判据是可重放的，不是一次性特例。

## 保留判据（可重放，逐条带依据）

1. **有评论的卡优先**——评论是重复卡里唯一「关了也难看全」的东西（虽然关闭不删评论，
   但留在正本上才有人读得到）；
2. 同为有/无评论 ⇒ **留 CNB 编号最小**的那张（最早创建，一般是原卡）；
3. 留的那张**状态不被本脚本改动**。

⚠️ 特别注意本仓（CNB）**#167** 那张卡：它对应 GitHub 编号 `2118`，带 38 条评论、
且被人工关过（拆卡转移），而 9 张重复卡全是空的 `open`。按判据 1 保留 CNB #167 ——
它才是唯一的正本。**不要**因为「#167 是 closed、重复卡是 open」就去保留重复卡。

## ⚠️ 保留卡的状态必须跟 GitHub 对齐（2026-10-14 实测踩到）

判据 1（有评论优先）会在一个场景下**选出一张 `closed` 的保留卡**：
正本带讨论、但被人工关过（#167 正是如此），而重复卡全是空的 `open`。
若只按判据 1 选它、再把 9 张 open 的关掉，这组就**一张 open 都不剩**，
而 GitHub 侧那张卡**还开着** —— 镜像失去了「活的卡」，看板上再也找不到它。

所以判据 1 之后还要补一条**状态检查**：**GitHub 侧仍 open ⇒ 保留卡也必须是 open**，
不是就**重开它**（`PATCH state=open`）。判据是「GitHub 的 state」，不是卡自己的 history。

> 实测：本仓（CNB）编号 `167` 那张卡是 `closed`（人工拆卡转移），而 GitHub 侧对应编号 `2118`
> 仍 `open`。清理后我手工重开了它，本脚本补上这条之后就不再依赖人工发现。

## 失败态（#171 的纪律）

拿不到输入（CNB 列表 / 详情读取失败）⇒ **退出码 2 并声明结论不可信**，
**不得**因为「读不到」就退化成一个看起来正常的结论。
**`--apply` 在有卡读不到时直接拒绝动手**，调用方无须自己判 `read_failed`。

## 用法

    python scripts/bridge/cleanup_duplicate_mirrors.py           # dry-run，列出将关闭的卡
    python scripts/bridge/cleanup_duplicate_mirrors.py --apply   # 真正关闭
    python scripts/bridge/cleanup_duplicate_mirrors.py --apply --reopen-keeper  # 并修好保留卡状态
    python scripts/bridge/cleanup_duplicate_mirrors.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from check_duplicate_mirrors import collect, group_by_github_number  # noqa: E402
from github_cnb_issues import cnb_api, fetch_github_open_issues, get_cnb_issue  # noqa: E402

EXIT_OK = 0
EXIT_ACTIONED = 1  # dry-run 下有可清理项（便于 CI 判红），或 apply 后有失败
EXIT_UNKNOWN = 2


def _comment_count(detail: dict[str, Any]) -> int:
    return int(detail.get('comment_count') or 0)


def pick_keeper(details: list[dict[str, Any]]) -> tuple[int, list[int]]:
    """给定同一 GitHub 编号下的多张卡详情，返回 `(保留卡号, 其余卡号)`。

    判据（见文件头）：**有评论的优先，其余按编号升序取最小**。
    纯函数，供单测直接用。
    """

    def sort_key(d: dict[str, Any]) -> tuple[int, int]:
        # 第一维降序（有评论优先）用 -count；第二维升序用 number
        return (-_comment_count(d), int(d['number']))

    ordered = sorted(details, key=sort_key)
    keeper = int(ordered[0]['number'])
    return keeper, [int(d['number']) for d in ordered[1:]]


def plan(grouped: dict[int, list[int]], details: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """对每个重复的 GitHub 编号给出 `{保留: n, 关闭: [...]}`。纯函数。"""
    out: dict[int, dict[str, Any]] = {}
    for gh, numbers in sorted(grouped.items()):
        if len(numbers) < 2:
            continue
        cards = [details[n] for n in numbers]
        keeper, extras = pick_keeper(cards)
        out[gh] = {
            'keep': keeper,
            'remove': extras,
            'keep_comments': _comment_count(details[keeper]),
            'removed_comments': sum(_comment_count(details[n]) for n in extras),
        }
    return out


def close_issue(number: int) -> None:
    """关闭一张重复卡。

    ⚠️ 只能用 PATCH 关闭，**不能删除**：CNB OpenAPI 的
    `DELETE /{repo}/-/issues/{n}` 对真实存在的卡一律返 404（2026-10-14 实测），
    而 `PATCH state=closed` 返 200 生效。见文件头「为什么是关而不是删」。
    """
    repo = 'duoduobei/fundmate'
    cnb_api(
        f'/{repo}/-/issues/{number}',
        method='PATCH',
        payload={'state': 'closed', 'state_reason': 'not_planned'},
    )


def keeper_state_fixes(
    plans: dict[int, dict[str, Any]],
    details: dict[int, dict[str, Any]],
    github_open: set[int],
) -> dict[int, int]:
    """算出「保留卡应当被重开」的 `{GitHub 编号: CNB 卡号}`。

    判据：**GitHub 侧仍 open，而保留卡是 `closed`** ⇒ 这组会一张 open 都不剩，
    镜像就此从看板上消失。此时必须重开保留卡（它是带讨论的正本）。

    只输出**需要动**的，已经是 open 的不管。纯函数，供单测直接用。
    """
    fixes: dict[int, int] = {}
    for gh, p in plans.items():
        keeper = p['keep']
        if gh not in github_open:
            continue
        if (details.get(keeper) or {}).get('state') == 'closed':
            fixes[gh] = keeper
    return fixes


def reopen_issue(number: int) -> None:
    """重开一张被误关的保留卡（GitHub 侧仍 open 时用）。"""
    repo = 'duoduobei/fundmate'
    cnb_api(
        f'/{repo}/-/issues/{number}',
        method='PATCH',
        payload={'state': 'open', 'state_reason': 'reopened'},
    )


def render(
    plans: dict[int, dict[str, Any]],
    failed: list[int],
    *,
    applied: bool,
    keeper_fixes: dict[int, int] | None = None,
) -> tuple[str, int]:
    keeper_fixes = keeper_fixes or {}
    total = sum(len(p['remove']) for p in plans.values())
    lost_comments = sum(p['removed_comments'] for p in plans.values())

    lines: list[str] = ['# 重复镜像卡清理（CNB #450）', '']
    lines.append(
        '- 动作：关闭（`PATCH state=closed`；CNB 不支持删除 issue，见脚本 docstring）'
        + ('　**已执行**' if applied else '　dry-run（未动手）')
    )
    lines.append(f'- 重复的 GitHub 编号：{len(plans)} 个')
    lines.append(f'- 将关闭的卡：{total} 张')
    lines.append(
        f'- 被关闭卡上的评论总数：{lost_comments} 张'
        + ('' if lost_comments == 0 else '　⚠️ 非零即违反保留判据，应停下核实')
    )
    lines.append(f'- 读取失败的卡：{len(failed)} 张' + (f'（{failed[:20]}）' if failed else ''))
    if keeper_fixes:
        lines.append(
            f'- ⚠️ **保留卡需重开**：{len(keeper_fixes)} 张（GitHub 侧仍 open，但保留卡是 closed）：{keeper_fixes}'
        )
    lines.append('')

    if plans:
        lines.append('## 清单（GitHub 编号 → 保留 / 关闭，附保留依据）')
        lines.append('')
        for gh, p in plans.items():
            why = '有评论' if p['keep_comments'] else '编号最小'
            lines.append(
                f'- GitHub #{gh}：保留 CNB #{p["keep"]}（{why}，{p["keep_comments"]} 条评论）；关闭 {p["remove"]}'
            )
        lines.append('')

    if failed:
        lines.append('## ⚠️ 结论不可信')
        lines.append('')
        lines.append(
            f'有 {len(failed)} 张镜像卡读取失败，它们**未被纳入任何判定**。上面的清单是**下限**，**不得**据此执行清理。'
        )
        lines.append('')

    if total == 0 and not failed:
        lines.append('## 无重复卡')
        lines.append('')

    exit_code = EXIT_UNKNOWN if failed else (EXIT_ACTIONED if total else EXIT_OK)
    return '\n'.join(lines), exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='重复镜像卡清理（CNB #450）')
    parser.add_argument('--apply', action='store_true', help='真正执行清理（默认 dry-run）')
    parser.add_argument(
        '--reopen-keeper',
        action='store_true',
        help='若保留卡是 closed 而 GitHub 侧仍 open，重开它（否则这组会一张 open 都不剩）',
    )
    parser.add_argument('--limit', type=int, default=None, help='只读前 N 张镜像卡（调试用）')
    parser.add_argument('--json', dest='json_out', default=None, help='把结构化清单写到该文件')
    args = parser.parse_args(argv)

    details_list, failed = collect(limit=args.limit)
    grouped, unkeyed = group_by_github_number(details_list)

    # 详情按编号索引，便于 pick_keeper 取评论数
    details: dict[int, dict[str, Any]] = {}
    for card in details_list:
        n = int(card['number'])
        try:
            details[n] = get_cnb_issue(n)
        except Exception as exc:  # noqa: BLE001  读不到 ⇒ 记失败，不猜
            failed.append(n)
            print(f'  ⚠️ 读取 CNB #{n} 详情失败：{exc}', file=sys.stderr)

    plans = plan(grouped, details)

    # GitHub 侧仍 open 的编号：用于判断保留卡是否该重开（见文件头「状态必须跟 GitHub 对齐」）
    keeper_fixes: dict[int, int] = {}
    github_failed = False
    if plans and args.reopen_keeper:
        gh_issues, complete = fetch_github_open_issues()
        if not complete:
            github_failed = True
            print('⚠️ GitHub 侧拉取不完整，无法判断保留卡状态（不得当成「无需重开」）', file=sys.stderr)
        else:
            keeper_fixes = keeper_state_fixes(plans, details, {int(i['number']) for i in gh_issues})

    # 失败态：拿不到输入就不动手（#171 的纪律）
    if (failed or github_failed) and args.apply:
        print('❌ 有输入读取失败，结论不可信，拒绝执行清理（先查清再跑）', file=sys.stderr)
        text, _ = render(plans, failed, applied=False, keeper_fixes=keeper_fixes)
        print(text)
        return EXIT_UNKNOWN

    applied = False
    actions_failed: list[int] = []
    if args.apply:
        # 先修保留卡状态，再关重复卡：顺序反了的话，中间态会出现「这组一张 open 都没有」
        for gh, keeper in keeper_fixes.items():
            try:
                reopen_issue(keeper)
                print(f'  🔓 GitHub #{gh}：已重开保留卡 CNB #{keeper}（GitHub 侧仍 open）')
            except Exception as exc:  # noqa: BLE001
                actions_failed.append(keeper)
                print(f'  ❌ GitHub #{gh}：重开 CNB #{keeper} 失败：{exc}', file=sys.stderr)
        for gh, p in plans.items():
            for n in p['remove']:
                try:
                    close_issue(n)
                    print(f'  ✅ GitHub #{gh}：已关闭 CNB #{n}')
                except Exception as exc:  # noqa: BLE001  单张失败不掩盖其余
                    actions_failed.append(n)
                    print(f'  ❌ GitHub #{gh}：关闭 CNB #{n} 失败：{exc}', file=sys.stderr)
        applied = True

    text, code = render(plans, failed, applied=applied, keeper_fixes=keeper_fixes)
    print(text)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    'plans': {str(k): v for k, v in plans.items()},
                    'unkeyed': unkeyed,
                    'read_failed': failed,
                    'actions_failed': actions_failed,
                    'keeper_fixes': {str(k): v for k, v in keeper_fixes.items()},
                    'applied': applied,
                },
                ensure_ascii=False,
                indent=2,
            )
            + '\n',
            encoding='utf-8',
        )
        print(f'\n已写入 {args.json_out}')

    if actions_failed:
        print(f'\n❌ 有 {len(actions_failed)} 张清理失败：{actions_failed}')
        return EXIT_ACTIONED
    if failed:
        print('\n⚠️ 数据不完整，本次结论不可信（有卡读不到）')
        return EXIT_UNKNOWN
    if plans and not applied:
        print('\n（dry-run）加 --apply 才真正执行')
        return EXIT_ACTIONED
    print('\n✅ 无重复镜像卡' if not plans else '\n✅ 清理完成')
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
