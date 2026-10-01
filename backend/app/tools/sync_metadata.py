# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:27
# File : sync_metadata.py
# !/usr/bin/env python
"""
多多贝 元数据同步脚本

用法:
    # 日常增量更新（推荐每天运行）
    python app/tools/sync_metadata.py --all

    # 通过 CSV 文件指定要同步的基金/股票代码
    python app/tools/sync_metadata.py --all --target-file codes.csv

    # 单独执行某个任务
    python app/tools/sync_metadata.py --job fund_nav
    python app/tools/sync_metadata.py --job fund_detail_enrich --target-file codes.csv

    # 强制全量同步（拉取全部历史数据，耗时长，仅首次或需要修复时使用）
    # 注意：--full-sync 必须带范围，禁止裸调用（见下方「同步入口职责」）
    python app/tools/sync_metadata.py --all --full-sync --target-file codes.csv
    python app/tools/sync_metadata.py --job fund_nav --full-sync --targets 000001,000002

同步入口职责:
    --all            日常增量（默认）；--all --full-sync 必须配合 --target-file 限定范围
    --job <name>     单 Job；逐标的回填型 Job（fund_nav / price_history 等）--full-sync 必须带 --targets / --target-file
    --full-sync      全量；仅限初始化 / 修复场景，且必须带范围，裸调用将被拒绝（#824 / #1776 ④）
    --targets        直接指定代码（逗号分隔），或
    --target-file    CSV 指定代码范围

任务说明:
    stock_list         - 刷新 A 股股票列表（全量，约 5000 只）
    fund_list          - 刷新公募基金列表（全量，约 27000 只）
    fund_detail_enrich - 补充基金的分类、公司、费率等信息（核心池，约 200 只）
    fund_nav           - 更新基金净值（增量，仅核心池）
    price_history      - 更新股票行情（增量，仅核心池）

    核心池 = 持仓标的 + 自选标的 + CSV文件指定标的
"""

import argparse
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

from app.core.database import get_db, init_db  # noqa: E402
from app.services.sync.orchestrator import DataSyncOrchestrator, require_full_sync_scope  # noqa: E402

# ✅ 在入口文件顶部加载 .env（相对于 backend/ 目录）
env_path = BACKEND_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# `--target-file` 时按 job 决定从 CSV 里取哪一类代码。
# ⚠️ 漏掉某个 job 的后果不是报错，而是 targets 保持 None → 静默跑成「0 只处理」。
FUND_TARGET_JOBS = ('fund_nav', 'fund_detail_enrich', 'fund_manager', 'fund_position')

# 受限目标池 job：**未给任何显式目标时，从库内核心池（持仓 + 自选）现取**。
#
# 为什么必须单独列：`targets=None` 在 `job_base.SyncJob.run()` 里的语义是
# 「子类自取全部数据」（第 195 行分支），而对这类 job 是「目标池为空 → 显式跳过」
# （`data-strategy.md` §4.3.3 红线）。`daily_scheduler` 走
# `spec.target_kind` + `resolve_targets()`，所以周任务正常；CLI 没有这条路，
# 于是 `pdm run sync --job fund_position` 会静默跑成「0 只、status=success」，
# 比报错更危险——手工回填的人会以为成了（2026-10-01 实测踩到）。
#
# ⚠️ 不要顺手把 fund_nav / fund_detail_enrich / fund_manager 一并放进这里：
# 它们的 `targets=None` 是「子类自取核心池」的既有语义，赋成显式列表会把执行
# 切成 `_execute_batches` 分批路径，属行为变更，需单独评估。
DB_POOL_JOBS = {'fund_position': 'fund'}


