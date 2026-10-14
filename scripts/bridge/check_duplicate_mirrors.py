#!/usr/bin/env python3
"""重复镜像卡自检：同一 GitHub 卡在 CNB 侧有几张镜像卡（源 CNB #450）。  <!-- cross-repo-ref-allow -->

## 为什么要有它

#450 的 224 张重复卡是**三天里一轮一轮攒出来的**（同一 GitHub 编号最多 11 张），  <!-- cross-repo-ref-allow -->
而全程**零信号**：每轮建卡都成功、日志都是「✅ CNB #N ← GitHub #M」，
`mirror_state_sync` 只关心「GitHub 关了 CNB 还没关」，
`check_mirror_refs` 只关心「正文引用的行号还在不在」——
**没有任何一条作业在问「这张卡是不是已经建过了」**。

这与 #171 / #179 是同一族：不是缺功能，是缺**能问出这件事**的作业。
修复根因（`harvest_existing` 不再短路）只能防住未来；存量重复卡需要被发现，
且**再去重复**之后还需要一道网盯着它别回潮。

## 判据

镜像卡正文里的幂等键 `GitHub 编号：#N`（与建卡脚本同一形状，不抄第二份正则的是
`check_mirror_refs` 那边的纪律；这里必须自己解析，见下）。

- 同一 `N` 对应 **>1 张** CNB 卡 ⇒ 重复，**退出码 1**；
- 拿不到输入（CNB 列表 / 详情读取失败）⇒ **退出码 2** 并声明「结论不可信」，
  **不得**降级成「无重复」——这是 #171 的教训（拿不到 ≠ 没有）。

## 边界

- **只读**：不改卡、不关卡、不删卡、不落状态文件。清理是人的决定
  （删哪张、留哪张要看评论与标签，脚本不猜）；
- 逐张拉详情是必要的：CNB 列表接口**不返回 body**，而幂等键在正文里；
- 卡片数量大时请求多（实测 387 张卡 ≈ 400 次请求），与 `--report-local` 同一量级。

## 用法

    python scripts/bridge/check_duplicate_mirrors.py --report            # 只报告
    python scripts/bridge/check_duplicate_mirrors.py --report --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from github_cnb_issues import MIRROR_LABEL, extract_github_number, get_cnb_issue, list_cnb_issues  # noqa: E402

EXIT_OK = 0
EXIT_DUPES = 1
EXIT_UNKNOWN = 2


def group_by_github_number(cards: list[dict[str, Any]]) -> tuple[dict[int, list[int]], list[int]]:
    """把镜像卡按幂等键分组。

    返回 `(映射, 抠不到键的卡号)`。**两者必须分开返回**：抠不到键的卡既不能算
    「重复」也不能算「不重复」，把它们混进映射会让结论失真（#450 里就有一张
    「标签测试-可删」没键）。
    """
    grouped: dict[int, list[int]] = defaultdict(list)
    unkeyed: list[int] = []
    for card in cards:
        number = int(card['number'])
        gh = extract_github_number(card.get('body') or '')
        if gh is None:
            unkeyed.append(number)
            continue
        grouped[gh].append(number)
    for v in grouped.values():
        v.sort()
    return grouped, unkeyed


def _is_mirror(card: dict[str, Any]) -> bool:
    return any(
        (lb.get('name') if isinstance(lb, dict) else lb) == MIRROR_LABEL for lb in (card.get('labels') or [])
    )


def collect(*, limit: int | None = None) -> tuple[list[dict[str, Any]], list[int]]:
    """拉全部 CNB 卡详情，返回 `(镜像卡详情, 读取失败的卡号)`。"""
    cards: list[dict[str, Any]] = []
    for state in ('open', 'closed'):
        cards.extend(list_cnb_issues(state))
    mirror_cards = [c for c in cards if _is_mirror(c)]
    if limit:
        mirror_cards = mirror_cards[:limit]

    print(f'📥 CNB 卡 {len(cards)} 张，其中镜像卡 {len(mirror_cards)} 张，逐张读取正文…', file=sys.stderr)
    details: list[dict[str, Any]] = []
    failed: list[int] = []
    for i, card in enumerate(mirror_cards, 1):
        number = int(card['number'])
        try:
            details.append(get_cnb_issue(number))
        except Exception as exc:  # noqa: BLE001  # 读不到 ≠ 没重复，单独记账
            failed.append(number)
            print(f'  ⚠️ 读取 CNB #{number} 失败（不计入任何一类）：{exc}', file=sys.stderr)
        if i % 50 == 0:
            print(f'  …已读 {i}/{len(mirror_cards)}', file=sys.stderr)
    return details, failed


def render(grouped: dict[int, list[int]], unkeyed: list[int], failed: list[int]) -> tuple[str, int]:
    """渲染报告并给出退出码。纯函数，供单测直接用。"""
    dupes = {gh: ns for gh, ns in sorted(grouped.items()) if len(ns) > 1}
    total_extra = sum(len(ns) - 1 for ns in dupes.values())

    lines: list[str] = ['# 重复镜像卡自检（CNB #450）', '']
    lines.append(f'- 镜像卡读取失败：{len(failed)} 张' + (f'（{failed[:20]}{"…" if len(failed) > 20 else ""}）' if failed else ''))
    lines.append(f'- 抠不到幂等键的镜像卡：{len(unkeyed)} 张' + (f'（{unkeyed[:20]}）' if unkeyed else ''))
    lines.append(f'- 幂等键去重后：{len(grouped)} 个 GitHub 编号')
    lines.append(f'- **重复的 GitHub 编号：{len(dupes)} 个，多出来的卡：{total_extra} 张**')
    lines.append('')

    if dupes:
        lines.append('## 重复清单（GitHub 编号 → CNB 卡号，升序）')
        lines.append('')
        for gh, ns in dupes.items():
            lines.append(f'- GitHub #{gh} → {len(ns)} 张：{ns}')
        lines.append('')

    if failed:
        lines.append('## ⚠️ 结论不可信')
        lines.append('')
        lines.append(
            f'有 {len(failed)} 张镜像卡读取失败，它们**既未被判重复、也未被判不重复**。'
            '上面的重复数是**下限**，不得叙述成「已查清」。'
        )
        lines.append('')

    lines.append('## 处置（人工）')
    lines.append('')
    lines.append('- 留哪张、删哪张要看**评论与标签**，脚本不猜（本作业只读）：')
    lines.append('  - 一般留**编号最小**的那张（最早的、可能有讨论）；')
    lines.append('  - 但若某张有 `GitHub 已关闭` 状态回流评论、或已被人工改过标签，优先留它；')
    lines.append('- 删除前先确认没有评论会被一并丢弃；')
    lines.append('- 根因修复见 `harvest_existing()`（不再拿状态文件缓存当已镜像全集）。')

    exit_code = EXIT_UNKNOWN if failed else (EXIT_DUPES if dupes else EXIT_OK)
    return '\n'.join(lines), exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='重复镜像卡自检（CNB #450）')
    parser.add_argument('--report', action='store_true', help='只报告（默认行为）')
    parser.add_argument('--json', dest='json_out', default=None, help='把结构化的重复映射写到该文件')
    parser.add_argument('--limit', type=int, default=None, help='只读前 N 张镜像卡（调试用）')
    args = parser.parse_args(argv)

    details, failed = collect(limit=args.limit)
    grouped, unkeyed = group_by_github_number(details)
    text, code = render(grouped, unkeyed, failed)
    print(text)

    if args.json_out:
        payload = {
            'duplicates': {str(k): v for k, v in grouped.items() if len(v) > 1},
            'unkeyed': unkeyed,
            'read_failed': failed,
            'exit_code': code,
        }
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'\n已写入 {args.json_out}')

    if code == EXIT_DUPES:
        print('\n❌ 存在重复镜像卡（同一 GitHub 卡被建了多次）')
    elif code == EXIT_UNKNOWN:
        print('\n⚠️ 数据不完整，本次结论不可信（有卡读不到）')
    else:
        print('\n✅ 无重复镜像卡')
    return code


if __name__ == '__main__':
    sys.exit(main())
