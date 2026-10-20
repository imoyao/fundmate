#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守门：每日调度的每个 job，都必须在 `backend/.env.example` 里有开关（#1186）。

WHY —— 两张清单互不引用，忘了同步不会报错
--------------------------------------------
`daily_scheduler._JOB_TEMPLATES` 是「哪些 job 进本机每日调度」的**唯一事实来源**，
而 `backend/.env.example` 是部署者「知道有哪些开关可调」的**唯一入口**。两者由不同的人
在不同时间改，且都不引用对方：

- 往 `_JOB_TEMPLATES` 加了 job、忘了补 `.env.example` ⇒ 用户**调不了**这个任务，
  也看不出它被调度了（`.env.example` 里没有的字面量，就是「不存在」）；
- 反过来，`.env.example` 留着已改名/已删除的开关 ⇒ 用户照着它配，配了个空气。

实证（#1186 盘点，2026-10-19）：`_JOB_TEMPLATES` 当时已有 **15** 个 job，而
`.env.example` 只登记了 **8** 个——漏掉的 7 个里包含 **`price_history`（场内日线 OHLC）**，
正是 #1186 点名要「股票每日开盘/收盘/最高/最低」的那一项。也就是说：本机其实**每天都跑**
场内日线，而 `.env.example` 里连它的开关都没有。（同批漏登记的还有
`market_asset_daily` / `index_valuation` / `convertible_bond` / `dividend_split` /
`fund_position` / `orphan_backfill`。）

判据
----
1. **正向**：`_JOB_TEMPLATES` 每项的「开关环境变量」与「cron 环境变量」两个常量，
   其**字面量**（如 `SCHEDULER_PRICE_HISTORY_ENABLED`）都必须作为变量名出现在
   `backend/.env.example`（注释形式 `# SCHEDULER_X_ENABLED=true` 或真实赋值均可）。
2. **反向**：`.env.example` 里出现的 `SCHEDULER_*_CRON` 必须都能在 `daily_scheduler.py`
   的常量里找到出处（`_CRON` 后缀是 job 专属，全局开关不带；防「代码改了名、示例留旧名」）。

⚠️ **失败态（AGENTS.md「拿不到输入 ≠ 输入为空」）**
解析不到 `_JOB_TEMPLATES`、解析不到任何 `ENV_*` 常量字面量、或读不到 `.env.example` 的
任何变量时，**必须报红**——不得退化成「没有可检查的项 ⇒ 通过」。那正是「守门自己失明、
却每轮报绿」的形态（同 `#171` 的空映射假绿）。

用 ast 静态解析而非 import
--------------------------
import `daily_scheduler` 会连带加载 Flask / SQLAlchemy / 各域 models，
CI 里跑不动（同 `guard_job_schedule_coverage.py` 的取舍）。代价是「动态生成模板」会漏抓，
故对形态做断言：`_JOB_TEMPLATES` 的每项必须是「job 名字面量 + 两个 env 引用」的元组。

用法
----
    python scripts/guard_scheduler_env_example.py            # 校验（CI）
    python scripts/guard_scheduler_env_example.py --quiet     # 只在失败时输出

退出码：0 = 通过；1 = 命中；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / 'backend'
SCHEDULER_PY = BACKEND_DIR / 'app' / 'services' / 'daily_scheduler.py'
ENV_EXAMPLE = BACKEND_DIR / '.env.example'

# `.env.example` 里的变量行：允许注释前缀（示例文件里开关都是注释形式）、
# 允许 `export VAR=` 形式（部分部署脚本会那样写）。
_ENV_LINE_RE = re.compile(r'^\s*(?:#\s*)?(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=', re.MULTILINE)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def _module_const_str_map(tree: ast.Module) -> dict[str, str]:
    """抽模块级 `NAME = '<字面量>'`（含带注解的 AnnAssign），返回 {NAME: 字面量}。"""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if not (isinstance(target, ast.Name) and isinstance(value, ast.Constant)):
            continue
        if isinstance(value.value, str):
            out[target.id] = value.value
    return out


