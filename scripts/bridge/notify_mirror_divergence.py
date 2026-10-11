# -*- coding: utf-8 -*-
"""镜像断链提醒：把「GitHub→CNB 代码镜像停摆」这件事从构建日志里捞出来。

## WHY 有这个脚本

`sync/mirror` 分支上的小时级镜像任务**只允许快进**。CNB 侧一旦出现 GitHub 没有的
提交（例如有人在 CNB 合了 PR），`merge-base --is-ancestor` 就判否，任务 `exit 1`。

问题不在「判否」——那是正确的保守行为；问题在**判否之后没人知道**：

  - 它是 crontab，不是 PR check，红了没人盯；
  - 失败原本只打一行日志，而构建日志不会主动推给任何人；
  - 于是从外部看，「停摆」和「正常」**完全一样**。2026-10-11 那次白丢了大半天。

本脚本就是「层 1：让失败可见」（CNB #118 / #123）：断链时在 CNB 建一张提醒卡。
配上 `.cnb.yml` 里「层 2：打印两侧独有提交清单」，接手的人拿到卡就能直接照做救援。

## 边界

- **只建卡，不修链**。救援需要人判断（哪些提交该回流、冲突怎么解），脚本不猜。
- **绝不回写 GitHub**：CNB 环境没有 GitHub 凭据（对 `api.github.com` 匿名 POST 返 401），
  且回写 GitHub 是另一条管道（`.github/workflows/cnb-github-backfill.yml`）的职责。
- **幂等**：同一断链状态重复运行不应刷屏。按「未关闭的同标题卡是否已存在」判定，
  存在则在**该卡追加评论**而不是新建（重复告警比不告警更消耗人的注意力）。
- **建卡失败 ≠ 任务成功**：调用方（`.cnb.yml`）不因本脚本失败而改退出码——
  否则「提醒挂了」会盖掉「镜像断了」这个真问题。

## 用法

    # 本地演练（不建卡，只打印将要发送的内容）
    python scripts/bridge/notify_mirror_divergence.py --report /tmp/report-dev.txt --dry-run

    # 真实调用（由 .cnb.yml 在断链分支执行）
    python scripts/bridge/notify_mirror_divergence.py --report /tmp/report-dev.txt /tmp/report-main.txt

环境变量：`CNB_TOKEN`（平台注入）、`CNB_WEB_HOST` / `CNB_WEB_PROTOCOL`（默认 cnb.cool / https）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TITLE = "[镜像断链] GitHub→CNB 代码镜像已停摆（需人工救援）"
SLUG = "duoduobei/fundmate"
MAX_ISSUE_BODY = 6000

# 断链提醒卡正文的固定骨架 —— 与单测共享，改这里等于改契约。
BODY_TEMPLATE = """## 发生了什么

GitHub→CNB 的**代码镜像**判定「两侧已分叉」，按设计拒绝快进并退出非零。
这是**断链**：在此之前，CNB 的 `dev` / `main` 每小时都会自动跟上 GitHub。

## 现场

{report}

## 怎么修（人工）

1. 把上面「CNB 独有」的提交 **cherry-pick 成 `rescue/` 分支**；
2. 对 **GitHub 开 PR**（base 填对应的 `dev` / `main`）——CNB 侧只读，不要在 CNB 合 PR；
3. 合并后等下一轮整点，日志应变成 `[dev] 已一致` / `[main] 已一致` —— 那才算闭环。

> ⚠️ **不要** force push、**不要**删除 CNB 侧的独有提交：那会静默丢改动。
> ⚠️ **不要**给镜像任务加 `--force`：断链要「大声失败」，不是「自动抹平」。

## 为什么需要这张卡

根因是数学上的：镜像只允许快进，而在 CNB 侧合 PR 必然产生 GitHub 没有的 merge commit。
两者不可能共存。这也是为什么 CNB 仓按设计**只读**。

---

> 本卡由 `sync/mirror` 定时任务在检测到断链时自动创建（CNB #118 / #123）。
> 同一断链状态再次运行时，只在本卡追加评论，不重复建卡。
"""


def build_body(report_paths: list[str]) -> str:
    """把各分支的现场报告拼成卡面正文。读不到的文件跳过（分支可能本来就没有）。"""
    parts: list[str] = []
    for p in report_paths:
        try:
            text = Path(p).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            parts.append(text)
    report = "\n\n".join(parts) or "_（未拿到现场报告，请直接看本次构建日志）_"
    body = BODY_TEMPLATE.format(report=report)
    if len(body) > MAX_ISSUE_BODY:
        body = body[:MAX_ISSUE_BODY] + "\n\n> （正文过长已截断，完整清单见构建日志）"
    return body


def build_comment(report_paths: list[str]) -> str:
    """重复断链时追加的评论：只带**现场**，不复述整张卡的修法。

    只截取「## 现场」与下一个二级标题之间的那一段——直接 split 会把后面的
    「怎么修 / 为什么需要这张卡」一起带过来，等于每隔一小时把整张卡重贴一遍。
    """
    body = build_body(report_paths)
    if "## 现场" not in body:
        return "## 又检测到一次断链\n\n" + body
    after = body.split("## 现场", 1)[1]
    section = after.split("\n## ", 1)[0].strip()
    return "## 又检测到一次断链\n\n" + section + "\n"


def _api_base() -> str:
    host = os.environ.get("CNB_WEB_HOST") or "cnb.cool"
    proto = os.environ.get("CNB_WEB_PROTOCOL") or "https"
    return f"{proto}://{host}"


def _request(method: str, url: str, payload: dict | None, token: str) -> object:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (固定 https 主机)
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else None


def find_open_alert(token: str) -> tuple[int, str] | None:
    """找未关闭的同题提醒卡。返回 (编号, 状态) 或 None。

    幂等键 = **标题**：镜像任务是无人值守的，用标题足够（正文每次都不同，
    不能当键；编号在别的仓）。找不到就返回 None，由调用方决定建卡。
    """
    query = urllib.parse.urlencode({"state": "open", "title": TITLE})
    url = f"{_api_base()}/{SLUG}/-/issues?{query}"
    try:
        issues = _request("GET", url, None, token)
    except (urllib.error.URLError, ValueError) as exc:  # pragma: no cover - 网络路径
        print(f"[warn] 查询既有提醒卡失败：{exc}", file=sys.stderr)
        return None
    if not isinstance(issues, list):
        return None
    for it in issues:
        if isinstance(it, dict) and it.get("title") == TITLE:
            return int(it.get("number")), str(it.get("state", ""))
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", nargs="+", required=True, help="各分支现场报告文件")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不建卡/评论")
    args = ap.parse_args(argv)

    token = os.environ.get("CNB_TOKEN", "")
    body = build_body(args.report)

    if args.dry_run or not token:
        if not token:
            print("[warn] 未设置 CNB_TOKEN，转为 dry-run", file=sys.stderr)
        print("=" * 60)
        print(TITLE)
        print("=" * 60)
        print(body)
        return 0

    existing = find_open_alert(token)
    if existing:
        number, _ = existing
        _request(
            "POST",
            f"{_api_base()}/{SLUG}/-/issues/{number}/comments",
            {"body": build_comment(args.report)},
            token,
        )
        print(f"[ok] 已在本卡 #{number} 追加断链评论（不重复建卡）")
    else:
        created = _request(
            "POST", f"{_api_base()}/{SLUG}/-/issues", {"title": TITLE, "body": body}, token
        )
        number = created.get("number") if isinstance(created, dict) else "?"
        print(f"[ok] 已建断链提醒卡 #{number}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
