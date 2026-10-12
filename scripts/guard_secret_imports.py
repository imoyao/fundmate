#!/usr/bin/env python3
"""守门：git-sync 凭据引用必须挂在**插件任务级**，且用 `imports`（源 CNB #148）。

WHY：2026-10-12 两条形态都实测踩过，报错完全不同，把人带向了两个错方向：

  ① 凭据挂在**流水线级** `imports`（`push:` 下一层、`stages:` 之上一行）⇒ 死在 Prepare：
         vars.yml declares allow_images and can only be referenced by plugin tasks.
     因为 vars.yml 必须声明 `allow_images: [tencentcom/git-sync]`（否则插件读不到密钥），
     而流水线级引用**不算「插件任务」**，平台判定「声明了 allow_images 却没在插件任务里用」
     → 直接拒绝，连 stage 都进不去。

  ② 改挂**插件任务级 `settingsFrom`** ⇒ Prepare 过了、进得了 stage，但推不上去：
         fatal: could not read Username for 'https://github.com'
     `settingsFrom` 的语义是「从文件**加载插件参数**」（KEY 直接当插件参数名），
     **不注入环境变量**；而 `settings` 里的 `${GIT_USERNAME}` 是环境变量替换，此时无从解析
     ⇒ 插件拿到空的 username/password ⇒ `setup_https()` 跳过写 `~/.git-credentials`
     ⇒ git 交互式要用户名而失败。

✅ 正确形态：**插件任务级 `imports`**（与 `image` 平级）。依据 CNB 文档
   《文件引用 › image 检查说明》：镜像任务参数「可通过 `settingsFrom` 设置，也可通过
   `imports` 引入后以**环境变量**方式设置，**两种方式均视为插件任务引用文件**」。
   即：插件任务级 `imports` 同样是合规的插件引用（`allow_images` 检查通过），
   且它**注入环境变量**，`settings` 里的 `${GIT_USERNAME}` 才解析得出。
   这也是 git-sync 插件作者给的官方示例形状（其 example.yml 即此法）。

  口诀：**「引用挂在哪」决定合规（必须插件任务内）；
        「用 imports 还是 settingsFrom」决定 `${VAR}` 能不能解析（要解析就用 imports）。**

判据（三条，都只看静态结构，不拉网络）
--------------------------------------
1. **密钥类 URL 出现在流水线级（非插件任务级）引用里** ⇒ 报错（原文 ① 形态）。
   「插件任务级」= 与 `image` 同级的对象内部的 `imports` / `settingsFrom`；
   其余位置（`push:` / `crontab:` 元素对象、`stages:` 之上）都算流水线级。
2. **插件任务用 `settingsFrom` 引用密钥文件，且 `settings` 里对其凭据用了 `${...}`** ⇒ 报错
   （原文 ② 形态）。`settingsFrom` 不注入环境变量，`${VAR}` 解析不出；要用 `${VAR}` 就得 `imports`。
3. **同一份 URL 同时出现在 `imports` 与 `settingsFrom`** ⇒ 报错。
   平台不允许同一引用对象两种语义并存，且这是过渡期最容易留下的半吊子改动。

不做什么
--------
**不拉网络、不校验 URL 可达性**：`fundmate-secret` 对 API / token 一律 403
（`Secret repos do not support token access`），守卫读不到也不该读。
判据 1 只读**仓库内** `.cnb.yml`；判据 2 只看「settingsFrom 引密钥 + settings 用 ${}」这一组合，
不依赖任何外部文件。

用法
----
    python scripts/guard_secret_imports.py            # 检查仓库根 .cnb.yml
    python scripts/guard_secret_imports.py --file x   # 检查指定文件
退出码 0 = 通过，1 = 发现问题。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# 密钥仓库 `vars.yml` 在本仓的**内容同步模板**（见 docs/ops/git-sync-secret-vars.example.yml 文件头：
# 「真正被读取的是密钥仓库里的 vars.yml……故模板落在代码仓里」）。
SECRET_TEMPLATE = Path('docs/ops/git-sync-secret-vars.example.yml')

# 插件任务标记：与 `image` 同级、可用来引用外部文件的键名，按 CNB 语法只有两种。
PLUGIN_TASK_KEYS = ('imports', 'settingsFrom')

# `settings` 里常被用来引用凭据的环境变量名（命中即认为该键需要 `${}` 解析）。
CREDENTIAL_KEYS = ('username', 'password', 'ssh_key')


def _is_secret_url(value: str) -> bool:
    low = value.lower()
    return 'secret' in low or low.strip().endswith('vars.yml')


def _vals(v) -> list[str]:
    items = v if isinstance(v, list) else [v]
    return [x.strip() for x in items if isinstance(x, str)]


def _walk_stage_items(data: dict):
    """产出所有「插件任务对象」（含 image 的 stage 元素）及其所在分支事件名。

    CNB 语法里插件任务 = `stages` 列表里的一个 dict（`image` 与 `imports`/`settingsFrom` 同级）。
    """
    for branch, events in (data or {}).items():
        if branch.startswith('.') or branch == '$':
            continue
        if not isinstance(events, dict):
            continue
        for event, jobs in events.items():
            for job in jobs or []:
                if not isinstance(job, dict):
                    continue
                for stage in job.get('stages') or []:
                    if isinstance(stage, dict) and 'image' in stage:
                        yield branch, event, stage


def check_pipeline_level_secret_refs(data: dict) -> list[str]:
    """判据 1 + 3：密钥类 URL 必须挂在插件任务级，且不得两种语义并存。"""

    problems: list[str] = []
    # 先收集「插件任务级」出现过的 URL，供判据 1 白名单用。
    plugin_level: set[str] = set()
    for _branch, _event, stage in _walk_stage_items(data):
        for key in PLUGIN_TASK_KEYS:
            plugin_level.update(_vals(stage.get(key)))

    problems += _check_pipeline_level(data, plugin_level)
    problems += _check_dual_use(data)
    return problems


def _iter_pipeline_level_refs(data: dict):
    """产出流水线级（非插件任务级）的 imports/settingsFrom 引用。

    做法：从 `push:` / `crontab:` 的事件对象**直接**取这两个键——插件任务级的引用
    在 `stages[*]` 里，不会被这里取到。
    """
    for branch, events in (data or {}).items():
        if branch.startswith('.') or branch == '$':
            continue
        if not isinstance(events, dict):
            continue
        for event, jobs in events.items():
            for i, job in enumerate(jobs or []):
                if not isinstance(job, dict):
                    continue
                for key in PLUGIN_TASK_KEYS:
                    if key in job:
                        for url in _vals(job[key]):
                            yield key, url, f'{branch}.{event}[{i}].{key}'


def _check_pipeline_level(data: dict, plugin_level: set[str]) -> list[str]:
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for key, url, trail in _iter_pipeline_level_refs(data):
        if not _is_secret_url(url):
            continue
        if url in plugin_level:
            # 同一 URL 也在插件任务级出现过：判据 3 会单独报「两种语义并存」，这里别重复报。
            continue
        if (key, url) in seen:
            continue
        seen.add((key, url))
        problems.append(
            f'{url} 被**流水线级** `{trail}` 引用。密钥文件声明了 allow_images，'
            '只有**插件任务级**引用才合规（流水线级会让整条作业死在 Prepare：'
            'declares allow_images and can only be referenced by plugin tasks）。'
            f'请把它移到插件任务内部（与 `image` 同级）并改用 `imports`。'
        )
    return problems


def _check_dual_use(data: dict) -> list[str]:
    imports: dict[str, str] = {}
    settings_from: dict[str, str] = {}
    for branch, event, stage in _walk_stage_items(data):
        for key in PLUGIN_TASK_KEYS:
            for url in _vals(stage.get(key)):
                bucket = imports if key == 'imports' else settings_from
                bucket.setdefault(url, f'{branch}.{event}.stages')
    problems: list[str] = []
    for url, trail in sorted(imports.items()):
        if url in settings_from:
            problems.append(
                f'{url} 同时被插件任务的 imports（{trail}）与 settingsFrom（{settings_from[url]}）引用。'
                '同一份密钥文件两种语义并存：`imports` 注入环境变量、`settingsFrom` 只加载插件参数，'
                '留着两份只会让下一轮继续踩坑；迁移时必须删掉旧的那一种。'
            )
    return problems


def check_settingsfrom_var_substitution(data: dict) -> list[str]:
    """判据 2：插件任务用 `settingsFrom` 引密钥，却在 `settings` 里用 `${VAR}` 引凭据。

    `settingsFrom` 从文件**加载插件参数**，不注入环境变量 ⇒ `${VAR}` 无从解析
    （实现在环境变量里只有 `PLUGIN_*`），插件拿到的 username/password 为空，
    表现为 `fatal: could not read Username for 'https://github.com'`（#148 ② 原文）。
    """
    problems: list[str] = []
    for branch, event, stage in _walk_stage_items(data):
        refs = _vals(stage.get('settingsFrom'))
        if not any(_is_secret_url(u) for u in refs):
            continue
        settings = stage.get('settings') or {}
        if not isinstance(settings, dict):
            continue
        touched = [
            k
            for k in CREDENTIAL_KEYS
            if isinstance(settings.get(k), str) and '${' in settings[k]
        ]
        if touched:
            problems.append(
                f'{branch}.{event} 的插件任务用 `settingsFrom` 引密钥文件，'
                f'却把 {touched} 写成 `${{VAR}}` 环境变量替换。`settingsFrom` 只加载插件参数、'
                '**不注入环境变量**，`${VAR}` 解析不出 ⇒ 插件拿到空凭据 ⇒ git 报 '
                "`could not read Username for 'https://github.com'`。"
                '改用插件任务级 `imports`（它注入环境变量，`${VAR}` 才解析得出）。'
            )
    return problems


def _secret_template_has_allow_images(path: Path) -> bool:
    template = path.resolve().parent / SECRET_TEMPLATE
    if not template.exists():
        return False
    try:
        content = yaml.safe_load(template.read_text(encoding='utf-8'))
    except yaml.YAMLError:
        return False
    return isinstance(content, dict) and bool(content.get('allow_images'))


def self_check() -> list[str]:
    """探针（本仓老规矩：守门通过 ≠ 守门有效）。

    用**最小真实形态**验证三条判据都真会报错——判据若被写坏（例如遍历层级算错），
    守卫会全绿通过，而线上照样红。探针在真实数据形态上跑，不依赖线上。
    """
    errors: list[str] = []

    # 合法形态：插件任务级 imports，不该报错。
    ok = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'image': 'tencentcom/git-sync',
                            'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                            'settings': {'username': '${GIT_USERNAME}'},
                        }
                    ]
                }
            ]
        }
    }
    if check_pipeline_level_secret_refs(ok) or check_settingsfrom_var_substitution(ok):
        errors.append('自检探针失败：合法的「插件任务级 imports」形态却被判为不合规。')

    # 判据 1：流水线级 imports 引密钥。
    bad1 = {
        'main': {
            'push': [
                {
                    'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                    'stages': [{'image': 'tencentcom/git-sync', 'settings': {'username': 'x'}}],
                }
            ]
        }
    }
    if not check_pipeline_level_secret_refs(bad1):
        errors.append('自检探针失败：流水线级 imports 引密钥（#148 ①）没被判据 1 报错。')

    # 判据 2：settingsFrom 引密钥 + settings 用 ${VAR}。
    bad2 = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'image': 'tencentcom/git-sync',
                            'settingsFrom': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                            'settings': {'username': '${GIT_USERNAME}', 'password': '${GITHUB_PAT}'},
                        }
                    ]
                }
            ]
        }
    }
    if not check_settingsfrom_var_substitution(bad2):
        errors.append('自检探针失败：settingsFrom + ${VAR}（#148 ②）没被判据 2 报错。')

    # 判据 3：两种语义并存。
    bad3 = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'image': 'tencentcom/git-sync',
                            'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                            'settingsFrom': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                        }
                    ]
                }
            ]
        }
    }
    if not check_pipeline_level_secret_refs(bad3):
        errors.append('自检探针失败：imports 与 settingsFrom 并存（判据 3）没被报错。')

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description='检查 git-sync 密钥引用是否挂在插件任务级且用 imports')
    ap.add_argument('--file', default=None, help='待检查文件（默认仓库根 .cnb.yml）')
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    path = Path(args.file) if args.file else root / '.cnb.yml'
    if not path.exists():
        print(f'⚠️ 找不到 {path}，跳过')
        return 0

    problems = self_check()
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        print(f'❌ {path} 不是合法 YAML：{exc}')
        return 1
    if not isinstance(data, dict):
        data = {}

    problems += check_pipeline_level_secret_refs(data)
    problems += check_settingsfrom_var_substitution(data)

    if problems:
        print(f'❌ {path} 密钥引用位置检查未通过：')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('✅ git-sync 密钥引用合规（插件任务级 imports）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