def _module_assignment_value(tree: ast.Module, var_name: str):
    """取模块级变量 var_name 的赋值右值，同时支持 Assign 与带注解的 AnnAssign。

    （与 `guard_job_schedule_coverage.py` 同源：`_JOB_TEMPLATES: Tuple[...] = (...)`
    是**带注解**的赋值，只认 Assign 会漏。）
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


def _job_env_nodes(tree: ast.Module) -> list[tuple[str, ast.expr, ast.expr]]:
    """抽 `_JOB_TEMPLATES` 每项的 (job 名, 开关 env 节点, cron env 节点)。

    元组形态变了（不再是「6 项、前三位是 名字 + 两个 env 引用」）就返回空——
    main() 会把它当成「拿不到输入」报红，而不是静默放过。
    """
    value = _module_assignment_value(tree, '_JOB_TEMPLATES')
    if value is None or not isinstance(value, ast.Tuple):
        return []
    out: list[tuple[str, ast.expr, ast.expr]] = []
    for elt in value.elts:
        if not isinstance(elt, ast.Tuple) or len(elt.elts) < 3:
            return []
        head = elt.elts[0]
        if not (isinstance(head, ast.Constant) and isinstance(head.value, str)):
            return []
        out.append((head.value, elt.elts[1], elt.elts[2]))
    return out


def _resolve_env_name(
    node: ast.expr,
    consts: dict[str, str],
    *,
    job: str,
    which: str,
    problems: list[str],
) -> str | None:
    """把 `ENV_PRICE_HISTORY_ENABLED` 这类引用解析成字面量，顺带记录形态异常。"""
    if isinstance(node, ast.Name):
        literal = consts.get(node.id)
        if literal is None:
            problems.append(
                f'job {job} 的 {which} 引用常量 {node.id}，但模块里找不到它的字符串字面量定义——'
                f'常量被删/改名了？'
            )
            return None
        return literal
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # 直接写字面量也认（不强制非得走常量），但要在注释里说清为何放行
        return node.value
    problems.append(
        f'job {job} 的 {which} 既不是常量引用也不是字符串字面量（模板形态变了？）'
    )
    return None


def _env_example_names(src: str) -> set[str]:
    """抽 `.env.example` 里出现过的变量名（注释行也算）。"""
    return {m.group(1) for m in _ENV_LINE_RE.finditer(src)}


def check(scheduler_src: str, env_src: str) -> list[str]:
    """返回问题列表；空列表 = 通过。纯函数，便于回归网喂假样本。"""
    problems: list[str] = []

    try:
        tree = ast.parse(scheduler_src)
    except SyntaxError as exc:
        return [f'daily_scheduler.py 语法错误，无法解析（{exc}）——结论不可信']

    consts = _module_const_str_map(tree)
    jobs = _job_env_nodes(tree)

    # ── 失败态：拿不到输入必须报红，不得当成「没有可检查的项」 ──
    if not jobs:
        problems.append(
            '没能在 daily_scheduler.py 里抓到 `_JOB_TEMPLATES` 的字符串字面量——'
            '清单缺失或形态变了？守门会静默放过，需同步更新 `_job_env_nodes`'
        )
        return problems
    if not consts:
        problems.append(
            '没能在 daily_scheduler.py 里抓到任何 `NAME = \'字面量\'` 常量——'
            '常量表形态变了？守门会静默放过'
        )
        return problems

    env_names = _env_example_names(env_src)
    if not env_names:
        problems.append(
            '没能从 backend/.env.example 里解析出任何变量名——'
            '文件缺失或被改写成了别的形态？守门会静默放过'
        )
        return problems

    # ── 正向：每个 job 的开关 + cron 都要在示例里出现 ──
    for job, enabled_node, cron_node in jobs:
        for which, node in (('开关', enabled_node), ('cron', cron_node)):
            literal = _resolve_env_name(
                node, consts, job=job, which=which, problems=problems
            )
            if literal is None:
                continue
            if literal not in env_names:
                problems.append(
                    f'job `{job}` 的{which}变量 `{literal}` 未登记在 backend/.env.example——'
                    f'用户既调不了它，也看不出它被调度了。'
                    f'请在「每日任务与触发时刻」段补上 `# {literal}=...`'
                )

    # ── 反向：示例里的 `*_CRON` 必须都能在代码里找到出处 ──
    # `_CRON` 后缀是 job 专属（全局开关 SCHEDULER_ENABLED / _TIMEZONE 等不带），
    # 故用它做反向判据不会误伤全局项。
    known_literals = set(consts.values())
    for name in sorted(env_names):
        if name.endswith('_CRON') and name not in known_literals:
            problems.append(
                f'backend/.env.example 里的 `{name}` 在 daily_scheduler.py 里找不到出处——'
                f'代码改了名 / 删了 job，而示例留着旧开关？'
            )

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description='每日调度开关与 .env.example 一致性守门（#1186）')
    ap.add_argument('--quiet', action='store_true', help='只在失败时输出')
    args = ap.parse_args()

    # Windows 控制台默认 GBK，直接 print 中文/符号会 UnicodeEncodeError 崩掉——
    # 守门在本地跑崩 = 守门失效。统一把输出流切到 UTF-8。
    for _stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(_stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8')
            except (AttributeError, ValueError, OSError):
                pass

    for p in (SCHEDULER_PY, ENV_EXAMPLE):
        if not p.exists():
            print(f'[FAIL] 找不到文件：{p}', file=sys.stderr)
            return 2

    problems = check(
        SCHEDULER_PY.read_text(encoding='utf-8'),
        ENV_EXAMPLE.read_text(encoding='utf-8'),
    )

    if problems:
        print(f'[FAIL] 每日调度开关守门失败（{len(problems)} 项）：\n', file=sys.stderr)
        for p in problems:
            print(f'  · {p}', file=sys.stderr)
        return 1

    if not args.quiet:
        tree = _parse(SCHEDULER_PY)
        jobs = _job_env_nodes(tree)
        print(
            f'[OK] 每日调度开关守门通过：_JOB_TEMPLATES 的 {len(jobs)} 个 job '
            f'（开关 + cron 共 {len(jobs) * 2} 个变量）全部登记在 backend/.env.example'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())