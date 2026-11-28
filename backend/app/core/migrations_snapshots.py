# -*- coding: utf-8 -*-
"""asset_snapshots 表结构迁移（组合维度，#D135）.

为什么单独成模块：``core/migrations.py`` 已 3000+ 行、被 ``scripts/guard_service_size.py``
冻结在基线，新增函数必然顶破行数闸门；本文件只服务 asset_snapshots 一张表的组合维度。

## 为什么必须重建唯一键，不能只加列

旧键 ``uq_asset_snapshots_scope`` = ``(family_id, COALESCE(ledger_id,-1), snapshot_date)``。
组合行与家庭行一样 ``ledger_id IS NULL`` ⇒ 两个**不同组合**的同日行在旧键下互相冲突：
先写的赢，后者 ``IntegrityError`` 让整个快照批次回滚。所以这条迁移的幂等判据是
**索引定义里有没有 ``portfolio_id``**，而不是「列在不在」——「有列、无新键」是必须
被识别成未完成的半截状态。

## 为什么组合行只含持仓市值

通用资产（房产 / 负债 / 现金）与孤儿货基流水只挂**账户**，没有组合归属（组合的归属
规则见 ``services/scope.py``：显式 ``positions.portfolio_id`` 覆盖账户继承）。故
``Σ组合 ≤ Σ账户 ≤ 家庭总资产``，差额是「不属于任何组合的东西」，不是漏算。

## 方言

加列一律走 ``migrations._add_columns_if_missing``（PG 用 ``ADD COLUMN IF NOT EXISTS``）；
索引 ``DROP INDEX IF EXISTS`` / ``CREATE UNIQUE INDEX`` 两种引擎通用，表达式索引
（``COALESCE``）两侧都支持，故不写方言分支（#2534：不允许「非 SQLite 就跳过」）。
"""

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.migrations import _add_columns_if_missing, _is_postgres, _table_exists

#: 唯一键名字必须与模型 ``__table_args__`` 完全一致（同名才可查、可幂等判断）
SNAPSHOT_SCOPE_INDEX = 'uq_asset_snapshots_scope'


def _index_definition(engine: Engine, index_name: str) -> str:
    """读索引定义文本（SQLite 走 sqlite_master、PG 走 pg_indexes）；取不到返回空串。"""
    sql = (
        f"SELECT indexdef FROM pg_indexes WHERE indexname = '{index_name}'"
        if _is_postgres(engine)
        else f"SELECT sql FROM sqlite_master WHERE type = 'index' AND name = '{index_name}'"
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(text(sql)).first()
    except Exception:  # noqa: BLE001 —— 读不到定义不等于结构正确：交给调用方重建
        return ''
    return str(row[0] or '') if row else ''


def migrate_asset_snapshots_portfolio_scope(engine: Engine) -> str:
    """``asset_snapshots`` 长出组合维度：加 ``portfolio_id`` 列 + 重建唯一键（D135）。

    组合行与家庭 / 账户行同表（与 #1181 同理由：两套口径必然分叉，D1 反复强调），
    靠 ``portfolio_id`` 是否为 NULL 区分；组合行 ``total_liabilities`` 恒 0。
    """
    if not _table_exists(engine, 'asset_snapshots'):
        return '[SKIP] asset_snapshots 表不存在（空库，create_all 将按新模型建表）'
    added = _add_columns_if_missing(engine, 'asset_snapshots', [('portfolio_id', 'INTEGER')])
    if 'portfolio_id' in _index_definition(engine, SNAPSHOT_SCOPE_INDEX):
        return f'[SKIP] 唯一键已含组合维度（本次新增列：{added or "无"}）'

    with engine.begin() as conn:
        # DROP + CREATE 同一事务：中途失败整段回滚，不留「无唯一键」的窗口
        conn.execute(text(f'DROP INDEX IF EXISTS {SNAPSHOT_SCOPE_INDEX}'))
        conn.execute(
            text(
                f'CREATE UNIQUE INDEX {SNAPSHOT_SCOPE_INDEX} ON asset_snapshots '
                '(family_id, COALESCE(ledger_id, -1), COALESCE(portfolio_id, -1), snapshot_date)'
            )
        )
        conn.execute(
            text(
                'CREATE INDEX IF NOT EXISTS idx_asset_snapshots_portfolio_date '
                'ON asset_snapshots (portfolio_id, snapshot_date)'
            )
        )

    # 收尾自校验：定义里必须真的出现 portfolio_id（DDL 被静默忽略时不让它蒙混过关）。
    # 读不到定义（权限 / 方言差异）不硬失败——代价是下次启动再建一次，而不是拒绝启动。
    after = _index_definition(engine, SNAPSHOT_SCOPE_INDEX)
    if after and 'portfolio_id' not in after:
        raise RuntimeError(f'{SNAPSHOT_SCOPE_INDEX} 重建后仍不含 portfolio_id（{after!r}），迁移失败')
    logger.info(f'[OK] D135 asset_snapshots 长出组合维度（新增列：{added or "无"}）')
    return f'[OK] asset_snapshots.portfolio_id={added or "已存在"}，唯一键已含组合维度'
