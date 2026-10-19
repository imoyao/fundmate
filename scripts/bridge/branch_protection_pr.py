#!/usr/bin/env python3
"""分支保护拒绝直推时，把合并结果**开成 PR**（源 CNB #586，2026-10-19）。  <!-- cross-repo-ref-allow -->

为什么单独一个脚本
------------------
`machine_branch.py --merge-sync` 的职责是「把两侧合并起来并搬运」，它刻意**零网络依赖**
（判据 `test_script_never_imports_network` 钉着：判定不该依赖网络，否则「网络不通 = 报告绿」
又是一次静默降级）。而开 PR 必然要打 GitHub API —— 两件事的失败语义完全不同：

| 动作 | 失败意味着 |
|---|---|
| git push | 「没搬过去」——git 的事实，退出码可信 |
| REST 开 PR | 「搬运有下落了没」——网络 + 凭据 + 幂等都要单独判 |

所以拆成两个脚本：前者只负责**落下一条 ref**并喊出「接下来该开 PR」，
后者负责**幂等地**把那条 ref 开成 PR。合并叙述的代价是 #567 / #573 都踩过的那个坑。

现场（为什么会有这个兜底）
--------------------------
构建 `cnb-68p-1k58q97a8` / `cnb-sor-1k58prgc9` 的 stage-0 原文：

    ✅ 无冲突，两侧内容可合。
    ❌ 推 `dev` 失败：remote: error: GH006: Protected branch update failed for refs/heads/dev.
       remote: - Required status check "质量门禁汇总" is expected.
     ! [remote rejected]   HEAD -> dev (protected branch hook declined)

**合并是成功的**，被拒的只有推。根因不是分叉没解，而是「直推」这种通行方式在
**有保护规则的分支上恒不可达**：`质量门禁汇总` 只在 PR 上产生
（`ci.yml` 的 `if: github.event_name == 'pull_request'`），直推永远满足不了它。
这正是 #450 当年的结论 —— 解法是**换通行方式**，不是关掉门禁。

幂等键 = head 分支
------------------
同一个 head 已有 open PR 就复用（改推送只会更新那张 PR，不会又开一张）。
刻意不用标题当幂等键：标题会随文案改，改了就等于每轮开一张新卡（#450 的教训）。

用法
----
    # 报告（默认）：只说会做什么
    python scripts/bridge/branch_protection_pr.py --repo imoyao/fundmate \\
        --head fix/cnb-dev-merge --base dev

    # 真正开 PR（CNB 侧凭据来自 Secret 仓库的 GITHUB_PAT）
    python scripts/bridge/branch_protection_pr.py --repo imoyao/fundmate \\
        --head fix/cnb-dev-merge --base dev --apply

退出码：0 = PR 已存在 / 已开出；1 = 开失败（含「没有 token」）；
        2 = 拿不到输入（列 PR 失败）——**结论不可信**，不得读成「不需要开」。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

GITHUB_API = 'https://api.github.com'
UA = 'fundmate-cnb-bridge-pr'

TITLE = 'chore(bridge): 两侧 dev 合并结果 → {base}（直推被分支保护拒绝，改走 PR 门禁）'

BODY = """本 PR 由 CNB 构建自动开出（`scripts/bridge/branch_protection_pr.py`）。

**为什么不直推**：`{base}` 有分支保护，要求 `质量门禁汇总`；而那条检查只在 PR 上产生
（`ci.yml` 的 `if: github.event_name == 'pull_request'`）⇒ 直推**永远**满足不了它。
**门禁一个检查都没少，是被满足，不是被绕过。**

**内容**：CNB `dev` 与 GitHub `dev` 的合并结果（无冲突）。合并本身不产生新内容，
只是让两侧重新收敛；合入后请删掉 `{head}`（一次性分支）。

**被拒原文**：

```
{reason}
```

