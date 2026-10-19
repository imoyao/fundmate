#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守门：**回流 / 认领**两条通道必须真的跑得起来（源 CNB #552）。  <!-- cross-repo-ref-allow -->

WHY —— 用户的原话与它指出的三件事
----------------------------------
「分诊侧不用做，回流侧需要做。就是说你关卡或者是说留下评论的时候，一定要判有判据，
不然我会感觉到很困惑。」

前一半是**范围**（分诊那边已经有 `scripts/guard_triage_reachable.py`，本卡不碰）；
后一半是**判据要求**：关卡 / 留评论这类**有副作用**的动作，必须能回答
「凭什么动它」与「拿不到数据时会不会装作动了」。本守卫把回流侧那三个**已经发生过**
的静默形态机械化：

### 判据 1：段落挂错 ⇒ 读的是默认分支的旧配置（2026-10-19 实测）

`.cnb.yml` 里「GitHub issue 增量镜像」这个 job（`.mirror-job` 锚点）是**两处挂载**：
`dev:` 段的 cron、以及 `$:` 段的 `web_trigger`。**`$:` 下没有 `push`** ——
建卡 / **状态回流** / 分诊三段全都在 cron 那一条里。而 `web_trigger` 是一次性的手动触发，
cron 要等下一次 18:00 UTC。

于是一次 `merge` 进 `dev`，**回流（含关卡）与分诊都不会立刻发生**。
若哪天 `dev:` 那段被误挪进 `$:`（或反过来），两条通道更是长在「默认分支的旧配置」上：
`main` 只有发版才前进 ⇒ 修好的代码要等下一次发版才执行，而**每一条构建都报绿**。

判据是集合等价，不拟合写法：**`dev:` 段 cron 里调用的 `scripts/` 脚本集合，
必须等于 `$:` 段 web_trigger 里调用的集合**，且每一侧都非空。

### 判据 2：数据不完整时不得产出结论（#171 的失败态纪律）

`mirror_state_sync.py` 在拿不全 GitHub 数据时**已经**退 1 并打印
「数据不完整，本次结论不可信」；`claim_detect.py` 退 1 且**不摘任何标签**。
这两条判据本身没有判据守着 —— 谁把 `return 1 if not complete else 0` 改成 `return 0`，
行为就退化成「一直绿、一直没干活」，而**没有任何测试会红**。

判据：两个脚本里 `return` 的**第一个**分支必须携带 `complete`（读源码，不跑网络）。

### 判据 3：凭据注入顺序（源 CNB #586 同族：缺失的信号被复制动作盖住）

`mirror_state_sync.py` 用 `GITHUB_TOKEN` 读 GitHub（缺 token ⇒ 匿名 60 次/时/IP，
正是 #171 那轮「第 3 页 403 ⇒ 0 张 ⇒ 报已对齐」的成因）。而 `imports` 引入的
`GITHUB_PAT` **不会自动变成 `GITHUB_TOKEN`** —— 认领同步那段有显式的
`export GITHUB_TOKEN="$GITHUB_PAT"`，别的 stage 只有靠这一条才拿得到认证。

判据（**只对「第一次赋值」**，不要求每个 stage 都写）：`GITHUB_TOKEN` 的第一次赋值必须
来自 `GITHUB_PAT`；若先 `export GITHUB_TOKEN=""`（空串占位）再导出 PAT，后者
**静默不生效**（空串在 `export` 语义里是合法值），脚本仍按匿名跑 ——
那正是「以为注入了、其实没有」。

⚠️ 本判据**当前对「回流 stage 没写这一行」是放行的**，因为 `.cnb.yml` 现状如此
（缺 token 只会退化成 #171 那种「数据不完整 ⇒ 退 1」，不会给出错误结论）。
把它变成硬判据需要先改配置，而改配置要不要动 `mirror_state_sync` 的取数行为，
是**另一件事** —— 卡上另开，不在本守卫里顺手改。

边界（有意不做）
----------------
- **不判 Git 权限 / 不拉网络**：PR 门禁不该依赖外网与 Secret 仓库（那里 403，读不到）；
- **不判「结论判得对不对」**：判据质量在 `scripts/tests/test_mirror_state_sync.py` /
  `test_claim_detect.py`；
- **不判分诊**：那是 `guard_triage_reachable.py` 的范围，本卡明确「分诊侧不用做」。

