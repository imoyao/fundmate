#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步元数据 CLI 入口（pdm run sync / python app/tools/sync_metadata.py）。

支持：
- `sync --job <name>` 单 job 执行
- `sync --all` 全量执行
- `sync --full-sync` 启用全量回填模式（仅限逐标的回填型 job 必须带 --targets/--target-file）
- `sync --targets <code,...>` 显式指定回填标的（逐标的回填型 job 强制）
- `sync --target-file <csv>` 从 CSV 读取回填标的（批量/全量回填场景）
- `sync --snapshot <path>` 导出市场域只读快照（只含市场域表，不含用户数据）
- `sync --import-snapshot <file>` 导入已下载的快照文件（校验 + 幂等去重，不覆盖本地记录）

用法示例：
  pdm run sync --job temperature
  pdm run sync --job fund_nav --full-sync --targets 000001,000002
  pdm run sync --job fund_position --target-file positions.csv
  pdm run sync --all --full-sync --target-file all_funds.csv
  pdm run sync --snapshot ./snapshot.db
  pdm run sync --import-snapshot ./snapshot.db
"""

import os
import sys
import time
from pathlib import Path

# 将项目根目录（backend/）加入 Python 路径 —— 必须在 import app 之前。
# pdm run sync 以「脚本路径」方式运行（python app/tools/sync_metadata.py），
# sys.path[0] 是 app/tools/ 而非 backend/，不补路径则 import app 直接
# ModuleNotFoundError（#1366 实测）。需向上三级：tools/ → app/ → backend/。
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from loguru import logger  # noqa: E402

# ✅ 在入口文件顶部加载 .env（相对于 backend/ 目录）
env_path = BACKEND_DIR / '.env'
load_dotenv(dotenv_path=env_path)

from app.core.database import get_db, init_db  # noqa: E402
from app.core.db_factory import app_db_startup_check, resolve_app_db  # noqa: E402
from app.services.sync.orchestrator import DataSyncOrchestrator  # noqa: E402

# `--target-file` 时按 job 决定从 CSV 里取哪一类代码。
# ⚠️ 漏掉某个 job 的后果不是报错，而是 targets 保持 None → 静默跑成「0 只处理」。
FUND_TARGET_JOBS = ('fund_nav', 'fund_detail_enrich', 'fund_manager', 'fund_position')

# Stock 类 job（--target-file 走 stock 池）。
STOCK_TARGET_JOBS = ('price_history', 'fund_position_legacy')

# 受限目标池 job：**未给任何显式目标时，从库内核心池（持仓 + 自选）现取**。
#
# 为什么必须单独列：`targets=None` 在 `job_base.SyncJob.run()` 里的语义是
# 「子类自取全部数据」（第 195 行分支），而对这类 job 是「目标池为空 → 显式跳过」
# （`data-strategy.md` §4.3.3 红线）。`daily_scheduler` 走
# `spec.target_kind` + `resolve_targets()`，所以周任务正常；CLI 没有这条路，
# 于是 `pdm run sync --job fund_position` 会静默跑成「0 只、status=success」，
# 比报错更危险——手工回填的人会以为成了（2026-10-01 实测踩到）。
#
# 值为 resolve_targets() 的池键（str 或元组，`_combine_pools` 统一兼容）：
# fund_position 需要 fund + etf 两池（#1983：场内 ETF 的底层持仓 / 行业配置
# 同样要抓），与 daily_scheduler 的 target_kind=('fund', 'etf') 同源覆盖，
# CLI 单 job 路径不再漏掉 etf 池。
#
# ⚠️ 不要顺手把 fund_nav / fund_detail_enrich / fund_manager 一并放进这里：
# 它们的 `targets=None` 是「子类自取核心池」的既有语义，赋成显式列表会把执行
# 切成 `_execute_batches` 分批路径，属行为变更，需单独评估。
DB_POOL_JOBS = {'fund_position': ('fund', 'etf')}


def _combine_pools(resolved: dict, keys) -> list:
    """把 resolve_targets() 返回的多个池合并成列表（去重）。"""
    if isinstance(keys, str):
        keys = (keys,)
    out = []
    for k in keys:
        out.extend(resolved.get(k, []))
    return list(dict.fromkeys(out))


def _resolve_targets_from_file(target_file: str) -> list:
    """从 CSV 文件读取标的代码（支持单列或多列，取第一列）。"""
    import csv

    with open(target_file, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        codes = [row[0].strip() for row in reader if row and row[0].strip()]
    return codes


def resolve_job_targets(orch, job: str, targets: str | None, target_file: str | None) -> list | None:
    """根据 job 与显式参数解析目标池。

    优先级：显式 --targets > --target-file > DB_POOL_JOBS 从库内核心池取 > None（交给 job 处理）

    - DB_POOL_JOBS 里的 job（fund_position）：None 会被当成显式跳过，必须显式解析核心池
    - 其他 job：None 保持原有「子类自取核心池」语义
    """
    # 1. 显式 --targets 直接用
    if targets:
        return [code.strip() for code in targets.split(',') if code.strip()]

    # 2. --target-file：走 orchestrator 的 resolve_targets() 组合对应池（不读文件，文件读取在 CLI 层）
    if target_file:
        resolved = orch.resolve_targets()
        if job in FUND_TARGET_JOBS:
            # fund_nav 等只吃 fund 池；fund_position 吃 fund + etf（_combine_pools 统一）
            return _combine_pools(resolved, DB_POOL_JOBS.get(job, 'fund'))
        if job in STOCK_TARGET_JOBS:
            # stock 分支（price_history 等）
            return resolved.get('stock', [])
        # 未知 job：不处理 target-file，返回 None
        return None

    # 3. 无显式目标：DB_POOL_JOBS 里的 job 必须从库内核心池取
    if job in DB_POOL_JOBS:
        return _combine_pools(orch.resolve_targets(), DB_POOL_JOBS[job])

    # 4. 其他 job 保持 None 语义（子类自取）
    return None


def main():
    parser = __import__('argparse').ArgumentParser(description='同步元数据 CLI（同步 / 快照导出入口）')
    parser.add_argument(
        '--job',
        type=str,
        metavar='NAME',
        help='执行单个同步 job（如 temperature, fund_nav, fund_position 等）',
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='执行所有同步 job（按 orchestrator 注册顺序）',
    )
    parser.add_argument(
        '--full-sync',
        action='store_true',
        help='启用全量回填模式（逐标的回填型 job 必须配合 --targets/--target-file）',
    )
    parser.add_argument(
        '--targets',
        type=str,
        metavar='CODES',
        help='逗号分隔的显式回填标的（逐标的回填型 job 强制要求）',
    )
    parser.add_argument(
        '--target-file',
        type=str,
        metavar='CSV',
        help='从 CSV 读取回填标的（首列为代码），用于批量/全量回填',
    )
    parser.add_argument(
        '--snapshot',
        type=str,
        metavar='PATH',
        help='导出市场域只读快照到 PATH（#1776 ⑤ DB 下载导入层；只含市场域表，不含用户数据）',
    )
    parser.add_argument(
        '--import-snapshot',
        type=str,
        metavar='FILE',
        help='导入已下载的快照文件（校验 + 按本地唯一约束幂等去重，不覆盖本地记录）',
    )
    args = parser.parse_args()

    # 启动即打印 + 守卫 market 域运行库解析（#2344）：显式目标（--targets/--target-file/--snapshot/--import-snapshot）
    # 的批量修复场景，对「解析出的库文件不存在」fail-closed——对着不存在的库重同步
    # 只会静默新建空库后全部跳过（2026-10-18 worktree 实测事故）；日常增量仅告警，
    # 不误伤 fresh clone 首跑就地建库。
    # 启动即打印 + 守卫 market 域运行库解析（#2344）：显式目标（--targets/--target-file/--snapshot/--import-snapshot）
    # 的批量修复场景，对「解析出的库文件不存在」fail-closed——对着不存在的库重同步
    # 只会静默新建空库后全部跳过（2026-10-18 worktree 实测事故）；日常增量仅告警，
    # 不误伤 fresh clone 首跑就地建库。
    strict = bool(args.targets or args.target_file or args.snapshot or args.import_snapshot)
    db_problem = app_db_startup_check(strict=strict)
    
    # 无论 strict 与否，都把目标信息打印到 stdout（供 test_cli_prints_target_before_running 断言）
    env = os.getenv('APP_ENV', 'development')
    url, source = resolve_app_db(env)
    print(f'运行库目标（APP_ENV={env}）: market 域: {url}（解析来源: {source}）')
    
    if db_problem:
        # 显式配置了数据库（source != 'default'）但文件不存在：配置错误，直接报错（无论 strict）
        # strict=True 的场景也走这儿（返回码 2）
        print(f'错误：{db_problem}', file=sys.stderr)
        sys.exit(2)

    # 快照导出 / 导入（#1776 ⑤）：文件通道，与同步互斥（设计：初始化/重建不再全市场拉取）
    if args.snapshot or args.import_snapshot:
        if args.snapshot and args.import_snapshot:
            print('错误：--snapshot 与 --import-snapshot 只能二选一')
            sys.exit(2)
        if args.all or args.job or args.full_sync or args.targets or args.target_file:
            print('错误：--snapshot / --import-snapshot 不能与 --all/--job/--full-sync/--targets/--target-file 同用')
            sys.exit(2)
        _run_snapshot_command(args)
        return

    if not args.all and not args.job:
        parser.print_help()
        return

    # 初始化数据库（创建表）
    # 域模型必须先于 init_db 全量导入：部分表存在跨模块外键（如 position_import_meta
    # → ledgers.id），缺导入会让 Base.metadata 解析 FK 时抛 NoReferencedTableError
    # （E账户对账上线后 sync CLI 首跑即暴露，2026-08-24）。
    import app.domains.assets.models  # noqa: F401
    import app.domains.families.models  # noqa: F401
    import app.domains.funds.models  # noqa: F401
    import app.domains.indices.models  # noqa: F401
    import app.domains.ledgers.models  # noqa: F401
    import app.domains.market.models  # noqa: F401
    import app.domains.portfolios.models  # noqa: F401
    import app.domains.positions.models  # noqa: F401
    import app.domains.price_history.models  # noqa: F401
    import app.domains.securities.models  # noqa: F401
    import app.domains.strategy.models  # noqa: F401
    import app.domains.summary.models  # noqa: F401
    import app.domains.transactions.models  # noqa: F401
    import app.domains.users.models  # noqa: F401
    import app.domains.watchlist.models  # noqa: F401
    import app.models.sync_log  # noqa: F401

    init_db()

    with get_db() as db:
        # 确保同步相关字段存在
        ensure_fund_sync_fields(db)
        orchestrator = DataSyncOrchestrator(db)

        try:
            if args.all:
                # --all --full-sync 必须带 --target-file 范围，否则全市场逐标的全量回填
                # 会触发数据源封禁且耗时极长（#824 / #1776 ④）
                if args.full_sync and not args.target_file:
                    print(
                        '错误：--all --full-sync 必须配合 --target-file <csv> 限定范围，'
                        '禁止裸调用（全市场逐标的全量回填会触发数据源封禁）。'
                    )
                    sys.exit(2)
                start = time.time()
                results = orchestrator.run_all_jobs(full_sync=args.full_sync, target_file=args.target_file)
                elapsed = time.time() - start
                print(f'✅ 全量同步完成，耗时 {elapsed:.1f}s')
                for r in results:
                    status = '✅' if r.success else '❌'
                    print(f'  {status} {r.job_name}: {r.message} ({r.duration_ms}ms)')
                if any(not r.success for r in results):
                    sys.exit(1)
            else:
                # 单 job
                if args.job in FUND_TARGET_JOBS:
                    targets = None
                    if args.targets:
                        targets = [c.strip() for c in args.targets.split(',') if c.strip()]
                    elif args.target_file:
                        targets = _resolve_targets_from_file(args.target_file)
                    else:
                        # fund_position 从库内核心池现取（DB_POOL_JOBS）
                        if args.job in DB_POOL_JOBS:
                            from app.services.sync.orchestrator import resolve_targets

                            resolved = resolve_targets(db)
                            targets = _combine_pools(resolved, DB_POOL_JOBS[args.job])
                            if not targets:
                                print(f'ℹ️ {args.job}: 库内核心池（持仓+自选）为空，跳过')
                                return
                        else:
                            print(
                                f'错误：{args.job} 属逐标的回填型 job（FUND_TARGET_JOBS），'
                                '必须显式指定 --targets <code,...> 或 --target-file <csv>（#824 / #1776 ④）'
                            )
                            sys.exit(2)

                    # --full-sync 校验：逐标的回填型 job 必须带 --full-sync 才走全量模式
                    if not args.full_sync:
                        print(
                            f'提示：{args.job} 在增量模式下运行（仅回填缺失日期）。'
                            '如需全量回填（含历史），请加 --full-sync。'
                        )

                    result = orchestrator.run_job(args.job, full_sync=args.full_sync, targets=targets)
                    status = '✅' if result.success else '❌'
                    print(f'{status} {result.job_name}: {result.message} ({result.duration_ms}ms)')
                    if not result.success:
                        sys.exit(1)
                else:
                    # 列表型 / 指数型 / 温度计型 job：单次调用换全市场，裸 --full-sync 为正常模式
                    if args.full_sync and not (args.targets or args.target_file):
                        logger.warning(
                            f'{args.job} 裸带 --full-sync（列表/指数/温度计型 job 单次即换全市场，目标参数被忽略）。'
                        )
                    result = orchestrator.run_job(args.job, full_sync=args.full_sync)
                    status = '✅' if result.success else '❌'
                    print(f'{status} {result.job_name}: {result.message} ({result.duration_ms}ms)')
                    if not result.success:
                        sys.exit(1)
        except Exception as e:
            logger.exception('同步执行异常: {}', e)
            sys.exit(1)


def ensure_fund_sync_fields(db):
    """确保 funds 表的同步相关字段存在（SQLite 迁移：若缺则加列，幂等）。

    需要的字段：
    - fund_type_id: 基金小类 ID（用于风险榜单分组，#167）
    - company_id: 基金管理公司 ID（用于经理/公司画像，#1970）
    - manager_ids: 基金经理 ID 列表（JSON 文本，用于经理筛选）
    - latest_nav_date: 最新净值日期（前端详情页展示）
    - latest_nav: 最新净值（前端详情页展示）
    - last_synced_at: 最后同步时间（前端展示同步新鲜度）

    这些字段在早期模型里可能不存在（分批加列），老库需补齐。
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.bind)
    cols = {c['name'] for c in inspector.get_columns('funds')}

    additions = {
        'fund_type_id': 'INTEGER',
        'company_id': 'INTEGER',
        'manager_ids': 'TEXT',
        'latest_nav_date': 'DATE',
        'latest_nav': 'DECIMAL(18,6)',
        'last_synced_at': 'DATETIME',
    }
    for col_name, col_type in additions.items():
        if col_name not in cols:
            db.execute(text(f'ALTER TABLE funds ADD COLUMN {col_name} {col_type}'))
    if additions.keys() - cols:
        db.commit()
        logger.info('funds 表已补齐同步相关字段: {}', ', '.join(additions.keys() - cols))


def _run_snapshot_command(args):
    """运行快照导出/导入命令。"""
    from app.services.sync.snapshot import export_snapshot, import_snapshot

    if args.snapshot:
        # 导出快照
        path = Path(args.snapshot)
        # 父目录不存在则建
        path.parent.mkdir(parents=True, exist_ok=True)
        export_snapshot(path)
        print(f'✅ 快照已导出: {path}')
    else:
        # 导入快照
        path = Path(args.import_snapshot)
        if not path.exists():
            print(f'错误：快照文件不存在: {path}')
            sys.exit(2)
        stats = import_snapshot(path)
        print(f'✅ 快照已导入: {path}')
        for table, count in stats.items():
            print(f'  {table}: {count} 行')


if __name__ == '__main__':
    # 退出码必须传出去：#2344 的预检靠 `return 2` 表达「拒绝继续」，若这里忽略返回值，
    # shell/CI 看到的仍是 0——那和没拦一样。
    raise SystemExit(main() or 0)