源提交：`{sha}`。合并完成后 `{head}` 可删。
"""


def api(path: str, *, token: str, method: str = 'GET', payload: dict | None = None) -> object:
    """最小的 GitHub REST 调用。写必须带 token（没 token 当场抛，不等到 401 让人猜）。"""
    if method != 'GET' and not token:
        raise RuntimeError('缺少 GITHUB_PAT / GITHUB_TOKEN（CNB 侧来自 Secret 仓库 imports）')
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(f'{GITHUB_API}{path}', data=data, method=method)
    req.add_header('Authorization', f'Bearer {token}')
    # 显式给 Accept：不给的话错误体会是 HTML，读日志的人只会看到一坨标签。
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    req.add_header('User-Agent', UA)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        # 把响应体并进异常消息：403 的体里写着缺哪个权限，裸 "403 Forbidden" 看不出该改什么
        detail = ''
        try:
            detail = exc.read(400).decode('utf-8', 'replace').strip()
        except Exception:  # noqa: BLE001 - 读错误体失败不该盖掉原始错误
            pass
        raise RuntimeError(f'{exc.code} {exc.reason}：{detail[:400]}') from None
    return json.loads(raw) if raw.strip() else None


def find_open_pr(*, repo: str, owner: str, head: str, base: str, token: str) -> dict | None:
    """同一 head/base 的 open PR（幂等键）。"""
    q = f'/repos/{repo}/pulls?state=open&head={owner}:{head}&base={base}'
    prs = api(q, token=token)
    if isinstance(prs, list) and prs:
        return prs[0]
    return None


def ensure_pr(
    *,
    repo: str,
    head: str,
    base: str,
    reason: str,
    sha: str,
    token: str,
    apply: bool,
    label: str = 'automerge',
) -> dict:
    """确保存在一张 head→base 的 PR；已有就复用。

    返回 `{"ok", "url", "detail"}`。**不猜**：列不出 PR ⇒ 直接抛（调用方退 2），
    不得退化成「没有 PR ⇒ 去开一张」——那会在网络抖动时造出重复卡。
    """
    owner = repo.split('/')[0]
    existing = find_open_pr(repo=repo, owner=owner, head=head, base=base, token=token)
    if existing:
        return {
            'ok': True,
            'url': existing.get('html_url', ''),
            'detail': f'已存在同 head 的 open PR #{existing.get("number")}，未重复开（幂等）',
        }
    if not apply:
        return {'ok': True, 'url': '', 'detail': '（演练：未开 PR。）'}
    if not token:
        return {
            'ok': False,
            'url': '',
            'detail': (
                f'结果已落在 `{head}`，但**没有 token 开 PR**（需 `GITHUB_PAT`）——'
                f'请到 GitHub 手工开 PR 到 `{base}`，或补上凭据后重跑（推送是幂等的）。'
            ),
        }
    pr = api(
        f'/repos/{repo}/pulls',
        token=token,
        method='POST',
        payload={
            'title': TITLE.format(base=base),
            'head': head,
            'base': base,
            'body': BODY.format(
                base=base,
                head=head,
                reason=(reason or '').strip()[:1500] or '（未提供）',
                sha=sha[:12] or '?',
            ),
        },
    )
    number = pr.get('number') if isinstance(pr, dict) else None
    url = pr.get('html_url', '') if isinstance(pr, dict) else ''
    detail = f'PR #{number} 已开'
    if number:
        try:
            api(
                f'/repos/{repo}/issues/{number}/labels',
                token=token,
                method='POST',
                payload={'labels': [label]},
            )
            detail += f'并挂 `{label}`'
        except Exception as exc:  # noqa: BLE001 - 标签失败不改结论，但要可见
            detail += f'；挂 `{label}` 失败：{exc}'
    return {'ok': True, 'url': url, 'detail': detail}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='分支保护拒绝直推时的 PR 兜底（源 CNB #586）')  # cross-repo-ref-allow
    ap.add_argument('--repo', required=True, help='owner/repo，例如 imoyao/fundmate')
    ap.add_argument('--head', required=True, help='合并结果所在的一次性分支')
    ap.add_argument('--base', default='dev', help='目标分支（默认 dev）')
    ap.add_argument('--reason', default='', help='被拒原文（写进 PR 正文，供人判断）')
    ap.add_argument('--sha', default='', help='合并结果 sha')
    ap.add_argument('--label', default='automerge', help='要挂的标签（默认 automerge）')
    ap.add_argument('--apply', action='store_true', help='真正开 PR（默认只报告）')
    args = ap.parse_args(argv)

    token = (os.environ.get('GITHUB_PAT') or os.environ.get('GITHUB_TOKEN') or '').strip()
    try:
        res = ensure_pr(
            repo=args.repo,
            head=args.head,
            base=args.base,
            reason=args.reason,
            sha=args.sha,
            token=token,
            apply=args.apply,
            label=args.label,
        )
    except RuntimeError as exc:
        # 「列不出 PR / 开不动」≠「不需要开」（#171）：退 2 且明说结论不可信。
        print(f'❌ 拿不到输入 / 开 PR 失败：{exc}', file=sys.stderr)
        print('   ⚠️ 本轮结论不可信，不得读成「PR 已就绪」', file=sys.stderr)
        return 2
    print(f'{"✅" if res["ok"] else "❌"} {res["detail"]}')
    if res.get('url'):
        print(f'   {res["url"]}')
    return 0 if res['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