用法
----
    python scripts/guard_bridge_sync_reachable.py            # 检查仓库根
    python scripts/guard_bridge_sync_reachable.py --file x   # 检查指定 .cnb.yml
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用（**不得**退化成「没问题」）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# 回流 / 认领两条通道的脚本（判据 2 的输入）。
FLOWBACK_SCRIPTS = (
    'scripts/bridge/mirror_state_sync.py',
    'scripts/bridge/claim_detect.py',
)

# 判据 2 的锚：两处**已经**写死的失败态。
#   - `mirror_state_sync.run()`：`return 1 if not complete else 0`
#   - `claim_detect.run()`：`return 1 if (failed or not complete) else 0`
# 两种都认，但**必须命中其中之一**；一个都命中不了 ⇒ 说明失败态被改掉/删掉了（判红）。
_RETURN_INCOMPLETE = re.compile(
    r'return\s+1\s+if\s+(?:\(\s*failed\s+or\s+not\s+complete\s*\)|not\s+complete)\s+else\s+0'
)

# 判据 3 的锚：`GITHUB_TOKEN` 的赋值（含 `export`）。
_TOKEN_ASSIGN = re.compile(r'^\s*(?:export\s+)?GITHUB_TOKEN\s*=\s*(?P<value>.*?)\s*$', re.MULTILINE)

# `.cnb.yml` 里 `python <path>.py` 的调用。
_PY_INVOKE = re.compile(r'\bpython3?\s+(\./)?(?P<path>[\w./-]+\.py)')

_CRON_KEY = re.compile(r'^\s*[\'"]?\s*(?:crontab|cron)\s*:', re.IGNORECASE)

# 两条通道各自的那一对键（`dev:` 的 cron / `$:` 的 web_trigger）。
ACTIVE_BRANCH = 'dev'
WEB_TRIGGER = 'web_trigger'


# ---------------------------------------------------------------------------
# 判据 1：段落等价
# ---------------------------------------------------------------------------


def _collect_scripts(node: object, seen: set[int] | None = None) -> set[str]:
    """把一个 job / 事件体里所有 `script` 调用的 `scripts/` 脚本收出来。

    `<<: *anchor` 在 `safe_load` 之后已是展开后的 dict，故正常遍历即可
    （与 `guard_triage_reachable._collect_scripts` 同口径，但仍防递归引用）。
    """
    seen = seen or set()
    out: set[str] = set()
    if isinstance(node, dict):
        if id(node) in seen:
            return out
        seen.add(id(node))
        for key, value in node.items():
            if key == 'script' and isinstance(value, str):
                out |= {m.group('path') for m in _PY_INVOKE.finditer(value) if m.group('path').startswith('scripts/')}
            else:
                out |= _collect_scripts(value, seen)
    elif isinstance(node, list):
        for item in node:
            out |= _collect_scripts(item, seen)
    return out


def dev_cron_scripts(data: object) -> set[str]:
    """`dev:` 段 cron 里跑到的脚本集合。"""
    if not isinstance(data, dict):
        return set()
    branch = data.get(ACTIVE_BRANCH)
    if not isinstance(branch, dict):
        return set()
    out: set[str] = set()
    for key, jobs in branch.items():
        if _CRON_KEY.match(f'{key}:'):
            out |= _collect_scripts(jobs)
    return out


def web_trigger_scripts(data: object) -> set[str]:
    """`$:` 段 `web_trigger` 里跑到的脚本集合。"""
    if not isinstance(data, dict):
        return set()
    dollar = data.get('$')
    if not isinstance(dollar, dict):
        return set()
    return _collect_scripts(dollar.get(WEB_TRIGGER))


def check_parity(data: object) -> list[str]:
    """判据 1：两条通道的脚本集合必须相等，且都非空。"""
    problems: list[str] = []
    dev = dev_cron_scripts(data)
    web = web_trigger_scripts(data)

    if not dev:
        problems.append(
            f'`{ACTIVE_BRANCH}:` 段的 cron 里没有任何 job 调用 `scripts/` 脚本 —— '
            '回流 / 建卡 / 自检都**不会按时间跑**（源 CNB #564 的形态：写了、测了、从不执行）。'
        )
    if not web:
        problems.append(
            f'`$:` 段的 `{WEB_TRIGGER}` 里没有任何 job 调用 `scripts/` 脚本 —— '
            '手动 / 网页触发那条通道等于空转，构建会绿，但什么都没做。'
        )
    for missing in sorted(web - dev):
        problems.append(
            f'`{WEB_TRIGGER}` 跑的 `{missing}` 不在 `{ACTIVE_BRANCH}:` 的 cron 里 —— '
            '两条触发方式跑的不是同一套命令。cron 才是常态通道（每天一次），'
            '漏在 cron 外的那一个**只在有人手动点的时候才会跑**，而构建一律报绿。'
        )
    for missing in sorted(dev - web):
        problems.append(
            f'`{ACTIVE_BRANCH}:` 的 cron 跑的 `{missing}` 不在 `{WEB_TRIGGER}` 里 —— '
            '手动通道跑的与定时通道不是同一套命令。两边改一处漏一处，'
            '就会出现「定时跑的是新的、手动跑的是旧的」（或反之），而两边都报绿。'
        )
    return problems


