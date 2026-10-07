#!/usr/bin/env python3
"""守门：编排器注册的 job 必须被「每日调度」或「明确不调度」覆盖（#1934）。

WHY：orchestrator._register_jobs 与 daily_scheduler._JOB_TEMPLATES 是两张互不引用的清单，
忘了同步不会报错。实证后果（#1907 批 2 / 批 3 复核）：index_valuation / convertible_bond /
market_asset_daily / dividend_split 全都已注册且已进全量执行计划，但都不在每日调度里，
真库从未执行过——卡片看起来做了，数据却永不自动更新（自选页指数估值列、可转债条款列、
探市快照的「每日自动更新」全都不会发生）。

断言：已注册 job ⊆ _JOB_TEMPLATES ∪ _NOT_SCHEDULED。往 _NOT_SCHEDULED 加条目不是绕过检查：
守门会校验每条理由非空，且会在编排器已删除该 job 时报「登记变墓地」。

用 ast 静态解析而非 import：import orchestrator 会连带加载 akshare / py_mini_racer，
CI 里跑不动。代价是「动态注册」会漏抓，故对注册形态做断言（见 _collect_registered_jobs）。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / 'backend'
ORCHESTRATOR_PY = BACKEND_DIR / 'app' / 'services' / 'sync' / 'orchestrator.py'
SCHEDULER_PY = BACKEND_DIR / 'app' / 'services' / 'daily_scheduler.py'
def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def _collect_registered_jobs(tree: ast.Module) -> set[str]:
    """抽出 self.jobs['x'] = ... 形式的注册 key。

    只认字面量下标：若有人改成 self.jobs[name] = ...（变量下标），这里会漏抓，
    于是该 job 逃过覆盖检查。因此 main() 里另有「注册语句数量」断言兜底。
    """
    jobs: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Subscript):
            continue
        base = tgt.value
        if not (isinstance(base, ast.Attribute) and base.attr == 'jobs'):
            continue
        sl = tgt.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            jobs.add(sl.value)
    return jobs


def _count_jobs_assignments(tree: ast.Module) -> int:
    """统计 self.jobs[...] = ... 语句总数（不要求 key 是字面量），用于检测形态变化。"""
    n = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        tgt = node.targets[0]
        if isinstance(tgt, ast.Subscript):
            base = tgt.value
            if isinstance(base, ast.Attribute) and base.attr == 'jobs':
                n += 1
    return n


def _module_assignment_value(tree: ast.Module, var_name: str):
    """取模块级变量 var_name 的赋值右值，同时支持 Assign 与带注解的 AnnAssign。

    `_JOB_TEMPLATES: Tuple[...] = (...)` 是**带类型注解**的赋值（AnnAssign），
    而 `_NOT_SCHEDULED: Dict[...] = {...}` 也是——只认 Assign 会两者都漏，
    第一版就是这么把守门写成了「恒定失败」。
    """
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == var_name:
                return node.value
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == var_name for t in node.targets
        ):
            return node.value
    return None


def _tuple_literal_strings(tree: ast.Module, var_name: str) -> list[str]:
    """抽模块级 VAR = ( ('job', ENV, CRON, DEFAULT, KIND, DESC), ... ) 里的 job 名。

    注意元组的元素是**元组**（每项 6 个字段，第 0 位是 job 名），不是裸字符串——
    早期版本按「直接字符串字面量」抓，恒为空，守门会误报「形态变了」，
    这正是本脚本第一版踩的坑。
    """
    value = _module_assignment_value(tree, var_name)
    if value is None or not isinstance(value, ast.Tuple):
        return []
    names: list[str] = []
    for elt in value.elts:
        if not isinstance(elt, ast.Tuple) or not elt.elts:
            return []
        head = elt.elts[0]
        if not (isinstance(head, ast.Constant) and isinstance(head.value, str)):
            return []
        names.append(head.value)
    return names


def _dict_literal_pairs(tree: ast.Module, var_name: str) -> dict[str, str]:
    """抽模块级 VAR: Dict[str, tuple[str, str]] = {'job': ('理由', '频率')}。

    值是二元组（不进每日调度的理由, 建议频率）——早期版本按「字符串值」抓，
    会把每个理由都读成空串、守门全量误报，故这里显式支持 tuple 并取第 0 元素。
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if not (isinstance(node.target, ast.Name) and node.target.id == var_name):
            continue
        if not isinstance(node.value, ast.Dict):
            return {}
        out: dict[str, str] = {}
        for k, v in zip(node.value.keys, node.value.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            reason = ''
            if isinstance(v, ast.Tuple) and v.elts:
                head = v.elts[0]
                if isinstance(head, ast.Constant) and isinstance(head.value, str):
                    reason = head.value
            elif isinstance(v, ast.Constant) and isinstance(v.value, str):
                reason = v.value
            out[k.value] = reason
        return out
    return {}
def main() -> int:
    ap = argparse.ArgumentParser(description='job 调度覆盖守门（#1934）')
    ap.add_argument('--quiet', action='store_true', help='只在失败时输出')
    args = ap.parse_args()

    # Windows 控制台默认 GBK，直接 print 中文/符号会 UnicodeEncodeError 崩掉——
    # 守门在本地跑崩 = 守门失效。统一把输出流切到 UTF-8。
    for _stream in (sys.stdout, sys.stderr):
        # 老版本 Python 无reconfigure；缺这个 API 不该让守门崩（那时输出可能仍乱码，但不致命）
        reconfigure = getattr(_stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8')
            except (AttributeError, ValueError, OSError):
                pass

    for p in (ORCHESTRATOR_PY, SCHEDULER_PY):
        if not p.exists():
            print(f'[FAIL] 找不到文件：{p}', file=sys.stderr)
            return 2

    orch_tree = _parse(ORCHESTRATOR_PY)
    sched_tree = _parse(SCHEDULER_PY)

    registered = _collect_registered_jobs(orch_tree)
    assign_total = _count_jobs_assignments(orch_tree)
    scheduled = set(_tuple_literal_strings(sched_tree, '_JOB_TEMPLATES'))
    not_scheduled = _dict_literal_pairs(sched_tree, '_NOT_SCHEDULED')

    problems: list[str] = []

    # 形态变化检测：静态解析的代价是「注册写法变了」会静默漏抓，故显式拦住
    if assign_total == 0:
        problems.append(
            'orchestrator 里没有 self.jobs[...] = ... 语句——注册形态变了？'
            '守门需同步更新 _collect_registered_jobs'
        )
    if assign_total != len(registered):
        problems.append(
            f'注册语句共 {assign_total} 条，但只抓到 {len(registered)} 个字面量 key——'
            f'存在变量下标注册（self.jobs[name] = ...），会被静默漏抓'
        )
    if not scheduled:
        problems.append(
            'daily_scheduler 里没抓到 _JOB_TEMPLATES 的字符串字面量——'
            '清单形态变了？守门会静默放过，需同步更新'
        )
    if not not_scheduled:
        problems.append(
            'daily_scheduler 里没抓到 _NOT_SCHEDULED 字典——'
            '「明确不调度」登记表缺失或形态变了'
        )
    covered = scheduled | set(not_scheduled)
    missing = sorted(registered - covered)

    # 登记了但编排器已不再注册 → 登记表变成墓地，会误导下一个读代码的人
    for name in sorted(set(not_scheduled) - registered):
        problems.append(
            f'_NOT_SCHEDULED 里有 {name}，但编排器已不再注册它——'
            f'要么恢复注册，要么从登记表删掉（别让登记变成墓地）'
        )

    # 每条登记必须写清理由，空理由等于没登记
    for name, reason in sorted(not_scheduled.items()):
        if not reason.strip():
            problems.append(f'_NOT_SCHEDULED[{name}] 的理由是空的——必须写清为什么不进每日调度')

    for name in missing:
        problems.append(
            f'job {name} 已在 orchestrator 注册，但既不在 daily_scheduler._JOB_TEMPLATES，'
            f'也没登记进 _NOT_SCHEDULED——请二选一：'
            f'① 数据日变化且用户直接可见 → 加进 _JOB_TEMPLATES；'
            f'② 否则 → 登记进 _NOT_SCHEDULED 并写明理由与建议频率'
        )

    if problems:
        print(f'[FAIL] job 调度覆盖守门失败（{len(problems)} 项）：\n', file=sys.stderr)
        for p in problems:
            print(f'  · {p}', file=sys.stderr)
        print(
            f'\n已注册 {len(registered)} / 每日调度 {len(scheduled)} / '
            f'明确不调度 {len(not_scheduled)}（并集覆盖 {len(covered)}）',
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(
            f'[OK] job 调度覆盖守门通过：已注册 {len(registered)} 个 job，'
            f'每日调度 {len(scheduled)} 个 + 明确不调度 {len(not_scheduled)} 个 = 全覆盖'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())

