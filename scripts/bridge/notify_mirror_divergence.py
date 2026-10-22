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

环境变量：`CNB_TOKEN`（平台注入；缺失时自动转 dry-run）、`CNB_API_ENDPOINT`
（默认 `https://api.cnb.cool`，与 `github_cnb_issues.py` 同一套，见其 `cnb_api`）。

调用方不限于 `sync/mirror`：dev 的 `.cnb.yml` 也把它挂在**每日 issue 镜像作业**的
分叉自检之后（那边查的是 CNB 仓内 `main` ↔ `dev` 的分叉，同一个「大声失败」诉求）。
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_cnb_issues import _cnb_repo, cnb_api  # noqa: E402

TITLE = '[镜像断链] GitHub→CNB 代码镜像已停摆（需人工救援）'
MAX_ISSUE_BODY = 6000

# 断链提醒卡正文的固定骨架 —— 与单测共享，改这里等于改契约。
BODY_TEMPLATE = """## 发生了什么

CNB 仓内的**分支分叉自检**（`.cnb.yml` → `dev` 每日 cron → `分支分叉自检（断链即建卡）`）
判定 `main` / `dev` 之间出现了新形态，或判据**拿不到输入**，退出码非零，于是在这里建卡。

⚠️ 本卡**不等于**「GitHub→CNB 已分叉」。那个判据是跨仓的
`scripts/bridge/check_cross_repo_dev_divergence.py`，本卡来自仓内的
`scripts/bridge/check_branch_divergence.py`。两者别混——查错了地方会得到「一切正常」。

⚠️ 退出码 **2 = 拿不到输入**（典型：定时构建只 fetch 了分支键那一条，`origin/main` 不在工作区），
那是「结论不可信」，**不是**「已分叉」——别照着下面「怎么修」去 cherry-pick。

## 现场

{report}

## 怎么修（分情况，别一律 cherry-pick）

先看上列**「现场」**给的是哪一类结论：

- **新形态**（`main` 上有未经 `dev` 中转的提交）⇒ 查清来路，**走 PR 并回 `dev`**；
- **合规发版**（`main` 独有提交全是 `dev` → `main` 的 merge，`dev` 领先一大截）⇒
  **这是本仓正常态，不是故障**——本卡属于**假红**，处置是修判据（见下），不是改分支；
- **判据不可用**（退 2，拿不到输入）⇒ 先让判据能跑（fetch 到被比较的 ref），再谈分叉。

> ⚠️ **不要** force push、**不要**删除任一侧的独有提交：那会静默丢改动。
> ⚠️ 别靠「抹平分支」消卡：卡是信号，分支是事实，改事实去迁就信号就本末倒置了。

## 这张卡为什么存在

「crontab 红了没人盯」是本仓反复出现的失败形态（2026-10-11 白丢大半天）。故让它建卡。
但**建卡不等于判据对**：本卡（CNB #607）就是判据本身出错后，卡照建、每轮照挂三轮、
卡面「现场」还空着的实例——**信号响亮与信号正确是两件事**。

---

> 本卡由 `.cnb.yml` 的定时作业在分叉自检退出码非零时自动创建（源 CNB #607 / #118 / #123）。
> 同一状态再次运行时，只在本卡追加评论，不重复建卡。
> ⚠️ 「每轮都追加」意味着**判据错了也会每轮追加**——三轮以上就该怀疑判据，而不是继续照做。
"""


def build_body(report_paths: list[str]) -> str:
    """把各分支的现场报告拼成卡面正文。读不到的文件跳过（分支可能本来就没有）。"""
    parts: list[str] = []
    for p in report_paths:
        try:
            text = Path(p).read_text(encoding='utf-8').strip()
        except OSError:
            continue
        if text:
            parts.append(text)
    report = '\n\n'.join(parts) or '_（未拿到现场报告，请直接看本次构建日志）_'
    body = BODY_TEMPLATE.format(report=report)
    if len(body) > MAX_ISSUE_BODY:
        body = body[:MAX_ISSUE_BODY] + '\n\n> （正文过长已截断，完整清单见构建日志）'
    return body


def build_comment(report_paths: list[str]) -> str:
    """重复断链时追加的评论：只带**现场**，不复述整张卡的修法。

    只截取「## 现场」与下一个二级标题之间的那一段——直接 split 会把后面的
    「怎么修 / 为什么需要这张卡」一起带过来，等于每隔一小时把整张卡重贴一遍。
    """
    body = build_body(report_paths)
    if '## 现场' not in body:
        return '## 又检测到一次断链\n\n' + body
    after = body.split('## 现场', 1)[1]
    section = after.split('\n## ', 1)[0].strip()
    return '## 又检测到一次断链\n\n' + section + '\n'


def find_open_alert() -> tuple[int, str] | None:
    """找未关闭的同题提醒卡。返回 (编号, 状态) 或 None。

    幂等键 = **标题**：镜像任务是无人值守的，用标题足够（正文每次都不同，
    不能当键；编号在别的仓）。

    **「查不到」和「没查到」必须分开**：列表调用本身失败（网络 / 鉴权）时让异常
    抛出去，由调用方决定**不建卡**——若把「查不到」当成「没有」，下一个小时
    会再建一张，正好制造本设计要避免的噪音。分页拉全再按标题精确匹配
    （不依赖未经证实的 `title` 查询参数，与 `list_cnb_issues` 同构）。
    """
    repo = _cnb_repo()
    page = 1
    while True:
        qs = urllib.parse.urlencode({'page': page, 'page_size': 100, 'state': 'open'})
        batch = cnb_api(f'/{repo}/-/issues?{qs}') or []
        if not isinstance(batch, list):
            return None
        for it in batch:
            if isinstance(it, dict) and it.get('title') == TITLE:
                return int(it.get('number')), str(it.get('state', ''))
        if len(batch) < 100:
            return None
        page += 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--report', nargs='+', required=True, help='各分支现场报告文件')
    ap.add_argument('--dry-run', action='store_true', help='只打印，不建卡/评论')
    args = ap.parse_args(argv)

    token = os.environ.get('CNB_TOKEN', '')
    body = build_body(args.report)

    if args.dry_run or not token:
        if not token:
            print('[warn] 未设置 CNB_TOKEN，转为 dry-run', file=sys.stderr)
        print('=' * 60)
        print(TITLE)
        print('=' * 60)
        print(body)
        return 0

    try:
        existing = find_open_alert()
    except (OSError, RuntimeError, ValueError) as exc:
        # HTTPError / URLError 都是 OSError 的子类；RuntimeError = 缺 token；ValueError = JSON 坏
        print(f'[error] 查询既有提醒卡失败，本轮不建卡（避免重复建卡噪音）：{exc}', file=sys.stderr)
        return 1
    try:
        repo = _cnb_repo()
        if existing:
            number, _ = existing
            cnb_api(
                f'/{repo}/-/issues/{number}/comments',
                method='POST',
                payload={'body': build_comment(args.report)},
            )
            print(f'[ok] 已在本卡 #{number} 追加断链评论（不重复建卡）')
        else:
            created = cnb_api(f'/{repo}/-/issues', method='POST', payload={'title': TITLE, 'body': body})
            number = (created or {}).get('number', '?')
            print(f'[ok] 已建断链提醒卡 #{number}')
    except (OSError, RuntimeError, ValueError) as exc:
        # 建卡/评论失败**不假装成功**：日志里要能看到真因（调用方的 `|| true`
        # 保证它不把「镜像断了」这个真问题盖掉）。
        print(f'[error] 建卡/评论失败：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