# ---------------------------------------------------------------------------
# 判据 2：数据不完整时不得给出结论
# ---------------------------------------------------------------------------


def check_failure_state(text: str, name: str = '?') -> list[str]:
    """判据 2：`return` 的第一个分支必须携带 `complete`（读源码，不跑网络）。"""
    if not _RETURN_INCOMPLETE.search(text):
        return [
            f'`{name}` 里找不到「数据不完整 ⇒ 非 0 退出」那一行'
            '（`return 1 if not complete else 0` / `return 1 if (failed or not complete) else 0`）—— '
            '「数据不完整 ⇒ 非 0 退出」是回流侧唯一能被人看见的失败态（源 CNB #171）。'
            '改掉它，拿不全数据时就会退化成「一直绿、一直没干活」，'
            '而**没有任何测试会红**。若此判据已过期（写法变了），请同步更新本守卫，'
            '**不要**把它改成「找不到就跳过」——那等于守卫自己先退化成假绿。'
        ]
    return []


# ---------------------------------------------------------------------------
# 判据 3：凭据注入顺序
# ---------------------------------------------------------------------------


def check_token_wiring(script: str, name: str = '?') -> list[str]:
    """判据 3：`GITHUB_TOKEN` 的第一次赋值必须来自 `GITHUB_PAT`。"""
    hits = list(_TOKEN_ASSIGN.finditer(script))
    if not hits:
        return []  # 不读 GitHub 的 stage 不该被本判据管
    first = hits[0].group('value')
    if 'GITHUB_PAT' in first:
        return []
    return [
        f'`{name}` 里 `GITHUB_TOKEN` 的第一次赋值是 `{first}`，没带 `GITHUB_PAT`。'
        '`imports` 引入的 `GITHUB_PAT` **不会自动变成 `GITHUB_TOKEN`**，'
        '脚本于是按匿名读 GitHub（60 次/时/IP）—— 那正是源 CNB #171 那轮'  # cross-repo-ref-allow
        '「第 3 页 403 ⇒ 0 张 ⇒ 报已对齐」的成因。'
        '正确写法：`export GITHUB_TOKEN="$GITHUB_PAT"`，且**不要**先写一个空串占位'
        '（空串在 `export` 语义里是合法值，后面的赋值会被挡住、静默不生效）。'
    ]


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def check_data(data: object, scripts: dict[str, str] | None = None) -> list[str]:
    """把三条判据合成一次判定。`scripts` = {仓库相对路径: 源码}，缺省读仓库。"""
    problems = check_parity(data)

    texts = scripts
    if texts is None:
        texts = {}
        for rel in FLOWBACK_SCRIPTS:
            p = REPO_ROOT / rel
            texts[rel] = p.read_text(encoding='utf-8') if p.is_file() else ''

    for rel in FLOWBACK_SCRIPTS:
        src = texts.get(rel, '')
        if not src:
            problems.append(f'输入不可信：读不到 `{rel}` —— 它的失败态本轮判不出来。')
            continue
        problems.extend(check_failure_state(src, rel))

    # 判据 3 只扫 `.cnb.yml` 里调用回流脚本的 stage
    if isinstance(data, dict):
        for branch, events in data.items():
            if not isinstance(events, dict):
                continue
            for event, jobs in events.items():
                if not isinstance(jobs, list):
                    continue
                for job in jobs:
                    if not isinstance(job, dict):
                        continue
                    for stage in job.get('stages') or []:
                        if not isinstance(stage, dict):
                            continue
                        body = stage.get('script') or stage.get('commands') or ''
                        if not isinstance(body, str):
                            continue
                        if not any(rel in body for rel in FLOWBACK_SCRIPTS):
                            continue
                        where = f'`{branch}` / `{event}` / job「{job.get("name")}」/ stage「{stage.get("name")}」'
                        problems.extend(check_token_wiring(body, where))
    return _dedup(problems)


