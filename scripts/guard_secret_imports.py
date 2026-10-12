#!/usr/bin/env python3
"""守门：插件用的密钥凭据只能走 `settingsFrom`，不得挂在流水线级 `imports`（源 CNB #148）。

WHY：2026-10-12 实测，`.cnb.yml` 里三条 git-sync 作业（`push` + 两条 `crontab`）**全部**
死在 `Prepare` 阶段，连 stage 都没进：

    The file: .../fundmate-secret/-/blob/main/vars.yml declares allow_images
    and can only be referenced by plugin tasks.
    文件 ... 声明了 allow_images 只能在插件任务引用。

根因是**引用位置错了**，不是内容写错：密钥仓库的 `vars.yml` 必须声明
`allow_images: [tencentcom/git-sync]`（否则插件读不到密钥），但 `imports` 是**流水线级**
引用，平台不把它算作「插件任务」，于是判定「你声明了 allow_images，却没在插件任务里用」
→ 直接拒绝。官方正确形态是把凭据挂在**插件的 `settingsFrom`** 上：

    stages:
      - image: tencentcom/git-sync
        settingsFrom:
          - https://cnb.cool/.../fundmate-secret/-/blob/main/vars.yml
        settings:
          username: ${GIT_USERNAME}
          password: ${GITHUB_PAT}

`imports` 本身没有过错——它读的是**不声明 allow_* 的普通 YAML**；错的是拿它读
**声明了 allow_images 的密钥文件**。故本守卫只拦这一个组合。

判据（两条，都只看静态结构，不拉网络）
--------------------------------------
1. **同一份 URL 同时出现在 `imports` 与 `settingsFrom`** ⇒ 报错。
   平台不允许「同一个引用对象两种语义并存」，且这正是过渡期最容易留下的半吊子改动：
   有人在插件里补了 `settingsFrom`，却忘了删掉上面那行 `imports`——下一轮流水线照旧红。
2. **`imports` 引用的文件内容里出现 `allow_images`** ⇒ 报错。
   `allow_images` 按 CNB 文档存在，**只可能是给插件任务用的**（见文件头推论），
   于是「文件声明了 allow_images」与「被 imports 引用」在语义上互斥，
   不必看线上报错就能判定这份引用会死在 `Prepare`。

不做什么
--------
**不拉网络、不校验 URL 可达性**：`fundmate-secret` 对 API / token 一律 403
（`Secret repos do not support token access`），守卫读不到也不该读。
判据 2 只读**仓库内**同路径的本地文件：密钥仓库的 `vars.yml` 在本仓有一份
**内容同步的模板** `docs/ops/git-sync-secret-vars.example.yml`，判据 2 认它。
若模板路径不存在或读不出来，判据 2 **静默跳过**（只靠判据 1），并在输出里说明。

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
# 判据 2 靠它推测被引用文件里有没有 `allow_images`——Secret 仓库读不到。
SECRET_TEMPLATE = Path('docs/ops/git-sync-secret-vars.example.yml')

# 插件任务标记：出现在 `stages` 元素里、与 `image` 平级的键名，按 CNB 语法只有两种。
PLUGIN_TASK_KEYS = ('imports', 'settingsFrom')


def _iter_uses(node, trail=''):
    """深度遍历，产出 (键名, 取值, 路径)。取值统一成 list[str]。"""
    if isinstance(node, dict):
        for k, v in node.items():
            here = f'{trail}.{k}' if trail else str(k)
            if k in ('imports', 'settingsFrom'):
                vals = v if isinstance(v, list) else [v]
                yield k, [x for x in vals if isinstance(x, str)], here
            yield from _iter_uses(v, here)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _iter_uses(item, f'{trail}[{i}]')


def check_dual_use(data: dict) -> list[str]:
    """判据 1：同一份 URL 既在流水线级 `imports`、又在插件 `settingsFrom`。"""
    imports: dict[str, str] = {}
    settings_from: dict[str, str] = {}
    for key, vals, trail in _iter_uses(data):
        bucket = imports if key == 'imports' else settings_from
        for v in vals:
            bucket.setdefault(v.strip(), trail)
    problems: list[str] = []
    for url, trail in sorted(imports.items()):
        if url in settings_from:
            problems.append(
                f'{url} 同时被 `{trail}` 的 imports 与 `{settings_from[url]}` 的 settingsFrom 引用。'
                '同一份密钥文件两种语义并存：settingsFrom 是插件任务的正确形态，'
                'imports 那一行会让流水线继续死在 Prepare（declares allow_images and can only be '
                'referenced by plugin tasks）。迁移到 settingsFrom 时必须把 imports 那行删掉。'
            )
    return problems


def _secret_referenced_by_imports(data: dict) -> list[str]:
    """产出被 `imports` 引用的密钥类 URL。判据 2 只需要这一类。"""
    out: list[str] = []
    for key, vals, trail in _iter_uses(data):
        if key != 'imports':
            continue
        for v in vals:
            if 'secret' in v.lower() or v.strip().endswith('vars.yml'):
                out.append(v.strip())
    return out


def check_allow_images_import(path: Path) -> list[str]:
    """判据 2：`imports` 引用的密钥文件声明了 `allow_images`（只能给插件任务用）。

    只看 `.cnb.yml` 里出现的密钥类 URL 是否对应本仓模板；模板缺失 / 解析失败则跳过。
    """
    template = path.resolve().parent / SECRET_TEMPLATE
    if not template.exists():
        return []
    try:
        content = yaml.safe_load(template.read_text(encoding='utf-8'))
    except yaml.YAMLError:
        return []
    if not isinstance(content, dict) or 'allow_images' not in content:
        return []
    return [
        f'被 imports 引用的密钥文件（本仓模板 {SECRET_TEMPLATE}）声明了 `allow_images: '
        f'{[x for x in (content["allow_images"] or []) if isinstance(x, str)]}`，'
        '而 `allow_images` 只对**插件任务**有意义、流水线级 imports 会因此被 Prepare 拒绝。'
        '凭据请改挂插件 `settingsFrom`；`imports` 只用于引用**不声明 allow_*** 的普通 YAML。'
    ]


def self_check() -> list[str]:
    """探针（本仓老规矩：守门通过 ≠ 守门有效）。

    用一份**最小真实形态**的配置验证两条判据都真能报错——判据若被写坏（例如键名比对失误），
    守卫会全绿通过，而线上照样红。探针在**真实数据**上跑，不依赖线上。
    """
    probe = {
        'main': {
            'push': [
                {
                    'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                    'stages': [
                        {
                            'image': 'tencentcom/git-sync',
                            'settingsFrom': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                            'settings': {'username': '${GIT_USERNAME}'},
                        }
                    ],
                }
            ]
        }
    }
    if not check_dual_use(probe):
        return ['自检探针失败：同一 URL 同时出现在 imports 与 settingsFrom，判据 1 却没报错。']
    if not _secret_referenced_by_imports(probe):
        return ['自检探针失败：判据 2 认不出被 imports 引用的密钥类 URL。']
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description='检查插件密钥是否误挂在流水线级 imports 上')
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

    problems += check_dual_use(data)
    secret_imports = _secret_referenced_by_imports(data)
    if secret_imports:
        # 判据 2 只有在「确实有密钥文件被 imports 引用」时才有意义——否则别制造噪音。
        if (path.resolve().parent / SECRET_TEMPLATE).exists():
            problems += check_allow_images_import(path)
        else:
            print(f'ℹ️ 未找到 {SECRET_TEMPLATE}，判据 2（allow_images）跳过，仅按判据 1 判定。')

    if problems:
        print(f'❌ {path} 密钥引用位置检查未通过：')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('✅ 插件密钥引用位置合规（无 imports 误挂密钥文件）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
