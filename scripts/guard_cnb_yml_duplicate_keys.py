#!/usr/bin/env python3
"""守门：`.cnb.yml` 的同一层不得出现重复键（含 `main:` / `dev:` / `pull_request:` 各一份）。

WHY（源 CNB #458，2026-10-15 实测）
----------------------------------
跨仓收敛合并（`5633d04c`，机器分支通道首轮可合结果）把两侧各自写的「同一处」并进了
`.cnb.yml`：CNB 侧原有 `main: pull_request:`（层 3 反向守卫）与 `dev: ...` 段，
GitHub 侧带来的 `pull_request:` 与 `dev: pull_request:` 落在**同一个 mapping 里** ⇒
同一层出现两个 `pull_request` 键、两个 `dev:` 键。

YAML 规范允许重复键（后值覆盖前值），所以：

- 仓库里 PyYAML `safe_load` **解析通过**（覆盖后只剩一份守卫）；
- 本仓全部 `.cnb.yml` 守卫（`check_cnb_events` / `guard_git_sync_push_scope` /
  `guard_secret_imports`）都走 `yaml.safe_load` ⇒ **全绿**；
- 而 CNB 平台用的是严格 YAML 解析器，**直接拒绝**：

      CI configuration file syntax error
      YAMLException: duplicated mapping key (240:3)

于是 `push` 到 `bridge/github-dev` 的构建 `cnb-l9m-1k4v28ls0` 在 Prepare 阶段即失败，
连 stage 都没进（`pipelineFailCount: 0`、`duration: 0`）。

这正是 #171「失败态被静默」的镜像：**本地判据全绿、平台判据全拒**，
中间的差值就是「严格 vs 宽松解析器」这一行。本守卫把差值补上。

判据
----
1. 用**保留重复键**的加载器解析 `.cnb.yml`（不复用 safe_load：它会把重复键静默合并）；
2. 任一层 mapping 出现同名键 ⇒ 报错，并给出**文件:行号**与已出现的次数；
3. 行号取该键**首次出现**的位置（读者要去删的是第一次那份）。

不做什么
--------
- 不解析 `<<:` 锚点合并的语义（`merge` 键交给 SafeLoader 处理，见 `_DupLoader`）；
- 不校验事件 / 分支挂载位置（那是 `check_cnb_events.py` 与
  `guard_git_sync_push_scope.py` 的职责）；
- 不拉网络。

用法
----
    python scripts/guard_cnb_yml_duplicate_keys.py           # 检查仓库根 .cnb.yml
    python scripts/guard_cnb_yml_duplicate_keys.py --file x  # 检查指定文件
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用（文件不存在 / 读不到 / 解析失败）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


class _DupKeyLoader(yaml.SafeLoader):
    """保留重复键的 SafeLoader：构造 mapping 时记录重复，但不抛异常。

    不覆写 `construct_mapping` 会怎样：PyYAML 默认行为就是「后者覆盖前者」，
    且**不报错**——重复键在本地永远看不见。覆写后才能拿到「第几行、哪个键」。
    """

    def construct_mapping(self, node, deep=False):  # type: ignore[override]
        if not isinstance(node, yaml.MappingNode):
            return super().construct_mapping(node, deep=deep)
        # 先做 flatten：`<<: *anchor` 的键节点 tag 是 `merge`，不展开就直接
        # construct_object 会抛「could not determine a constructor for the tag merge」
        # —— 而 `.cnb.yml` 自己就在用锚点（`<<: *mirror-job`），不能误报成解析失败。
        self.flatten_mapping(node)
        seen: dict[object, int] = {}
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            if isinstance(key, (dict, list)):  # 不可哈希：与重复键判据无关
                continue
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                mark = key_node.start_mark
                self.duplicates.append((key, mark.line + 1, mark.column + 1))
        return super().construct_mapping(node, deep=deep)


# 每个 Loader 实例各自一份收集器（并发 / 多次 load 时不会互相串味）。
_DupKeyLoader.duplicates = []  # type: ignore[attr-defined]


def find_duplicates(text: str) -> list[tuple[object, int, int]]:
    """返回 [(键, 行号, 列号)]，按出现顺序。重复键不抛异常，交由调用方报错。

    ⚠️ 收集器必须挂在**本次调用的 loader 类**上，不能用模块级的
    `_DupKeyLoader.duplicates`：那会被上一次调用残留污染（实测：
    连跑两次合法文本，第二次报出第一次的重复键 —— 判据自己造假阳性）。
    """
    class _Loader(_DupKeyLoader):
        pass

    _Loader.duplicates = []
    yaml.load(text, Loader=_Loader)  # 锚点 / merge 由 SafeLoader 基类处理
    return list(_Loader.duplicates)


def check_file(path: Path) -> list[str]:
    if not path.is_file():
        return [f"__MISSING__:{path}"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"__UNREADABLE__:{path}: {exc}"]
    try:
        dups = find_duplicates(text)
    except yaml.YAMLError as exc:
        return [f"__PARSE_ERROR__:{path}: {exc}"]
    return [
        f"{path}:{line}:{col} 重复键 `{key}`（该层第 {n} 次出现）"
        for key, line, col in [(k, l, c) for k, l, c in dups]
        for n in [2]
    ]


def self_check() -> list[str]:
    """一正一反两个探针：判据写坏了守卫会全绿，故必须自证咬得住。"""
    errors: list[str] = []
    dup_text = "a:\n  b: 1\n  b: 2\n"
    legal_text = "a:\n  b: 1\n  c: 2\n"
    # 锚点 / merge 不能误报：`.cnb.yml` 自己就在用 `<<: *mirror-job`。
    anchor_text = ".base: &base\n  image: python:3.12-slim\nmain:\n  push:\n    - name: x\n      <<: *base\n"
    if not find_duplicates(dup_text):
        errors.append("自检失败：重复键未被检出（守卫对真重复键全绿 = 没干活）。")
    if find_duplicates(legal_text):
        errors.append("自检失败：合法 mapping 被误报为重复键。")
    if find_duplicates(anchor_text):
        errors.append("自检失败：YAML 锚点/merge 被误报为重复键。")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 .cnb.yml 是否存在重复键")
    parser.add_argument("--file", default=".cnb.yml", help="待检查的 YAML 路径")
    args = parser.parse_args(argv)

    problems = check_file(Path(args.file))
    if problems and all(p.startswith("__") for p in problems):
        for p in problems:
            print(f"❌ 输入不可用：{p}（拿不到输入 ≠ 没有问题，#171 的失败态纪律）")
        return 2
    if problems:
        print("❌ .cnb.yml 存在重复键（CNB 平台严格解析会直接拒绝，构建死在 Prepare）：")
        for p in problems:
            print(f"   - {p}")
        print(
            "\n   本地 yaml.safe_load 会静默合并重复键（后者覆盖前者），"
            "所以现有守卫全绿也拦不住它；CNB 侧报错形如：\n"
            "       YAMLException: duplicated mapping key (240:3)\n"
            "   处置：删掉重复的那一份（通常是合并冲突两侧各写了一遍）。"
        )
        return 1
    print("✅ .cnb.yml 无重复键")
    return 0


if __name__ == "__main__":
    sys.exit(main())
