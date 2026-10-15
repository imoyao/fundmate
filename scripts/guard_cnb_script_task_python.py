#!/usr/bin/env python3
"""守门：`.cnb.yml` 里**跑 python 的脚本任务**必须自带 `docker.image`。

WHY（源 CNB #461，2026-10-15 实测）
----------------------------------
「跨仓同步（机器分支 + PR 通道）」这个 job 上线（`ad8ff42e`）时只写了
`imports` / `env` / `script`，**没写 `image`**。脚本任务不声明 image 时 runner
落在**默认镜像**上，而默认镜像里没有 python：

    构建 cnb-nii-1k4ua02j8 → stage-0 原文
      sh: line 10: python: command not found
      Finished, code: 127

⇒ 机器分支通道**一次都没跑成**。红了三类构建（push / cron / 机器分支自己），
报错却指向「脚本第 10 行」而不是「容器里没有解释器」——同一个仓库里其它
脚本任务（`.mirror-job` / `&claim-job`）都规规矩矩写了
`docker.image: python:3.12-slim`，只漏了这一处，而**没有任何判据在管这件事**。

它与 #171 同族：不是「缺功能」，是缺一条**能问出「这个 job 跑得起来吗」**的判据。
差别在于它问的不是数据完整性，是**执行环境**。

判据
----
1. stage 带 `script` / `commands` 且正文调用 `python ` / `python3 ` ⇒ 脚本任务；
2. 该脚本任务（job 级 `docker.image` 或 stage 自身 `image`）必须声明一个
   **含 python 解释器**的镜像；
3. 读不到输入（文件不存在 / 解析失败）⇒ 退 2 并声明「结论不可信」，
   **不得**退化成「没问题」（#171 的失败态纪律）。

边界：**重复键会遮蔽整个 job —— 那时本守卫看不见它**（2026-10-15 补，源 CNB #463）
--------------------------------------------------------------------
`yaml.safe_load` 对重复键「后者覆盖前者」且**不报错**。拿它跑一份 `dev:` 重复出现的配置，
被覆盖掉的那个 `dev:` 段里的 job（含机器分支 job）在 `safe_load` 后**根本不存在**，
于是本守卫对它**一无所知、报绿** —— 实测：

    # 拿 origin/dev 那份坏配置（顶层两个 `dev:`）喂本守卫
    ✅ .cnb.yml 的 python 脚本任务均自带镜像     ← 假的绿灯

这不是本守卫判据写错了，是**它的输入已经被别的错吃掉了**。处置：`check_text` 在解析前
先用**保留重复键**的加载器探一遍，命中即把「job 可能被遮蔽」如实报出来（退 1），
而不是让调用方读到一个看起来正常的 ✅。职责划分不变：**「键重复」本身仍归
`guard_cnb_yml_duplicate_keys.py` 判**，本守卫只拒绝在「输入不可信」时给出绿结论。

边界（有意为之）
----------------
- **只认字面量镜像名**：`image: python*` / `python:*` / `*python:3*` 这类含
  `python` 的即视为带解释器；`${VAR}` 求值不了 ⇒ 放行（判据不猜运行时值，
  与 `guard_git_sync_push_scope.py` 判据 5 同口径）。
- **不判 shell 写法**：`python3` 也放行（本仓统一用 `python`，但守卫不必更严）。
- 不含 python 调用的脚本任务（如纯 `sh` / `echo`）不在判据内 —— 默认镜像跑 shell 没问题。
- 不拉网络、不校验镜像是否可拉取。

用法
----
    python scripts/guard_cnb_script_task_python.py            # 检查仓库根 .cnb.yml
    python scripts/guard_cnb_script_task_python.py --file x   # 检查指定文件
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# job 级 docker.image 或 stage 级 image：含 python 即视为「自带解释器」。
# 形如 python:3.12-slim / python / python:3.11-alpine；`${VAR}` 无从静态求值 ⇒ 放行。
_PY_IMAGE = re.compile(r'python')
_VAR = re.compile(r'\$\{')

# 脚本正文里调用解释器的两种写法（行首或 `&&` / `;` 后都算）。
_PY_CALL = re.compile(r'(^|[;&|\s])(python3?|python)\s+\S')

_PROBE_GOOD = (
    'dev:\n'
    '  push:\n'
    '    - name: ok\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/x.py\n'
)

_PROBE_BAD = (
    'dev:\n'
    '  push:\n'
    '    - name: bad\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/x.py\n'
)


class _DupKeyLoader(yaml.SafeLoader):
    """保留重复键的 SafeLoader：构造 mapping 时把重复的键记下来，但不抛异常。

    与 `guard_cnb_yml_duplicate_keys.py` 的加载器同源（各自持有，避免守卫之间
    互相 import —— 它们要能**单独**跑，那才是守卫该有的样子）。
    """

    def __init__(self, stream):
        super().__init__(stream)
        self.duplicates: list[tuple[str, int]] = []

    def construct_mapping(self, node, deep=False):
        keys: list[str] = []
        for key_node, _ in node.value:
            try:
                keys.append(str(self.construct_object(key_node, deep=True)))
            except yaml.YAMLError:
                continue
        for key in set(keys):
            if keys.count(key) > 1:
                self.duplicates.append((key, node.start_mark.line + 1))
        return super().construct_mapping(node, deep=deep)


def _find_duplicate_keys(text: str) -> list[tuple[str, int]]:
    """返回 [(键名, 行号)]；同一键出现多次即计入（行号取该 mapping 起点）。

    解析不了（YAML 语法错）时返回空 —— 那不是本守卫的判据，交给
    `guard_cnb_yml_duplicate_keys.py` / 平台自身报。
    """
    loader = _DupKeyLoader(text)
    try:
        loader.get_single_data()
    except yaml.YAMLError:
        return []
    finally:
        try:
            loader.dispose()
        except Exception:  # noqa: BLE001 - dispose 失败不该影响判据
            pass
    return loader.duplicates


# 遮蔽探针：顶层 `dev:` 出现两次。第一个 `dev:` 里的坏 job（跑 python 无 image）
# 会被第二个 `dev:` 整个覆盖 ⇒ `safe_load` 后它不存在 ⇒ 老版本守卫会对这份输入报绿。
# 真实来源：`origin/dev` 的 `.cnb.yml`（跨仓收敛合并 `5633d04c` 留下的重复键）。
_PROBE_SHADOWED = (
    'dev:\n'
    '  push:\n'
    '    - name: shadowed-bad\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/x.py\n'
    'dev:\n'
    '  push:\n'
    '    - name: winner\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/y.py\n'
)


def _has_python_image(job: dict, stage: dict) -> bool | None:
    """返回 True=有 python 镜像、False=有镜像但不含 python、None=没声明镜像。"""
    for img in (
        (job.get('docker') or {}).get('image'),
        job.get('image'),
        stage.get('image'),
    ):
        if not img:
            continue
        if _VAR.search(str(img)):
            return True  # 运行期变量：不猜，放行
        return bool(_PY_IMAGE.search(str(img)))
    return None


def _calls_python(script: str) -> bool:
    return bool(_PY_CALL.search(str(script)))


def check_text(text: str) -> list[str]:
    problems: list[str] = []
    # 先探重复键：被覆盖掉的 job 在 safe_load 后不存在，本守卫会对它一无所知、
    # 报出一个**看起来正常**的绿（实测 `origin/dev` 那份配置）。宁可说「输入不可信」，
    # 也不给一个方向可能反了的结论（#171 / #463）。
    dups = _find_duplicate_keys(text)
    if dups:
        seen = ', '.join(f'`{k}`（第 {ln} 行起）' for k, ln in dups)
        return [
            f'输入不可信：`.cnb.yml` 存在重复键 {seen}。'
            '`yaml.safe_load` 会用后者覆盖前者，被覆盖段的 job **不会进入本次检查**'
            '—— 本守卫在遮蔽状态下给出的「均自带镜像」是假绿灯。'
            '先跑 `python scripts/guard_cnb_yml_duplicate_keys.py` 修掉重复键再复检。'
        ]
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return []
    for branch, events in data.items():
        if branch.startswith('.') or not isinstance(events, dict):
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
                    script = stage.get('script') or stage.get('commands')
                    if not script or not _calls_python(script):
                        continue
                    img = _has_python_image(job, stage)
                    if img is None:
                        problems.append(
                            f'`{branch}` / `{event}` / job「{job.get("name")}」'
                            f'/ stage「{stage.get("name")}」跑 python 却**没有声明 image**'
                            '——默认镜像里没有解释器，会以 `python: command not found` 收场'
                            '（code 127）。修法：给 job 加 `docker.image: python:3.12-slim`。'
                        )
                    elif img is False:
                        problems.append(
                            f'`{branch}` / `{event}` / job「{job.get("name")}」'
                            f'/ stage「{stage.get("name")}」声明的镜像不含 python。'
                        )
    return problems


def check_file(path: Path) -> tuple[list[str], bool]:
    """返回 (问题列表, 输入是否可用)。"""
    if not path.is_file():
        return [f'__MISSING__:{path}'], False
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        return [f'__UNREADABLE__:{path}: {exc}'], False
    try:
        return check_text(text), True
    except yaml.YAMLError as exc:
        return [f'__PARSE_ERROR__:{path}: {exc}'], False


def self_check() -> list[str]:
    """一正一反两个探针：判据没接上时守卫会全绿，故必须自证咬得住。"""
    errors: list[str] = []
    if not check_text(_PROBE_BAD):
        errors.append('自检失败：跑 python 却不声明 image 的样本没被报出来（判据恒绿）。')
    if check_text(_PROBE_GOOD):
        errors.append('自检失败：合法样本（带 python 镜像）反被误报。')
    # 遮蔽探针（#463）：重复键会把坏 job 整个吃掉，若守卫此时仍报 ✅，
    # 它给出的就是**方向可能反了**的结论 —— 必须转红。
    if not check_text(_PROBE_SHADOWED):
        errors.append(
            '自检失败：重复键遮蔽样本没被报出来（守卫在看不见的输入上给了假绿灯）。'
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='检查 .cnb.yml 的 python 脚本任务是否自带镜像')
    parser.add_argument('--file', default='.cnb.yml', help='待检查的 YAML 路径')
    args = parser.parse_args(argv)

    problems, usable = check_file(Path(args.file))
    if not usable:
        for p in problems:
            print(f'❌ 输入不可用：{p}（拿不到输入 ≠ 没有问题，#171 的失败态纪律）')
        return 2
    if problems:
        print('❌ .cnb.yml 有跑 python 却没自带镜像的脚本任务：')
        for p in problems:
            print(f'   - {p}')
        return 1
    print('✅ .cnb.yml 的 python 脚本任务均自带镜像')
    return 0


if __name__ == '__main__':
    sys.exit(main())
