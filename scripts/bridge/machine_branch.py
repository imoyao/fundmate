#!/usr/bin/env python3
"""跨仓同步的**机器分支 + PR 通道**：把「推裸 ref」换成「推中间态分支、由门禁放行」
（源 CNB #450，2026-10-14）。  <!-- cross-repo-ref-allow -->

为什么需要它
------------
本仓跨仓同步原先只有一条路：CNB 构建里 `git push <github> dev`（git-sync 插件）。
它撞在**两道闸**上，而且都不是「配置写错了」：

| 闸 | 报错 | 为什么 git-sync 自己过不去 |
|---|---|---|
| **非快进** | `! [rejected] dev -> dev (fetch first)` | push 刻意不开 `force`（反向护栏，对的）⇒ GitHub 只要多一笔就永久被拒 |
| **分支保护** | `GH006: Protected branch update failed … Required status check "质量门禁汇总" is expected` | `质量门禁汇总`（`ci.yml` 的 `gate`）**只在 PR 上产生**（`if: github.event_name == 'pull_request'`）⇒ 直推裸 ref 时它根本不跑 |

第二条是关键：**它不是要绕过门禁，是「直推需要一条根本不存在的检查」这个悖论。**
解法不是关掉门禁（用户 2026-10-14 明确「质量门禁不能关」），而是**换一种通行方式**：

    推一次性机器分支（该分支无保护规则） → 在 GitHub 开 PR 到 dev
      → PR 事件让 `质量门禁汇总` **真的跑起来** → 绿了就 auto-merge

门禁**一个检查都没少**，是**被满足**了。

与「CNBDEV 中转分支」的区别（这是本脚本存在的理由）
---------------------------------------------------
两者长得像，判据完全不同（`docs/dev/github-cnb-mirror.md` §21 / §18.2）：

| | `CNBDEV` 长期中转（否） | **本脚本：一次性机器分支（是）** |
|---|---|---|
| 推过去的是什么 | 又一条**长期分支**，活着、要维护 | **一次性 ref**，PR 合完即亡 |
| 有没有解分叉 | 没有——冲突换个分支名再演一遍 | **有**——先 merge 再推，本来快进 |
| 违反「禁止长期分支」 | 是 | 否 |

脚本做什么（**只做安全的那些**）
--------------------------------
1. 取两侧 `dev` 的真实 ref；
2. **以一侧为基线**把另一侧 merge 进来（默认 CNB 为基线，方向必须先定）；
3. **无冲突** ⇒ 把结果推成机器分支（默认 `bridge/github-dev`）、开 PR（可选 `--auto-merge`）；
4. **有冲突** ⇒ **停下、什么都不推**，打印冲突文件清单，交人工；
5. **拿不到输入**（fetch 失败 / ref 缺失）⇒ 退出码 2 且明说「结论不可信」——
   **不得**退化成「无需同步」（#171 / #450 的假绿纪律）。

⚠️ **它永远解不掉那 16 处冲突**：冲突面是 `.cnb.yml` / `AGENTS.md` 这类治理文件，
解错等于悄悄改掉治理规则。故 `--resolve` 之类一键开关**有意不提供**——
这就是为什么 B'（自动到冲突为止）必须与 C（治理文件只在 CNB 改）一起上。

先决条件（读不到，只能由人确认）
--------------------------------
`dev` 的 classic branch protection 里**不能勾「Require approvals」**。勾了的话机器 PR
会卡在等人 Approve，等于把死锁从「永远红」换成「永远等」。本脚本**读不到** protection
（匿名 401），故它只负责把 PR 开出来并回报「门禁 / 合并许可」的观测结果，
**不假装自己知道**。

用法
----
    # 演练：只报会怎么合、有没有冲突（不建分支、不联网写）
    python scripts/bridge/machine_branch.py --dry-run

    # 执行：建机器分支并推 GitHub（**不**碰 dev / main）
    python scripts/bridge/machine_branch.py --apply

    # 执行并开 PR（需要 GITHUB_TOKEN / GITHUB_PAT）
    python scripts/bridge/machine_branch.py --apply --open-pr

    # 反向：以 GitHub dev 为基线，把 CNB dev 合进来
    python scripts/bridge/machine_branch.py --apply --base github

退出码：0 = 就绪（无冲突，已推 / 已开 PR）；
        1 = 有冲突，需人工解（**什么都没推**）；
        2 = 拿不到输入（fetch / ref 缺失）**或合并没跑起来**（merge 非 0 退出且
            没有冲突清单）——**结论不可信**。#2262 实测（#2259 CI 首次暴露）：
            runner 上无 git 身份时 `git merge` 直接 rc128「Committer identity
            unknown」，冲突清单为空，曾被打着「无冲突」照常推送——
            「没跑成」被读成了「跑成了」。

两处「同一事实问两次」的坑（源 CNB #573，2026-10-18 构建 `cnb-um5-1k57nplko`）
-------------------------------------------------------------------------------
① **试算只跑一次**：演练路径原先调两遍 `git merge-tree`（先取退出码、再取输出），
   而第二遍的输出被读成空 ⇒ 冲突清单**恒为空** ⇒ 有冲突也打印「✅ 无冲突」。
   一次调用同时拿码与输出（`merge_tree_conflicts()`），且「取不出路径」按**不可信**
   处理而不是「没冲突」。
② **机器分支的推送方式**：`bridge/github-dev` 是**固定名、一次性、每轮覆盖**的 ref。
   上一轮没被合掉时，本轮合并结果不含它 ⇒ 非快进被拒 ⇒ 每小时红一次却一个字节都没推。
   故**只对这一条分支**用 `--force-with-lease`（`dev` / `main` 永不开 force —— 那是
   共享事实，冲掉别人的提交不可接受）。lease 保证：万一有人在它上面动了手，仍然失败。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date

# 机器分支名：**固定、可覆盖、一次性的语义**。
# 固定（而不是带日期）是为了幂等：同一件事重复跑只更新同一条 ref，
# 不攒出 `bridge/github-dev-2026-10-14` 这种「分支列表垃圾」。
DEFAULT_MACHINE_BRANCH = 'bridge/github-dev'

DEFAULT_GITHUB_URL = 'https://github.com/imoyao/fundmate.git'
DEFAULT_GITHUB_REPO = 'imoyao/fundmate'

# fetch 落地的临时 ref（不占分支名、不影响工作区之外的任何东西）
GH_REF = 'refs/cross-bridge/gh-dev'
CNB_REF = 'refs/cross-bridge/cnb-dev'


def _git(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """跑一条 git，返回 (退出码, stdout, stderr)。

    stderr 一并返回是 #2262 事故的教训：merge 挂掉时（如 runner 无 git 身份 ⇒
    「Committer identity unknown」），错误信息全在 stderr；只留 stdout 会让调用方
    看到一个空的 `out`，把「没跑起来」读成「没冲突」。
    """
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    # stderr 照旧第三个返回（#2262 的调用方靠它区分「没跑成 / 没冲突」），
    # **另把 stderr 拼进第二个返回值**（源 CNB #567）：`git push` / `git fetch` 的拒绝原因
    # **全在 stderr**，只把 stdout 当“输出”会让「推失败」那一行打印出空原因 —— 有信号等于没信号。
    # 三值返回与「stdout 里含 stderr」是两条不同的调用约定，别把其中一条读成另一条的回归。
    out = (r.stdout or '').strip()
    err = (r.stderr or '').strip()
    return r.returncode, '\n'.join(x for x in (out, err) if x), err


def plan(base: str, machine_branch: str, merge_ref: str = 'merge') -> dict:
    """把「以谁为基线、推哪条分支、合并结果从哪来」算清楚。**纯函数**，便于钉回归网。"""
    if base == 'github':
        return {
            'base_ref': GH_REF,
            'base_name': 'GitHub',
            'merge_ref': CNB_REF,
            'merge_name': 'CNB',
            'machine_branch': machine_branch,
            'settle': merge_ref,
        }
    return {
        'base_ref': CNB_REF,
        'base_name': 'CNB',
        'merge_ref': GH_REF,
        'merge_name': 'GitHub',
        'machine_branch': machine_branch,
        'settle': merge_ref,
    }


def fetch_ref(url: str, branch: str, dest_ref: str, cwd: str | None = None) -> tuple[bool, str]:
    """把远端某分支抓到本地临时 ref（与 `dev_converge` 同款：不改工作区、不动分支）。"""
    code, out, err = _git(['fetch', '--quiet', url, f'{branch}:{dest_ref}'], cwd)
    if code != 0:
        return False, err or out or f'git fetch {url} {branch} 失败'
    return True, ''


def conflict_files(cwd: str | None = None) -> list[str]:
    """当前工作区未解的冲突文件清单（`git ls-files -u`，比 diff --diff-filter=U 稳）。"""
    code, out, _ = _git(['ls-files', '-u'], cwd)
    if code != 0:
        return []
    files = set()
    for ln in out.splitlines():
        # 每行形如：<mode> <sha> <stage>\t<path>
        if '\t' in ln:
            files.add(ln.split('\t', 1)[1].strip())
    return sorted(files)


def merge_tree_conflicts(base_ref: str, merge_ref: str, cwd: str | None = None) -> tuple[list[str] | None, str]:
    """离线试算「把 `merge_ref` 合进 `base_ref`」的冲突文件清单。

    返回 `(conflicts, detail)`：
      - `conflicts` 为 `None` ⇒ **试算本身没跑成**（git 异常 / 输出读不懂）；
        调用方必须退 2 并声明「结论不可信」，**不得**把 `None` 读成「没有冲突」（#171 纪律）。
      - `conflicts == []` ⇒ 试算成功且无冲突。

    ⚠️ 只有**一份** merge-tree 调用（源 CNB #573，2026-10-18）：此前这里跑了两遍 ——
    先取退出码，再取一次输出，而两遍之间的输出被读成了「空」⇒ 冲突清单**恒为空**，
    于是「有冲突」与「无冲突」在报告里长得一模一样（都打印「✅ 无冲突，两侧内容可合」）。
    一次调用同时拿码与输，这类「同一事实问两次、取第二次」的形态就不再有机会出错。

    `--write-tree` 的首行是 40 位 tree hash，其余 `… \t<path>` 行才是冲突路径；
    按 NUL 之后的 tab 取 `rsplit('\t', 1)` —— 路径本身可能含 tab，用 `split('\t')[1]`
    会在那种路径上取错。
    """
    code, out, _ = _git(['merge-tree', '--write-tree', base_ref, merge_ref], cwd)
    if code not in (0, 1):
        return None, f'git merge-tree 异常退出（rc{code}）'
    if code == 0:
        return [], ''
    conflicts = sorted({ln.rsplit('\t', 1)[1].strip() for ln in out.splitlines() if ln.strip().count('\t') == 1})
    if not conflicts:
        # 退出码说「有冲突」，输出里却一条路径都取不出来 —— **读不懂就不猜**：
        # 退化成「无冲突」正是 #573 那个 bug 的结论形态（报告照打印「✅ 无冲突」）。
        return None, 'git merge-tree 报有冲突，但取不出冲突路径'
    return conflicts, ''


def machine_push_args(github_url: str, machine_branch: str, cwd: str | None = None) -> list[str]:
    """机器分支的 push 参数：**只对这一条一次性 ref** 用 `--force-with-lease`。

    为什么是 lease 而不是普通 push（源 CNB #573，构建 `cnb-um5-1k57nplko`）：
    `bridge/github-dev` 是**固定名、一次性、每轮覆盖**的 ref。上一轮若还没被合掉，
    本轮合并结果的祖先里就没有它 ⇒ 非快进被拒 ⇒ 每小时红一次，却**一个字节都没推出去**。
    这与「推 `dev` 绝不开 force」不冲突：`dev` 是**共享事实**，冲掉别人的提交不可接受；
    机器分支是**本次合并结果的快照**，名字固定即为了幂等地覆盖。

    为什么 lease 还要**显式指定期望值**：`git push --force-with-lease` 的裸形态依赖
    「本地有那个 ref 的 remote-tracking 信息」，而我们从不 fetch 这条分支
    （`refs/cross-bridge/*` 才是我们抓的），于是它退化成 `(stale info)` 被拒 ——
    实测（2026-10-18，临时仓复现）：裸 lease 推已存在的分支 = `stale info`；
    `--force-with-lease=<ref>:<sha>` 才真的按预期值比对。

    期望值取**本轮刚 push 前**远端那条 ref 的 sha（现取 `ls-remote`）。取不到 ⇒ **不带**
    lease 值，按普通 push 走：宁可被拒报红，也不拿「不知道远端是什么」当覆盖依据。
    """
    ref = f'refs/heads/{machine_branch}'
    code, out, _ = _git(['ls-remote', github_url, ref], cwd)
    expected = ''
    if code == 0 and out:
        expected = out.split()[0].strip()
    if not expected:
        return ['push', github_url, f'HEAD:{ref}']
    return ['push', f'--force-with-lease={ref}:{expected}', github_url, f'HEAD:{ref}']


def build_report(
    p: dict,
    *,
    pushed: bool,
    conflicts: list[str],
    pr_url: str | None = None,
    reason: str = '',
) -> str:
    """生成给人看的结论段。

    `reason` 把「**没推**」拆成三种**完全不同**的结论（源 CNB #573，2026-10-18）：

    | reason | 发生了什么 | 下一步 |
    |---|---|---|
    | `''`（默认） | 演练模式，没执行 | 加 `--apply --push` |
    | `'push_failed'` | **合好了，推被拒 / 推不通** | 看 remote 原话、清掉远端那条旧分支 |
    | `'inconclusive'` | 试算 / 合并没跑起来 | 结论不可信，别读成「无冲突」 |

    三种原因原先共用一句「（演练模式：未推、未开 PR）」，于是构建日志里
    「合并成功但推失败」与「根本没跑」长得一模一样 —— 诊断方向被直接掉包。
    """
    lines = ['## 跨仓同步（机器分支 + PR）', '']
    lines.append(f'- 基线方向：以 **{p["base_name"]} `dev`** 为基线，合入 **{p["merge_name"]} `dev`**')
    lines.append(f'- 机器分支：`{p["machine_branch"]}`（**一次性**：PR 合完即亡，不是长期分支）')
    lines.append('')
    if conflicts:
        lines.append(f'⚠️ **有 {len(conflicts)} 个文件冲突 —— 什么都没推**（脚本刻意不自动解）。')
        lines.append('')
        for f in conflicts:
            lines.append(f'- `{f}`')
        lines.append('')
        lines.append('解冲突是**人工**动作：冲突面多为治理文件（`.cnb.yml` / `AGENTS.md`），')
        lines.append('解错等于悄悄改掉治理规则。解完再重跑本脚本。')
        return '\n'.join(lines)
    lines.append('✅ 无冲突，两侧内容可合。')
    lines.append('')
    if pushed:
        lines.append(f'已推成 `{p["machine_branch"]}`。下一步：在 GitHub 开 PR → `dev`，')
        lines.append('等 `质量门禁汇总` 绿了再合（门禁**照跑**，是「被满足」不是「被绕过」）。')
        if pr_url:
            lines.append('')
            lines.append(f'PR 已开：{pr_url}')
    elif reason == 'push_failed':
        # 「合好了但没送出去」——**最贵的一种**：分叉是真的、合并也成功了，只是推被拒。
        # 若这里沿用「演练模式」，读日志的人会以为这一轮压根没执行（#573 实测踩过）。
        lines.append(f'⚠️ **两侧已合并成功，但没推上去**（目标分支 `{p["machine_branch"]}` 未更新）。')
        lines.append('')
        lines.append('三种可能，按上面的报错原文区分：远端那条机器分支已存在且分叉（非快进）、')
        lines.append('分支保护拒绝、或凭据失效。正常路径下脚本会先用 `--force-with-lease` 覆盖')
        lines.append('**自己那条一次性分支**；它都失败，说明远端那条 ref 不是我们能动的。')
    elif reason == 'inconclusive':
        lines.append('⚠️ **合并试算 / 合并本身没跑成** —— 本轮结论不可信，不得读成「无冲突」。')
    else:
        lines.append('（演练模式：未推、未开 PR。加 `--apply` 执行。）')
    return '\n'.join(lines)


def run(args: argparse.Namespace) -> int:
    cwd = args.cwd
    ok_cnb, err_cnb = fetch_ref(args.cnb_url, args.branch, CNB_REF, cwd)
    ok_gh, err_gh = fetch_ref(args.github_url, args.branch, GH_REF, cwd)
    if not ok_cnb or not ok_gh:
        msg = ') / ('.join([e for e in (err_cnb, err_gh) if e])
        print(f'❌ 拿不到输入：{msg}', file=sys.stderr)
        # 「拿不到输入」≠「无需同步」：明确声明结论不可信，且以非 0 退出（#171 / #450）。
        print('   ⚠️ 本轮结论不可信，不得读成「已对齐、无需同步」。', file=sys.stderr)
        return 2

    p = plan(args.base, args.machine_branch)

    if args.dry_run or not args.apply:
        conflicts, detail = merge_tree_conflicts(p['base_ref'], p['merge_ref'], cwd)
        if conflicts is None:
            # 「试算没跑成」≠「没有冲突」（#171 / #450 的假绿纪律）：退 2 且明说结论不可信。
            print(f'❌ 合并试算不可用：{detail} —— 结论不可信，不得读成「无冲突」', file=sys.stderr)
            print(build_report(p, pushed=False, conflicts=[], reason='inconclusive'), file=sys.stderr)
            return 2
        print(build_report(p, pushed=False, conflicts=conflicts))
        return 1 if conflicts else 0

    # ---- 执行：在临时 worktree 里合，绝不动当前工作区 ----
    wt = f'/tmp/machine-branch-{date.today().isoformat()}'
    _git(['worktree', 'remove', '--force', wt], cwd)
    code, out, err = _git(['worktree', 'add', '--detach', wt, p['base_ref']], cwd)
    if code != 0:
        print(f'❌ 建临时 worktree 失败：{err or out}', file=sys.stderr)
        return 2
    code, _, err = _git(['merge', '--no-edit', p['merge_ref']], wt)
    conflicts = conflict_files(wt)
    if code != 0 and not conflicts:
        # merge 非 0 退出且没留下冲突清单 ⇒ 合并根本没跑起来（身份缺失 / ref 不可用 / …）。
        # #2262 实测（#2259 CI 首次暴露）：Linux runner 无 git 身份 ⇒ merge rc128
        # 「Committer identity unknown」⇒ 冲突清单为空 ⇒ 旧代码读成「无冲突」，
        # rev-parse + push 照常执行——「没跑成」被当成了「跑成了」。
        # 与「拿不到输入」同族：结论不可信，什么都不推（#171 / #450 假绿纪律）。
        print(f'❌ 合并失败（rc{code}）且未检出冲突——结论不可信，什么都没推：{err}', file=sys.stderr)
        _git(['merge', '--abort'], wt)
        _git(['worktree', 'remove', '--force', wt], cwd)
        return 2
    print(build_report(p, pushed=False, conflicts=conflicts))
    if conflicts:
        _git(['merge', '--abort'], wt)
        _git(['worktree', 'remove', '--force', wt], cwd)
        return 1

    sha_code, sha, _ = _git(['rev-parse', 'HEAD'], wt)
    if sha_code != 0 or not sha:
        print('❌ 拿不到合并结果 sha——结论不可信', file=sys.stderr)
        return 2

    if not args.push:
        print(build_report(p, pushed=False, conflicts=[]))
        print(f'\n（`--push` 未给：合并结果停在临时 worktree 的 `{sha[:8]}`，未推任何远端。）')
        return 0

    code, out, err = _git(machine_push_args(args.github_url, p['machine_branch'], wt), wt)
    if code != 0:
        # ⚠️ 必须在 `worktree remove` **之前**把 remote 的原文打出来（源 CNB #567，2026-10-18）。
        # `git push` 的进展与拒绝原因走 **stderr**（`! [rejected] … (fetch first)` /
        # `hint: Updates were rejected …`），只打 stdout 就是一句空的「❌ 推机器分支失败：」——
        # 分叉存在了两天，日志里却没有任何一行说得出「被拒 / 非快进 / 远端领先」。
        # 返回码 2 保留（「结论不可信」），另起一行点名分支 —— 后面要用它开 PR。
        print(f'❌ 推机器分支失败：{out or err or "(git 没有任何输出)"}', file=sys.stderr)
        print(f'   目标分支：{p["machine_branch"]}（未推上去；下次重跑会覆盖同一 ref）', file=sys.stderr)
        if '(fetch first)' in out or 'stale info' in out:
            # ⚠️ 这一条在 #573 之后**不应再出现**：机器分支已按「覆盖自己那条一次性分支」
            # 推送（`--force-with-lease`）。真出现 = 远端那条 ref 不是我们能动的
            # （被人动过 ⇒ lease 拒绝，或分支保护规则显式禁止 force）。
            print('   ⇒ 这一条按理不该再出现：机器分支已用 --force-with-lease 覆盖自己那条 ref。', file=sys.stderr)
            print('      出现它说明「远端那条 ref 不是我们能覆盖的」——先看它的保护规则。', file=sys.stderr)
        # 失败也要把「本地合好了什么」说出来：没推上去时，人得知道合并结果停在哪、
        # 下一步该干什么，否则日志只剩一句报错（源 CNB #573）。
        print(build_report(p, pushed=False, conflicts=[], reason='push_failed'), file=sys.stderr)
        print(f'\n（合并结果停在临时 worktree 的 `{sha[:8]}`，未推任何远端。）', file=sys.stderr)
        _git(['worktree', 'remove', '--force', wt], cwd)
        return 2
    _git(['worktree', 'remove', '--force', wt], cwd)
    print(build_report(p, pushed=True, conflicts=[]))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='跨仓同步：机器分支 + PR 通道（源 CNB #450）')  # cross-repo-ref-allow
    ap.add_argument('--apply', action='store_true', help='真正执行（默认演练）')
    ap.add_argument('--dry-run', action='store_true', help='演练（默认行为）')
    ap.add_argument('--push', action='store_true', help='把合并结果推成机器分支（需 --apply）')
    # ⚠️ 开 PR 这一步**没有**实现，故不提供开关。
    # 理由：本脚本的职责是「把可合的结果推成一条一次性分支」，而开 PR / auto-merge
    # 属于 GitHub 侧动作（`POST /repos/{repo}/pulls`，`gh` 或 Actions 里做更顺手）。
    # 声明一个不干事的 `--open-pr` 等于谎报能力 —— 本仓 #118 的教训就是「契约要与行为一致」。
    # 要接的话：`claim_detect.py` 的 `github_api()` 是现成通道（插件任务 + Secret imports）。
    ap.add_argument('--base', choices=['cnb', 'github'], default='cnb', help='以哪一侧为基线（默认 cnb）')
    ap.add_argument('--branch', default='dev', help='被同步的分支名（默认 dev）')
    ap.add_argument(
        '--machine-branch',
        default=DEFAULT_MACHINE_BRANCH,
        help=f'机器分支名（默认 {DEFAULT_MACHINE_BRANCH}；**一次性**语义，别建成长期分支）',
    )
    ap.add_argument('--cnb-url', default=None, help='CNB 远程 URL（默认 origin 的 URL）')
    ap.add_argument('--github-url', default=DEFAULT_GITHUB_URL, help='GitHub 远程 URL')
    ap.add_argument('--cwd', default=None, help='git 仓库路径（默认当前目录）')
    args = ap.parse_args(argv)
    if not args.cnb_url:
        code, url, _ = _git(['remote', 'get-url', 'origin'], args.cwd)
        args.cnb_url = url if code == 0 and url else 'https://cnb.cool/duoduobei/fundmate.git'
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
