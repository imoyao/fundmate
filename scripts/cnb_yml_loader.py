# -*- coding: utf-8 -*-
"""`.cnb.yml` 的共享严格 YAML 装载器：**拒绝重复 mapping key**（源 CNB #460）。

WHY 单独一个模块
---------------
2026-10-15 跨仓收敛合并把两段同名分支键（两段 `dev:`）并进同一个 `.cnb.yml`，
CNB 平台直接报 `YAMLException: duplicated mapping key`，整条流水线死在 Prepare
（构建 `cnb-46l-1k4v28g8b` 实测：`pipelineFailCount: 0`、`duration: 0`，
连 stage 都没进去）。而三个本地守卫**全部放行**：

| 守卫 | 装载方式 | 对重复 key |
|---|---|---|
| `check_cnb_events.py` | `yaml.safe_load` | 静默放行（后值覆盖前值） |
| `guard_git_sync_push_scope.py` | `yaml.safe_load` | 同上 |
| `guard_secret_imports.py` | `yaml.safe_load` | 同上 |

根因是 **PyYAML 与 CNB 解析器口径不同**：PyYAML 的 `safe_load` 对重复 key 是
「后者覆盖前者」（合法），CNB 是「语法错」（不合法）。于是那一轮里
「本地全绿、平台全挂」，而绿的三个守卫没有一条能指向真正的原因。

`check_cnb_events.py` 已于源 CNB #459 / #460 修掉自己那一份，但**它是逐个守卫打的补丁**
——再新增一个解析 `.cnb.yml` 的守卫，同一个坑会原样再现。故把口径收进本模块：
所有守卫共用一个拒绝重复 key 的 loader，新守卫只要调 `load_cnb_yml()` 就自动带上。

⚠️ `flatten_mapping` 必须保留：本仓 `.cnb.yml` 用了 `<<: *anchor` 合并键
（`.mirror-job` / `claim-sync` 锚点），去掉它会在 merge 键上报
「could not determine a constructor for the tag merge」——那是守卫自己先崩，
不是被测文件有问题。
"""

from __future__ import annotations

from pathlib import Path

import yaml


class NoDuplicateKeyLoader(yaml.SafeLoader):
    """拒绝重复 mapping key 的 SafeLoader（口径与 CNB 平台一致）。"""


def _construct_mapping_no_dup(loader: NoDuplicateKeyLoader, node, deep: bool = False):
    loader.flatten_mapping(node)
    keys = []
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                f'duplicated mapping key {key!r}',
                key_node.start_mark,
            )
        keys.append(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


NoDuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_no_dup
)


def load_cnb_yml(path: Path | str):
    """按 CNB 口径装载 `.cnb.yml`：重复 mapping key 直接抛 `yaml.YAMLError`。

    调用方按既有 `except yaml.YAMLError` 处理即可，但**要把「重复 key」这一形态
    说清楚**（见 `describe_yaml_error`）——裸 YAML 错误信息对「本地全绿、平台全挂」
    这类事故的指路能力很弱。
    """
    p = Path(path)
    return yaml.load(p.read_text(encoding='utf-8'), Loader=NoDuplicateKeyLoader)


def describe_yaml_error(exc: yaml.YAMLError) -> str:
    """把 YAML 错误翻成一句人话。

    只对「重复 key」这一形态特判：它是本仓真实栽过的形态（跨仓收敛合并），
    且 PyYAML 的默认口径与平台相反，不特判就没人知道该往哪看。
    """
    msg = str(exc)
    if 'duplicated mapping key' in msg:
        return (
            f'{msg}\n'
            '   CNB 的解析器对重复 mapping key 直接报语法错，整条流水线死在 Prepare。\n'
            '   常见成因：跨仓收敛合并时两段同名分支键（如两段 `dev:`）被并进同一文件。'
        )
    return msg