def ensure_fund_sync_fields(db_session):
    """
    确保 funds 表包含同步所需的三个字段：is_active、last_nav_check、nav_fail_count。

    这是一个幂等操作：如果字段已存在，不会重复添加或报错。
    在引入正式的数据库迁移工具（如 Alembic）之前，此函数作为运行时安全网。

    Args:
        db_session: SQLAlchemy Session 实例
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db_session.get_bind())
    existing_columns = {col['name'] for col in inspector.get_columns('funds')}

    # 需要添加的字段及其 SQL 定义
    required_columns = {
        'is_active': 'BOOLEAN DEFAULT TRUE',
        'last_nav_check': 'DATETIME',
        'nav_fail_count': 'INTEGER DEFAULT 0',
    }

    for col_name, col_def in required_columns.items():
        if col_name not in existing_columns:
            db_session.execute(text(f'ALTER TABLE funds ADD COLUMN {col_name} {col_def}'))
            logger.info(f'已添加字段 {col_name} 到 funds 表')

    db_session.commit()


def resolve_job_targets(
    orchestrator,
    job_name: str,
    targets_arg,
    target_file,
):
    """解析单 job（`--job`）的目标池，供 `main()` 与单测共用。

    优先级：`--targets` > `--target-file` > 库内核心池（仅 `DB_POOL_JOBS` 里的 job）。

    返回值语义：`None` = 「不限目标，交给子类自取」（`job_base.SyncJob.run()` 第 195 行
    分支）。**对 `DB_POOL_JOBS` 里的 job，`None` 是必须避免的取值**——那个分支对它
    等于「目标池为空 → 显式跳过」，会静默跑成 0 只，故对它一定会解析出列表
    （哪怕解析结果为空列表，也是「明确告知没目标」，而不是「忘了传」）。
    """
    if targets_arg:
        # 直接指定代码列表（逗号分隔）
        return [code.strip() for code in targets_arg.split(',') if code.strip()]

    if target_file:
        all_targets = orchestrator.resolve_targets(target_file=target_file)
        if job_name in FUND_TARGET_JOBS:
            return all_targets.get('fund', [])
        if job_name == 'price_history':
            return all_targets.get('stock', [])
        return None

    if job_name in DB_POOL_JOBS:
        return orchestrator.resolve_targets().get(DB_POOL_JOBS[job_name], [])

    return None


def main():
    parser = argparse.ArgumentParser(description='元数据同步工具')
    parser.add_argument('--all', action='store_true', help='同步所有数据')
    parser.add_argument('--job', type=str, help='单独同步某个 Job')
    parser.add_argument('--full-sync', action='store_true', help='全量同步（默认增量）')
    parser.add_argument('--target-file', type=str, help='通过CSV文件指定待同步的代码列表')
    parser.add_argument('--targets', type=str, help='直接指定基金/股票代码列表，逗号分隔')
    args = parser.parse_args()

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

                # 输出人类可读的摘要
                summary = format_summary(results, elapsed)
                print(summary)

                # 同时保留 JSON 日志供调试
                logger.debug(f'详细结果: {results}')
            elif args.job:
                targets = resolve_job_targets(orchestrator, args.job, args.targets, args.target_file)

                # 逐标的回填型 Job 走 --full-sync 必须带 --targets / --target-file（#824 / #1776 ④）
                try:
                    require_full_sync_scope(args.job, args.full_sync, bool(targets) or bool(args.target_file))
                except ValueError as e:
                    print(f'错误：{e}')
                    sys.exit(2)

                result = orchestrator.run_job(args.job, full_sync=args.full_sync, targets=targets)
                logger.info(f'任务 {args.job} 执行完成: {result}')
                # 打印逐数据源成功/失败明细（若有）
                detail = format_source_results(result)
                if detail:
                    print(detail)
        except KeyboardInterrupt:
            logger.warning('用户中断同步')
            sys.exit(130)
        except Exception as e:
            logger.error(f'同步失败: {e}')
            sys.exit(1)


def format_summary(results: dict, elapsed: float) -> str:
    """
    将同步结果字典格式化为人类可读的摘要文本。

    Args:
        results: Orchestrator.run_all_jobs() 返回的结果字典
        elapsed: 总耗时（秒）

    Returns:
        格式化的多行文本
    """
    lines = list()
    lines.append('=' * 60)
    lines.append('  多多贝 元数据同步报告')
    lines.append(f'  耗时: {elapsed:.1f}s')
    lines.append('=' * 60)

    # 汇总统计
    total_success = 0
    total_failed = 0
    total_new = 0
    total_skipped = 0

    # 任务名 → 中文描述映射
    job_labels = {
        'stock_list': 'A股股票列表',
        'fund_list': '公募基金列表',
        'fund_detail_enrich': '基金详情补充',
        'fund_manager': '基金经理信息',
        'fund_nav': '基金净值',
        'price_history': '股票行情',
    }

    for job_name, job_result in results.items():
        label = job_labels.get(job_name, job_name)
        status = job_result.get('status', 'unknown')

        if status == 'success':
            total_success += 1
            stats = job_result.get('stats', {})

            # 不同 Job 的统计字段名可能不同
            new_count = stats.get('success', stats.get('enriched', 0))
            skip_count = stats.get('skipped', stats.get('skipped_inactive', 0))
            total_count = stats.get('total', 0)
            error_count = len(stats.get('errors', []))

            total_new += new_count
            total_skipped += skip_count

            if total_count == 0 and new_count == 0:
                lines.append(f'\n  [成功] {label}: 无新数据')
            else:
                lines.append(f'\n  [成功] {label}:')
                if total_count:
                    lines.append(f'     - 检查了 {total_count} 个标的')
                if new_count:
                    lines.append(f'     - 新增 {new_count} 条记录')
                if skip_count:
                    lines.append(f'     - 跳过 {skip_count} 条（已存在或无数据）')
                if error_count:
                    lines.append(f'     - 有 {error_count} 个标的获取失败')

                # 逐数据源明细（如市场温度任务）
                src_detail = format_source_results(job_result)
                if src_detail:
                    lines.append(src_detail)

        elif status == 'failed':
            total_failed += 1
            error_msg = job_result.get('stats', {}).get('error', job_result.get('error', '未知错误'))
            lines.append(f'\n  [失败] {label}: 失败 — {error_msg}')

        elif status == 'manual_intervention':
            total_failed += 1
            error_msg = job_result.get('stats', {}).get('error', job_result.get('error', '未知'))
            lines.append(f'\n  [人工] {label}: 需人工介入 — {error_msg}')

        else:
            lines.append(f'\n  [未知] {label}: 状态未知 ({status})')

    # 汇总
    lines.append('\n' + '-' * 60)
    lines.append(f'  总结: {total_success} 个任务成功, {total_failed} 个失败')
    if total_new or total_skipped:
        lines.append(f'  数据变更: 新增 {total_new} 条, 跳过 {total_skipped} 条')
    lines.append('=' * 60)

    return '\n'.join(lines)


def format_source_results(result: dict) -> str:
    """
    将单个任务返回的逐数据源明细（stats.source_results）格式化为可读文本。

    仅当结果中包含 source_results 时返回非空字符串，否则返回 ''。
    """
    stats = result.get('stats', {})
    source_results = stats.get('source_results')
    if not source_results:
        return ''

    icon = {'success': '[成功]', 'failed': '[失败]', 'skipped': '[复用]'}
    lines = []
    lines.append('  ' + '-' * 46)
    lines.append('  数据源更新明细:')
    for r in source_results:
        mark = icon.get(r.get('status'), '[未知]')
        name = r.get('name') or r.get('source')
        source = r.get('source')
        if r.get('status') == 'failed':
            lines.append(f'    {mark} {name} ({source}): 失败 - {r.get("error")}')
        elif r.get('status') == 'skipped':
            val = r.get('value')
            val_str = f' = {val}' if val is not None else ''
            lines.append(f'    {mark} {name} ({source}): 复用今日数据{val_str}')
        else:
            val = r.get('value')
            val_str = f' = {val}' if val is not None else ''
            lines.append(f'    {mark} {name} ({source}): 成功{val_str}')

    s = sum(1 for r in source_results if r['status'] == 'success')
    k = sum(1 for r in source_results if r['status'] == 'skipped')
    f = sum(1 for r in source_results if r['status'] == 'failed')
    lines.append('  ' + '-' * 46)
    lines.append(f'  成功 {s} / 复用 {k} / 失败 {f}')
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