def _dedup(items: list[str]) -> list[str]:
    out: list[str] = []
    for it in items:
        if it not in out:
            out.append(it)
    return out


# ---------------------------------------------------------------------------
# 自检探针（判据写坏了会全绿——本仓老规矩）
# ---------------------------------------------------------------------------

_SCRIPT = 'python scripts/bridge/mirror_state_sync.py --apply'

_PROBE_GOOD = {
    'dev': {'crontab: 0 18 * * *': [{'name': 'j', 'stages': [{'name': 's', 'script': 'export GITHUB_TOKEN="$GITHUB_PAT"\n' + _SCRIPT}]}]},
    '$': {'web_trigger': [{'name': 'm', 'stages': [{'name': 's', 'script': 'export GITHUB_TOKEN="$GITHUB_PAT"\n' + _SCRIPT}]}]},
}
_SRC_OK = {
    'scripts/bridge/mirror_state_sync.py': 'def f():\n    return 1 if not complete else 0\n',
    'scripts/bridge/claim_detect.py': 'def f():\n    return 1 if (failed or not complete) else 0\n',
}


def self_check() -> list[str]:
    errors: list[str] = []

    if check_data(_PROBE_GOOD, _SRC_OK):
        errors.append('自检失败：合法配置被误报（判据过宽）。')

    # 判据 1：web_trigger 少一个脚本
    missing_web = {'dev': _PROBE_GOOD['dev'], '$': {'web_trigger': [{'name': 'm', 'stages': [{'name': 's', 'script': 'echo hi'}]}]}}
    if not any('web_trigger' in p for p in check_data(missing_web, _SRC_OK)):
        errors.append('自检失败：web_trigger 空转没被拦。')

    no_dev_cron = {'dev': {'push': []}, '$': _PROBE_GOOD['$']}
    if not any('cron' in p for p in check_data(no_dev_cron, _SRC_OK)):
        errors.append('自检失败：dev 段没有 cron 没被拦。')

    # 判据 2：失败态被删
    broken_src = {'scripts/bridge/mirror_state_sync.py': 'def f():\n    return 0\n',
                  'scripts/bridge/claim_detect.py': _SRC_OK['scripts/bridge/claim_detect.py']}
    if not any('非 0 退出' in p for p in check_data(_PROBE_GOOD, broken_src)):
        errors.append('自检失败：失败态被删掉没被拦（正是 #171 的假绿形态）。')

    # 判据 3：空串占位后再说 PAT
    shadow = {
        'dev': {'crontab: 0 18 * * *': [{'name': 'j', 'stages': [{'name': 's', 'script': 'export GITHUB_TOKEN=""\nexport GITHUB_TOKEN="$GITHUB_PAT"\n' + _SCRIPT}]}]},
        '$': _PROBE_GOOD['$'],
    }
    if not any('GITHUB_PAT' in p for p in check_data(shadow, _SRC_OK)):
        errors.append('自检失败：空串占位盖住 PAT 没被拦。')

    # 读不到脚本 ⇒ 结论不可信，不得当成通过
    if not any('不可信' in p for p in check_data(_PROBE_GOOD, {})):
        errors.append('自检失败：读不到回流脚本却放行（#171 的失败态纪律）。')
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='回流 / 认领通道可达性守卫（源 CNB #552）')  # cross-repo-ref-allow
    ap.add_argument('--file', default=None, help='要检查的 .cnb.yml（默认仓库根）')
    args = ap.parse_args(argv)

    errors = self_check()
    if errors:
        for e in errors:
            print(f'❌ {e}', file=sys.stderr)
        print('守卫自身自检失败 —— 本轮结论不可信（判据写坏了会全绿）', file=sys.stderr)
        return 2

    path = Path(args.file) if args.file else REPO_ROOT / '.cnb.yml'
    if not path.is_file():
        print(f'❌ 输入不可用：读不到 {path} —— 本轮结论不可信', file=sys.stderr)
        return 2
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        print(f'❌ 输入不可用：{path} 读不出来（{exc}）—— 本轮结论不可信', file=sys.stderr)
        return 2
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        print(f'❌ 输入不可用：{path} 解析失败（{exc}）—— 本轮结论不可信', file=sys.stderr)
        return 2

    problems = check_data(data, None)
    if problems:
        for p in problems:
            print(f'❌ {p}', file=sys.stderr)
        return 1
    print('✅ 回流 / 认领两条通道可及：cron 与 web_trigger 跑同一套脚本，')
    print('   失败态（数据不完整 ⇒ 非 0）与凭据注入顺序都有判据守着。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
