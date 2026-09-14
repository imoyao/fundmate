# -*- coding: utf-8 -*-
"""
fundmate 开发任务集合（invoke + rich）

把日常开发指令统一到一个入口，避免散落在 README / 命令行记忆里：
  - 数据抓取（复用 app.tools.sync_cli）
  - 本机每日调度状态（sched.status，只读）
  - 测试（pytest，默认单进程；按模块/全量）
  - 后端启动（uvicorn）
  - 文档（前端 docs 站点，需到 frontend 目录）

用法：
    pdm run invoke --list              # 列出全部任务
    pdm run invoke grab.temperature    # 跑市场温度同步
    pdm run invoke sched.status        # 查看本机每日调度状态（只读）
    pdm run invoke test                # 跑全部后端测试
    pdm run invoke test --path backend/tests/services
    pdm run invoke serve               # 启动 API（默认 :5000）
    pdm run invoke docs.dev            # 本地文档预览

说明：
    - 抓取 / 验证类命令直接复用 sync_cli，保证单一事实来源，本文件不重复实现业务。
    - 「后续后端接口封装」属于路线图 §2.3 的远期项，待主线（B3/B5）收尾后再把
      serve/test 之外的接口级任务（如单接口冒烟、mock 数据生成）逐步补进本文件。
"""

from pathlib import Path

from invoke import Collection, task
from rich.console import Console
from rich.table import Table

# backend/ 根目录（tasks.py 位于 backend/）
BACKEND_ROOT = Path(__file__).resolve().parent
# 仓库根目录（backend 的上一级）
REPO_ROOT = BACKEND_ROOT.parent
# 前端目录（docs 站点脚本所在）
FRONTEND_ROOT = REPO_ROOT / 'frontend'

console = Console(emoji=False)


def _run(c, cmd: str, title: str) -> int:
    """统一打印标题并运行命令，返回退出码（直接透传底层命令退出码）。

    注意：底层命令自身可能用退出码表达业务语义（例如 sync_cli verify-jisilu
    在「无 level」时返回 1，这是预期的诊断结果而非执行失败），因此本函数
    不把非零退出码当作异常，仅如实反馈，由调用方决定如何解读。
    """
    console.rule(f'[bold cyan]{title}[/bold cyan]')
    console.print(f'[dim]$ {cmd}[/dim]')
    # pty 在 Windows 上不可用，统一用非 pty；echo 保证可见
    result = c.run(cmd, pty=False, warn=True, echo=True)
    code = result.return_code if result is not None else 1
    mark = 'OK' if code == 0 else 'EXIT=%d' % code
    console.print(f'[bold]{mark}[/bold] <- {title}')
    return code


def _list_tasks() -> None:
    """打印任务速查表（pdm run invoke --list 的友好版）。"""
    table = Table(title='fundmate 开发任务速查', show_lines=False)
    table.add_column('任务', style='bold cyan', no_wrap=True)
    table.add_column('说明', style='white')
    rows = [
        ('grab.temperature', '市场温度同步（集思录/韭圈儿/自算估值分位；乖离率跳过）'),
        ('grab.all', '全部同步任务（元数据 + 温度）'),
        ('grab.job <name>', '透传跑单个 Job（如 fund_nav / temperature）'),
        ('grab.verify-jisilu', '只读诊断：确认 jisilu_indicator 已含 level 字段'),
        ('sched.status', '只读查看本机每日调度：开关 / 单实例锁 / 各任务上次成功时间'),
        ('test', '跑后端 pytest（默认全量、单进程；可用 --path 限定）'),
        ('serve', '启动 API（uvicorn，默认 0.0.0.0:5000）'),
        ('docs.dev', '本地文档预览（vuepress dev，需 frontend 环境）'),
        ('docs.build', '构建静态文档（vuepress build）'),
        ('help', '打印本速查表'),
    ]
    for name, desc in rows:
        table.add_row(name, desc)
    console.print(table)


# --------------------------------------------------------------------------- #
# 抓取类任务（复用 app.tools.sync_cli，保证单一事实来源）
# --------------------------------------------------------------------------- #
@task
def temperature(c, full_sync=False):
    """跑市场温度同步（乖离率跳过）。"""
    flag = ' --full-sync' if full_sync else ''
    return _run(
        c,
        f'pdm run python -m app.tools.sync_cli temperature{flag}',
        '市场温度同步',
    )


@task
def all(c, full_sync=False):  # noqa: A001 - invoke 约定任务名
    """跑全部同步任务。"""
    flag = ' --full-sync' if full_sync else ''
    return _run(c, f'pdm run python -m app.tools.sync_cli all{flag}', '全部同步任务')


