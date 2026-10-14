#!/usr/bin/env python3
"""重复镜像卡清理：同一 GitHub 卡在 CNB 侧建了多张时，留一张、删其余（源 CNB #450）。  <!-- cross-repo-ref-allow -->

## 为什么是「删」而不是「关」

`check_duplicate_mirrors.py` 只负责**发现**（只读）。清理是人的决定，故本脚本
**默认 dry-run**，`--apply` 才动手；且清理方式选**删除**而非关闭：

- 重复卡是**纯噪声**——它们是同一轮建卡作业把同一张 GitHub 卡重复建出来的副本；
- 实测 224 张重复卡**全部零评论、标签与正文（除快照时间戳）与保留卡一致**，
  删掉**不丢任何信息**；
- 留成 `closed` 只会把「同一张卡的第二份」永久留在看板里，下一个人仍要逐张分辨。

> ⚠️ 但「零评论」是**当前实测**，不是**结构性保证**。若某张重复卡日后被人工评论过，
> 本脚本的判据（见下）会**优先保留有评论的那张**——所以判据是可重放的，不是一次性特例。

## 保留判据（可重放，逐条带依据）

1. **有评论的卡优先**——评论是**不可再生的信息**，重复卡里唯一「删了就没了」的东西；
2. 同为有/无评论 ⇒ **留 CNB 编号最小**的那张（最早创建，一般是原卡）；
3. 留的那张**状态不被本脚本改动**。

⚠️ 特别注意本仓（CNB）**#167** 那张卡：它对应 GitHub 编号 `2118`，带 38 条评论、
且被人工关过（拆卡转移），而 9 张重复卡全是空的 `open`。按判据 1 保留 CNB #167 ——
它才是唯一的正本。**不要**因为「#167 是 closed、重复卡是 open」就去保留重复卡。

## 失败态（#171 的纪律）

拿不到输入（CNB 列表 / 详情读取失败）⇒ **退出码 2 并声明结论不可信**，
**不得**因为「读不到」就退化成一个看起来正常的结论。
调用方对 `--apply` 也必须先确认 `read_failed == 0` 才动手。

## 用法

    python scripts/bridge/cleanup_duplicate_mirrors.py                 # dry-run，列出将删的卡
    python scripts/bridge/cleanup_duplicate_mirrors.py --apply         # 真正删除
    python scripts/bridge/cleanup_duplicate_mirrors.py --apply --close # 改为「关闭」而非删除
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
from github_cnb_issues import cnb_api, get_cnb_issue  # noqa: E402

EXIT_OK = 0
EXIT_ACTIONED = 1  # dry-run 下有可清理项（便于 CI 判红），或 apply 后有失败
EXIT_UNKNOWN = 2


def _comment_count(detail: dict[str, Any]) -> int:
    return int(detail.get("comment_count") or 0)


def pick_keeper(details: list[dict[str, Any]]) -> tuple[int, list[int]]:
    """给定同一 GitHub 编号下的多张卡详情，返回 `(保留卡号, 其余卡号)`。

    判据（见文件头）：**有评论的优先，其余按编号升序取最小**。
    纯函数，供单测直接用。
    """

    def sort_key(d: dict[str, Any]) -> tuple[int, int]:
        # 第一维降序（有评论优先）用 -count；第二维升序用 number
        return (-_comment_count(d), int(d["number"]))

    ordered = sorted(details, key=sort_key)
    keeper = int(ordered[0]["number"])
    return keeper, [int(d["number"]) for d in ordered[1:]]


def plan(grouped: dict[int, list[int]], details: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """对每个重复的 GitHub 编号给出 `{保留: n, 删除: [...]}`。纯函数。"""
    out: dict[int, dict[str, Any]] = {}
    for gh, numbers in sorted(grouped.items()):
        if len(numbers) < 2:
            continue
        cards = [details[n] for n in numbers]
        keeper, extras = pick_keeper(cards)
        out[gh] = {
            "keep": keeper,
            "remove": extras,
            "keep_comments": _comment_count(details[keeper]),
            "removed_comments": sum(_comment_count(details[n]) for n in extras),
        }
    return out


def _delete_issue(number: int) -> None:
    repo = "duoduobei/fundmate"
    cnb_api(f"/{repo}/-/issues/{number}", method="DELETE")


def _close_issue(number: int) -> None:
    repo = "duoduobei/fundmate"
    cnb_api(
        f"/{repo}/-/issues/{number}",
        method="PATCH",
        payload={"state": "closed", "state_reason": "not_planned"},
    )


def render(plans: dict[int, dict[str, Any]], failed: list[int], *, mode: str, applied: bool) -> tuple[str, int]:
    total = sum(len(p["remove"]) for p in plans.values())
    lost_comments = sum(p["removed_comments"] for p in plans.values())

    lines = ["# 重复镜像卡清理（CNB #450）", ""]
    lines.append(
        f"- 模式：{'删除（DELETE）' if mode == 'delete' else '关闭（PATCH closed）'}"
        + ("　**已执行**" if applied else "　dry-run（未动手）")
    )
    lines.append(f"- 重复的 GitHub 编号：{len(plans)} 个")
    lines.append(f"- 将清理的卡：{total} 张")
    lines.append(
        f"- 被清理卡上的评论总数：{lost_comments} 张"
        + ("" if lost_comments == 0 else "　⚠️ 非零即违反保留判据，应停下核实")
    )
    lines.append(f"- 读取失败的卡：{len(failed)} 张" + (f"（{failed[:20]}）" if failed else ""))
    lines.append("")

    if plans:
        lines.append("## 清单（GitHub 编号 → 保留 / 清理，附保留依据）")
        lines.append("")
        for gh, p in plans.items():
            why = "有评论" if p["keep_comments"] else "编号最小"
            lines.append(
                f"- GitHub #{gh}：保留 CNB #{p['keep']}（{why}，{p['keep_comments']} 条评论）；清理 {p['remove']}"
            )
        lines.append("")

    if failed:
        lines.append("## ⚠️ 结论不可信")
        lines.append("")
        lines.append(
            f"有 {len(failed)} 张镜像卡读取失败，它们**未被纳入任何判定**。上面的清单是**下限**，**不得**据此执行清理。"
        )
        lines.append("")

    if total == 0 and not failed:
        lines.append("## 无重复卡")
        lines.append("")

    exit_code = EXIT_UNKNOWN if failed else (EXIT_ACTIONED if total else EXIT_OK)
    return "\n".join(lines), exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重复镜像卡清理（CNB #450）")
    parser.add_argument("--apply", action="store_true", help="真正执行清理（默认 dry-run）")
    parser.add_argument("--close", action="store_true", help="改为关闭而非删除（默认删除）")
    parser.add_argument("--limit", type=int, default=None, help="只读前 N 张镜像卡（调试用）")
    parser.add_argument("--json", dest="json_out", default=None, help="把结构化清单写到该文件")
    args = parser.parse_args(argv)

    details_list, failed = collect(limit=args.limit)
    grouped, unkeyed = group_by_github_number(details_list)

    # 详情按编号索引，便于 pick_keeper 取评论数
    details: dict[int, dict[str, Any]] = {}
    for card in details_list:
        n = int(card["number"])
        try:
            details[n] = get_cnb_issue(n)
        except Exception as exc:  # noqa: BLE001  读不到 ⇒ 记失败，不猜
            failed.append(n)
            print(f"  ⚠️ 读取 CNB #{n} 详情失败：{exc}", file=sys.stderr)

    plans = plan(grouped, details)

    # 失败态：拿不到输入就不动手（#171 的纪律）
    if failed and args.apply:
        print("❌ 有卡读取失败，结论不可信，拒绝执行清理（先查清再跑）", file=sys.stderr)
        text, _ = render(plans, failed, mode="close" if args.close else "delete", applied=False)
        print(text)
        return EXIT_UNKNOWN

    applied = False
    actions_failed: list[int] = []
    if args.apply:
        mode = "close" if args.close else "delete"
        act = _close_issue if args.close else _delete_issue
        for gh, p in plans.items():
            for n in p["remove"]:
                try:
                    act(n)
                    print(f"  ✅ GitHub #{gh}：已{'关闭' if args.close else '删除'} CNB #{n}")
                except Exception as exc:  # noqa: BLE001  单张失败不掩盖其余
                    actions_failed.append(n)
                    print(f"  ❌ GitHub #{gh}：清理 CNB #{n} 失败：{exc}", file=sys.stderr)
        applied = True

    text, code = render(plans, failed, mode="close" if args.close else "delete", applied=applied)
    print(text)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "plans": {str(k): v for k, v in plans.items()},
                    "unkeyed": unkeyed,
                    "read_failed": failed,
                    "actions_failed": actions_failed,
                    "applied": applied,
                    "mode": "close" if args.close else "delete",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\n已写入 {args.json_out}")

    if actions_failed:
        print(f"\n❌ 有 {len(actions_failed)} 张清理失败：{actions_failed}")
        return EXIT_ACTIONED
    if failed:
        print("\n⚠️ 数据不完整，本次结论不可信（有卡读不到）")
        return EXIT_UNKNOWN
    if plans and not applied:
        print("\n（dry-run）加 --apply 才真正执行")
        return EXIT_ACTIONED
    print("\n✅ 无重复镜像卡" if not plans else "\n✅ 清理完成")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
