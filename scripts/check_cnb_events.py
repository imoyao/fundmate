#!/usr/bin/env python3
"""CNB `.cnb.yml` 结构守卫：顶层键必须是分支名，事件不得挂到不存在的分支上。

为什么需要它（源 CNB #152 的复盘，2026-10-11）
----------------------------------------------
双向同步的 PR #150 把 `push:` 与两条 `"crontab: ..."` 写在了**文件顶层**，而不是 `main:`
之下。CNB 的 `.cnb.yml` 顶层**只认分支名**（与 `$`）：读起来像「全局事件」的那三个键，
实际被解释成三个**名字分别为 `push` 与 `crontab: 0 * * * *` 的分支**——它们不存在。

于是流水线连续 7 条全红，而报错是三种看似无关的形态，每一条单独看都会把人指向错的
方向（完整推导见 `scripts/tests/branch_structure.test.js` 的文件头）。核心一条是：

    `GetFileContent: not found` **不是**「文件不存在」——是**事件无定义**。
    CNB 拿 `main` 的定义去兜底，而 `main` 上当时没有 `imports`，于是找不到密钥仓库里的文件。

因此本守卫的判据不是「文件在不在」（那是网络 + Secret 仓库权限问题，静态查不了），
而是**事件有没有挂在真实分支上**——从根上避免「读起来像全局、实际指向不存在的分支」。

判据
----
1. 顶层键 ∈ { 分支名（单值） , `$` , 已知 CNB 元键 }；`push` / `crontab: ...` 一律非法。
2. 白名单**只能是单值键**：`main:` / `dev:` 这类多值键一旦进白名单，任何分支名都被放行，
   本判据等于没有——故守卫自带一个探针，用真实存在的 `sync/mirror:` 验证白名单没被架空。
3. `imports` 引用：指向**仓库**的 `installs` 写法放行（CNB 插件语法的合法形态），
   只有「以目录结尾、看起来不像文件」的 URL 才报错。

不做什么
--------
**不拉网络**：Secret 仓库对 API / token 一律 403，且 CI 里每个 URL 都去 HEAD 一次既慢又脆。
`GetFileContent: not found` 那一类构造不出静态判据，靠判据 1 从根上避免。

用法
----
    python scripts/check_cnb_events.py            # 检查仓库根 .cnb.yml
    python scripts/check_cnb_events.py --file x   # 检查指定文件
退出码 0 = 通过，1 = 发现问题。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# 顶层只允许这些**非分支**的元键。**绝不能**往这里加 `main` / `dev` ——
# 「多值白名单」会让任何分支名都合法，判据随即失效（探针见 self_check()）。
ALLOWED_TOP_KEYS = {'$', 'version'}

# 顶层键长得像「事件」而不是「分支名」时的告警形态。CNB 的事件写在**分支之下**
# （`main: push:` / `main: "crontab: ...":`），写到顶层就成了一个不存在的分支名。
EVENT_LIKE = re.compile(r'^(push|pull_request|web_trigger|tag_push|crontab\s*:|\$.*)$', re.IGNORECASE)

# 分支名的合法字符集（CNB 允许 `/`、`.`、`-`、`_` 与 glob 通配；`crontab: 0 * * * *` 里的
# 空格不在内）。
#
# 字符集**必须**含 `*` `!` `(` `)` `|`：CNB 官方支持用 glob 给一批分支挂事件，
# 本仓 `"**/!(main|dev)"` 段（功能分支 → GitHub，源 CNB #167）就是这种形态。
# 收紧到纯字母数字会让合法配置报红——守卫的第一原则是「在真实数据上跑过」。
# 放宽字符集**不会**架空判据：`EVENT_LIKE` 在 `check_top_keys` 里**先判**，
# 事件名（`push:` / `crontab: ...:`）命中即报错，抢在这条之前；
# 且自检探针里用真实的 glob 反证（见 self_check）。
BRANCH_NAME = re.compile(r'^[A-Za-z0-9._/!()*|?-]+$')


def _load(path: Path) -> dict:
    with path.open(encoding='utf-8') as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def check_top_keys(data: dict) -> list[str]:
    problems: list[str] = []
    for key in data:
        if key in ALLOWED_TOP_KEYS:
            continue
        # ⚠️ EVENT_LIKE 必须**先判**：glob 字符集放宽后（见 BRANCH_NAME），
        # `push:*` 这类也可能落进字符集，若顺序反了就会被当成「分支名」放行 ——
        # 那正是本守卫存在的理由（源 CNB #152）被架空。探针 S4 钉住这个顺序。
        if isinstance(key, str) and EVENT_LIKE.match(key):
            problems.append(
                f'顶层键 {key!r} 是**事件名**，不是分支名。'
                'CNB 的顶层只认分支名（事件要写在分支之下）；'
                f'写成顶层等于让事件指向一个名为 {key!r} 的**不存在分支**——'
                '而平台会用默认分支的定义去兜底，报错形态会南辕北辙（见文件头）。'
            )
            continue
        if isinstance(key, str) and BRANCH_NAME.match(key):
            # 形如 `main` / `sync/mirror`：这是**单值分支键**，正是 CNB 期望的写法。
            # 注意：这里「看起来像分支名」就放行——真正的分支是否存在，静态无从判定；
            # 本守卫拦的是「长得像事件、其实指向不存在的分支」这一类（本事故的根因）。
            continue
        problems.append(
            f'顶层键 {key!r} 既不是分支名也不是已知元键。'
            'CNB 的顶层只认分支名（事件要写在分支之下）；'
            f'写成顶层等于让事件指向一个名为 {key!r} 的**不存在分支**——'
            '而平台会用默认分支的定义去兜底，报错形态会南辕北辙（见文件头）。'
        )
    return problems


def check_imports(data: dict) -> list[str]:
    """`imports` 的取值必须是「文件」而不是「仓库目录」。

    CNB 的 `installs` 语法允许指向仓库（如 `https://cnb.cool/cnb/plugins/xxx`），
    `imports` 则要求被引用的是一个 YAML **文件**。这里只拦「明显是目录」的形态，
    不拉网络、不校验可达性。
    """
    problems: list[str] = []

    def walk(node, trail=''):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == 'imports':
                    for item in v if isinstance(v, list) else [v]:
                        if not isinstance(item, str):
                            continue
                        tail = item.rstrip('/').rsplit('/', 1)[-1]
                        if item.endswith('/') or '.' not in tail:
                            problems.append(
                                f'{trail or "<root>"} 的 imports 指向 {item!r}，看起来是**仓库**而不是文件。'
                                '指向仓库请用 installs 语法；imports 要求被引用的是 YAML 文件。'
                            )
                walk(v, f'{trail}.{k}' if trail else str(k))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f'{trail}[{i}]')

    walk(data)
    return problems


def self_check() -> list[str]:
    """探针：白名单一旦被改成「多值」，唯一值分支键会被误判成非法——此处显式验证。

    这条不是形式主义：#152 的教训就是「守卫通过 ≠ 守卫有效」。若有人把 `main` / `dev`
    加进 ALLOWED_TOP_KEYS，多值白名单会让「事件指向不存在的分支」也放行，
    而守卫依然全绿、看起来好好的。
    """
    probe = {'sync/mirror': {'"crontab: 0 * * * *"': [{'stages': []}]}}
    problems = check_top_keys(probe)
    if problems:
        return [
            '自检探针失败：真实存在的分支键 sync/mirror 被判成非法顶层键，'
            f'说明白名单被改坏了（{problems[0]}）'
        ]
    if 'main' in ALLOWED_TOP_KEYS or 'dev' in ALLOWED_TOP_KEYS:
        return ['自检探针失败：ALLOWED_TOP_KEYS 里出现了具体分支名（多值白名单 = 判据失效）。']

    # 探针 S3b：CNB 官方 glob 分支键（本仓 `"**/!(main|dev)"`，源 CNB #167）必须放行，
    # 否则「事件挂在具体分支下」的正确配置反而报红，守卫会被人绕开而非遵守。
    glob_probe = {'**/!(main|dev)': {'push': [{'stages': []}]}}
    if check_top_keys(glob_probe):
        return [
            f'自检探针失败：合法的 CNB glob 分支键 **/!(main|dev) 被判成非法顶层键'
            f'（{check_top_keys(glob_probe)[0]}）——字符集漏了 glob 通配。'
        ]

    # 探针 S4：字符集放宽后，事件名必须**仍然**被拦（顺序不能反）。
    for ev in ('push', 'web_trigger'):
        if not check_top_keys({ev: {'stages': []}}):
            return [
                f'自检探针失败：字符集放宽后，顶层事件名 {ev!r} 不再被判错 ——'
                'EVENT_LIKE 判据被架空（或判定顺序被调换）。'
            ]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description='检查 CNB .cnb.yml 的事件是否挂在真实分支上')
    ap.add_argument('--file', default=None, help='待检查文件（默认仓库根 .cnb.yml）')
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    path = Path(args.file) if args.file else root / '.cnb.yml'
    if not path.exists():
        print(f'⚠️ 找不到 {path}，跳过')
        return 0

    problems = self_check()
    try:
        data = _load(path)
    except yaml.YAMLError as exc:
        print(f'❌ {path} 不是合法 YAML：{exc}')
        return 1

    problems += check_top_keys(data)
    problems += check_imports(data)

    if problems:
        print(f'❌ {path} 结构检查未通过：')
        for p in problems:
            print(f'  - {p}')
        return 1
    print(f'✅ {path} 顶层事件均挂在分支之下')
    return 0


if __name__ == '__main__':
    sys.exit(main())
