# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/9 19:23
# File : models.py
"""
维度	status	新增字段
含义	交易是否成功执行	记录在系统中的处理阶段
现有值	success	无
未来新值	failed（执行失败）
processing（执行中）	orphan（孤立未关联）
pending（待确认，如基金 T+1）
confirmed（已确认）
关系	一条孤立的卖出记录，交易本身是成功的	但它关联不到持仓，需要标记处理阶段
"""

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import validates

from app.core.constants import POSITION_SOURCE_LABELS, PositionSource
from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class Transaction(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    __tablename__ = 'transactions'

    position_id = Column(Integer)
    symbol = Column(String(30), nullable=True, comment='资产代码快照')
    txn_type = Column('type', String(20))
    trade_date = Column(DateTime, comment='交易发起日(T日)，秒级')
    quantity = Column(Integer, default=0, comment='操作数量(0.0001份/单位)')
    price = Column(Integer, default=0, comment='成交价(0.0001元)')
    confirm_date = Column(Date, comment='确认日期')
    fee = Column(Integer, default=0, comment='手续费(分)')
    amount = Column(Integer, default=0, comment='交易总金额(分)')
    realized_pnl = Column(
        Integer,
        default=0,
        comment='该笔流水结转的已实现盈亏(分)：卖出/取出=(成交价−成本均价)×份额−手续费；现金分红=分红金额。'
        '记在流水而非持仓上，因清仓会删除持仓行、记在持仓上会随之丢失。'
        '汇总口径唯一出口见 services/pnl_service.py（#1183）',
    )
    status = Column(String(20), default='success')
    entry_status = Column(String(20), nullable=True)
    link_group_id = Column(String(36), nullable=True, comment='关联交易组ID')
    position_name = Column(String(100))
    asset_type = Column(String(20), nullable=True, default=None, comment='资产类型快照')
    # #863 收益行标记（D1 收益本金化）：渠道导入的收益发放类流水置 True。
    # 聚合纪律：收益行只在「收益桶」累计并计入总资产，禁止进入本金/孤儿净额口径。
    is_income = Column(Boolean, nullable=True, default=None, comment='收益发放行（#863），NULL=未标记')
    ledger_id = Column(
        Integer,
        ForeignKey('ledgers.id', ondelete='RESTRICT'),
        nullable=True,
        comment='关联账户ID (冗余account_name快照，此为真外键)',
    )
    account_name = Column(String(100))
    import_hash = Column(String(64), nullable=True, comment='导入去重哈希值')
    extra = Column(Text, nullable=True)  # 用来存 JSON 字符串
    notes = Column(Text)
    source = Column(
        String(30),
        nullable=True,
        comment='来源标识（#1232 决策 11）：复用 PositionSource，与 positions.source 共用一套枚举。'
        'NULL=历史数据未标记来源，不回填不改写（避免 import_hash 漂移破坏去重）；'
        '新记录按场景写入：manual/对账补录 reconciliation_adjustment/交易导入 broker source。',
    )

    @validates('source')
    def _validate_source(self, key, value):
        # 复用 PositionSource 校验，与 positions.source 同源约束；允许 None（存量未标记来源）。
        if value is None:
            return value
        if isinstance(value, PositionSource):
            return value.value
        if value not in POSITION_SOURCE_LABELS:
            raise ValueError(f'非法流水来源 source={value!r}，必须是 PositionSource 的合法值')
        return value

    __table_args__ = (
        # 防重复导入：去重作用域降为 ledger 级（#1020 / #1065）。
        # import_hash 已含 ledger_id，复合约束与代码语义对齐，并放行跨账本重导。
        # 关键修正：ledger_id 可能为 NULL（未归档持仓 / 探市迁移），而唯一约束中 NULL 互不冲突，
        # 导致 (NULL, import_hash) 无法去重 → 重导/重迁移会产生重复流水。
        # 改用函数式唯一索引 COALESCE(ledger_id, -1)：NULL 落到哨兵 -1 后参与去重，
        # 既让未归档/探市记录的幂等键生效，又兼容存量 NULL import_hash 行（第二列仍为 NULL → 元组不冲突）。
        Index(
            'uq_txn_import_hash',
            text('COALESCE(ledger_id, -1)'),
            'import_hash',
            unique=True,
        ),
        # 核心查询加速：按账户 + 日期排序
        Index('idx_txn_ledger_date', 'ledger_id', 'confirm_date'),
        # 其他常用查询
        Index('idx_txn_position_id', 'position_id'),
        Index('idx_txn_symbol', 'symbol'),
        Index('idx_txn_account_name', 'account_name'),
    )
