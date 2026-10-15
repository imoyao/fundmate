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
4. **同一层不得有重复的 mapping key**（源 CNB #457，2026-10-15）。CNB 的 YAML 解析器
   对重复 key **直接报语法错**（`YAMLException: duplicated mapping key`），整条流水线
   死在 Prepare，连 stage 都进不去。而 PyYAML 的 `safe_load` **默认放行**重复 key
   （后值覆盖前值），所以此前三条判据对它全部「检查通过」——守卫自己看不见这一类。
   本仓已真实栽过一次：跨仓收敛合并把两段 `dev:` 并进同一个文件，平台上多条流水线
   同时红，本地却是绿的。

   口径**不在这里自备**：共用 `scripts/cnb_yml_loader.py` 的 `NoDuplicateKeyLoader`
   （源 CNB #460 / #459 合流时收敛）。本守卫曾自带一份等价实现，两份代码干同一件事
   —— 判据散成多份就会各自漂移，故只留共享的那一份。

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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cnb_yml_loader import NoDuplicateKeyLoader, describe_yaml_error  # noqa: E402

# 顶层只允许这些**非分支**的元键。**绝不能**往这里加 `main` / `dev` ——
# 「多值白名单」会让任何分支名都合法，判据随即失效（探针见 self_check()）。
ALLOWED_TOP_KEYS = {'$', 'version'}


# 顶层键长得像「事件」而不是「分支名」时的告警形态。CNB 的事件写在**分支之下**
# （`main: push:` / `main: "crontab: ...":`），写到顶层就成了一个不存在的分支名。
#
# ⚠️ **点分事件名必须收进来**（源 CNB #459，2026-10-15）：CNB 的事件名有点分子形态
# （`pull_request.mergeable` / `pull_request.merged` / `pull_request.update` ……），
# 而**点恰好在 `BRANCH_NAME` 的字符集里** ⇒ 漏掉它们就等于「顶层的
# `pull_request.mergeable:` 被当成合法分支名放行」，正是本守卫存在的理由（#152）被架空。
# 收成 `pull_request(\.\w+)*` 而不是逐个枚举：CNB 的点分事件是开放集合，
# 枚举会随平台加事件而漏 —— 判据要做到「长得像事件就报」，不做到「我认识这个事件才报」。
EVENT_LIKE = re.compile(
    r'^(push|pull_request(\.\w+)*|web_trigger|tag_push|crontab\s*:|\$.*)$', re.IGNORECASE
)

# 分支名的合法字符集（CNB 允许 `/`、`.`、`-`、`_` 与 glob 通配；`crontab: 0 * * * *` 里的
# 空格不在内）。
#
# 字符集**必须**含 `*` `!` `(` `)` `|`：CNB 官方支持用 glob 给一批分支挂事件，
# 本仓 `"**/!(main|dev)"` 段（功能分支 → GitHub，源 CNB #167）。  cross-repo-ref-allow
# 收紧到纯字母数字会让合法配置报红——守卫的第一原则是「在真实数据上跑过」。
# 放宽字符集**不会**架空判据：`EVENT_LIKE` 在 `check_top_keys` 里**先判**，
# 事件名（`push:` / `crontab: ...:`）命中即报错，抢在这条之前；
# 且自检探针里用真实的 glob 反证（见 self_check）。
BRANCH_NAME = re.compile(r'^[A-Za-z0-9._/!()*|?-]+$')


def _load(path: Path) -> dict:
    # 严格 loader：重复 key 必须在解析阶段就炸，而不是被后者静默覆盖（判据 4）。
    with path.open(encoding='utf-8') as fh:
        data = yaml.load(fh, Loader=NoDuplicateKeyLoader)
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

    # 探针 S5（源 CNB #457）：重复 key 必须**真的**被拒绝。
    # 否则「换严格 loader」会悄悄退化成空转——loader 换了、判据没接上，而真实文件
    # 一旦有重复 key，平台照样死在 Prepare。用最小样本验，不依赖真实文件。
    dup_probe = 'main:\n  push: []\ndev:\n  push: []\ndev:\n  pull_request: []\n'
    try:
        yaml.load(dup_probe, Loader=NoDuplicateKeyLoader)
        return [
            '自检探针失败：重复的顶层分支键（两段 `dev:`）没被拒绝 —— '
            '严格 loader 的重复 key 判据没接上（源 CNB #457）。'
        ]
    except yaml.YAMLError:
        pass  # 期望行为：抛错

    # 探针 S4：字符集放宽后，事件名必须**仍然**被拦（顺序不能反）。
    # 覆盖 GitHub 侧探针确认过的全部五类坏顶层键（2026-10-14 跨仓收敛时合并，
    # 少一类就等于「EVENT_LIKE 对那一类失效」时无人发现）。
    for ev in ('push', 'pull_request', 'web_trigger', 'tag_push', '"crontab: 0 * * * *"'):
        if not check_top_keys({ev: {'stages': []}}):
            return [
                f'自检探针失败：字符集放宽后，顶层事件名 {ev!r} 不再被判错 ——'
                'EVENT_LIKE 判据被架空（或判定顺序被调换）。'
            ]

    # 探针 S6（源 CNB #459，2026-10-15）：**点分事件名**必须被拦。
    # 这一条单列，是因为它漏得最隐蔽：`.cnb.yml` 里合法的挂法就是
    # `main: pull_request.mergeable:`，而「点」又在 `BRANCH_NAME` 的字符集里 ⇒
    # 一旦 EVENT_LIKE 不收点分形态，顶层的 `pull_request.mergeable:` 会被当成
    # **合法分支名**放行 —— 判据对着一类长得跟今天一模一样的坏配置空转。
    # 不逐个枚举具体事件（`mergeable` / `merged` / `update` …）：CNB 的点分事件是
    # 开放集合，枚举会随平台加事件而漏。
    for ev in ('pull_request.mergeable', 'pull_request.merged', 'pull_request.update'):
        if not check_top_keys({ev: {'stages': []}}):
            return [
                f'自检探针失败：点分事件名 {ev!r} 不再被判错 ——'
                'EVENT_LIKE 漏了点分形态，而「点」在 BRANCH_NAME 字符集里 ⇒'
                '这类顶层坏配置会被当成合法分支名放行（源 CNB #459）。'
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
        # 文案统一由共享 loader 给（源 CNB #460）：重复 key 的成因与后果只说一份，
        # 免得三个守卫各写各的、细节互相漂移。
        print(f'❌ {path} 不是合法 YAML：{describe_yaml_error(exc)}')
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