@task
def job(c, name, full_sync=False):
    """透传跑单个 Job，如 fund_nav / temperature。"""
    flag = ' --full-sync' if full_sync else ''
    return _run(
        c,
        f'pdm run python -m app.tools.sync_cli job {name}{flag}',
        f'同步 Job: {name}',
    )


@task(name='verify-jisilu')
def verify_jisilu(c):
    """只读诊断：确认 jisilu_indicator 是否已含 level 字段（B2 端到端验证）。"""
    return _run(
        c,
        'pdm run python -m app.tools.sync_cli verify-jisilu',
        '验证 jisilu_indicator level 字段',
    )


# --------------------------------------------------------------------------- #
# 本机每日调度（#1467）
# --------------------------------------------------------------------------- #
@task(name='status')
def sched_status(c):
    """只读查看本机每日调度状态（开关 / 单实例锁 / 各任务上次成功时间）。

    调度本身不常驻：开关打开时由应用启动时进程内调度，否则用
    `pdm run scheduler-daemon` 常驻。本任务只读，便于确认「到底跑没跑」。
    """
    return _run(c, 'pdm run scheduler --status', '每日调度状态')


# --------------------------------------------------------------------------- #
# 测试任务
# --------------------------------------------------------------------------- #
@task
def test(c, path='tests', k=''):
    """跑后端 pytest（默认单进程，强制禁用 xdist 并行）。

    单进程原因：pypinyin(3.2MB 词典) + pandas + akshare + playwright 等重型依赖在
    xdist 多 worker 下会被各进程重复加载，撑爆本机内存导致 OOM；单进程下全部测试正常。
    -p no:xdist 显式禁用并行，防止误加 -n 破坏（即便环境装了 pytest-xdist 也不会并行）。
    """
    # tasks.py 在 backend/ 下执行，path 统一相对 BACKEND_ROOT 解析，避免传仓库根路径前缀。
    target = (BACKEND_ROOT / path).as_posix() if not Path(path).is_absolute() else path
    extra = f' -k {k}' if k else ''
    return _run(
        c,
        f'pdm run python -m pytest -p no:xdist {target}{extra}',
        f'后端测试 ({path}{" -k " + k if k else ""}, 单进程)',
    )


# --------------------------------------------------------------------------- #
# 启动任务
# --------------------------------------------------------------------------- #
@task
def serve(c, host='0.0.0.0', port=5000, reload=True):
    """启动 API（uvicorn，默认 0.0.0.0:5000，开发模式热重载）。"""
    watch = '--reload' if reload else ''
    return _run(
        c,
        f'pdm run uvicorn app:app --app-dir backend --host {host} --port {port} {watch}',
        f'启动 API ({host}:{port})',
    )


# --------------------------------------------------------------------------- #
# 文档任务（前端 docs 站点）
# --------------------------------------------------------------------------- #
@task(name='docs.dev')
def docs_dev(c):
    """本地文档预览（vuepress dev，需 frontend 依赖已安装）。"""
    if not (FRONTEND_ROOT / 'node_modules').exists():
        console.print('[yellow]⚠ frontend/node_modules 不存在，请先在 frontend 执行 pnpm install[/yellow]')
    return _run(c, 'pnpm run docs:dev', '文档预览 (vuepress dev)')


@task(name='docs.build')
def docs_build(c):
    """构建静态文档（vuepress build）。"""
    return _run(c, 'pnpm run docs:build', '文档构建 (vuepress build)')


# --------------------------------------------------------------------------- #
# 帮助
# --------------------------------------------------------------------------- #
@task
def help(c):  # noqa: A001
    """打印任务速查表。"""
    _list_tasks()


# 命名空间：抓取归类到 grab.*，文档归类到 docs.*
GRAB = Collection('grab')
GRAB.add_task(temperature, name='temperature')
GRAB.add_task(all, name='all')
GRAB.add_task(job, name='job')
GRAB.add_task(verify_jisilu, name='verify-jisilu')

DOCS = Collection('docs')
DOCS.add_task(docs_dev, name='dev')
DOCS.add_task(docs_build, name='build')

SCHED = Collection('sched')
SCHED.add_task(sched_status, name='status')

# 顶级集合（关键字参数给子集合命名，避免 "Non-root collections must have a name!"）
namespace = Collection(grab=GRAB, docs=DOCS, sched=SCHED, test=test, serve=serve, help=help)
