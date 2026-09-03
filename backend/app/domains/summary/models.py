# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/10 21:00
# File : models.py
"""资产快照模型：每日记录家庭总资产/负债/净资产，支撑同比计算（历史积累期）。"""

from sqlalchemy import Column, Date, Index, Integer, text

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class AssetSnapshot(Base, PrimaryKeyMixin, TimestampMixin):
    """家庭 / 账户每日资产快照（#1181）。

    与 D1 家庭共享层一致按 `family_id`（而非 user_id）隔离；金额一律整数分（×100）。

    两级快照共存于同一张表，靠 `ledger_id` 是否为 NULL 区分：

    - `ledger_id IS NULL`：**家庭级**快照（既有行为，支撑总资产走势）
    - `ledger_id = N`：**账户级**快照（本卡新增，支撑账户维度走势）

    WHY 不新建一张账户快照表：账户走势与盈亏序列最终要在同一调度器、同一时间轴取数，
    拆成两张表必然出现「某日某账户的账面值」两套口径分叉（D1 反复强调要杜绝的），
    且 #1183 的盈亏时间序列（#1220）要复用本表基建。

    幂等 upsert 作用域 `(family_id, COALESCE(ledger_id, -1), snapshot_date)`：
    NULL 在唯一约束中互不冲突，故用 COALESCE 落哨兵 -1，让家庭级行也参与去重
    （与 `transactions.uq_txn_import_hash` 同范式）。
    """

    __tablename__ = 'asset_snapshots'
    __table_args__ = (
        Index(
            'uq_asset_snapshots_scope',
            'family_id',
            text('COALESCE(ledger_id, -1)'),
            'snapshot_date',
            unique=True,
        ),
        Index('idx_asset_snapshots_ledger_date', 'ledger_id', 'snapshot_date'),
    )

    family_id = Column(Integer, default=1, index=True, comment='归属家庭 ID（家庭共享层隔离键）')
    ledger_id = Column(
        Integer,
        nullable=True,
        comment='账户ID；NULL=家庭级快照，非 NULL=该账户的账户级快照（#1181）。'
        '刻意不加外键：账户被删除时不应被历史快照阻断（与 transactions.position_id 同处理）',
    )
    snapshot_date = Column(Date, nullable=False, comment='快照日期（上海时区本地日期）')
    total_assets = Column(Integer, nullable=False, comment='总资产（分）')
    total_liabilities = Column(Integer, nullable=False, comment='总负债（分）')
    net_worth = Column(Integer, nullable=False, comment='净资产（分）')
    # #1220：盈亏时间序列（整数分），与 pnl_service 口径一致，复用同一张表
    # （家庭级 ledger_id IS NULL 与账户级 ledger_id=N 同行，杜绝口径分叉）。
    realized_pnl_cents = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text('0'),
        comment='已实现盈亏（分）：卖出结转+现金分红，以流水为事实源',
    )
    unrealized_pnl_cents = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text('0'),
        comment='未实现盈亏（分）：市值−成本基数',
    )
    total_pnl_cents = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text('0'),
        comment='总盈亏（分）=已实现+未实现，与 XIRR 现金流口径一致',
    )
    # #863 P1-5（D1）：当日货基收益（分），展示用途——快照随每日调度一并落库，
    # 供「货基收益走势/日历」查询。该列**不**参与 total_assets（自动收益仅展示，
    # 总资产含的是渠道 is_income 收益桶；本列是本地按万份收益计算的预估收益）。
    # NULL=该作用域（家庭/账户）当日无货基本金表达，不写 0 以免覆盖语义混淆。
    money_fund_income_cents = Column(
        Integer,
        nullable=True,
        default=None,
        comment='当日货基收益（分，#863 P1-5 展示用，不入 total_assets；NULL=无货基）',
    )
