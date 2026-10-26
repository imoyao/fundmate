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

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    text,
)
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
    # ── #2137 费用拆分列（分）──
    # 与聚合 fee 的关系：fee 仍是唯一权威总额（已实现盈亏结转、卖出回款净额都读它），
    # 四列是「总额从哪来」的结构化明细。四列全为 NULL = 未拆分，是存量数据与
    # 未提供拆分的写入路径（现金/分红/转换等 fee=0 场景）的默认态；
    # 一旦拆分，四列必须齐全（缺的类别显式传 0），且其和必须等于 fee——
    # 该不变量由文件末尾的 mapper 事件 fail closed 保证，写入路径无需自觉。
    commission = Column(Integer, nullable=True, comment='佣金(分，#2137 拆分列；NULL=未拆分)')
    stamp_duty = Column(Integer, nullable=True, comment='印花税(分，#2137 拆分列；NULL=未拆分)')
    transfer_fee = Column(Integer, nullable=True, comment='过户费等税费(分，#2137 拆分列；NULL=未拆分)')
    other_fee = Column(Integer, nullable=True, comment='其他费用(分，#2137 拆分列；NULL=未拆分)')
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
    # #2138 定投计划关联：哪几笔 buy 由某个计划产生。
    # 只用「计划 → 流水」单向弱引用（不建 FK）：计划可被删除/停用，历史流水必须保留；
    # 立 FK 会让删计划连带卡住流水，而 ON DELETE SET NULL 又要改 PG 侧约束。
    plan_id = Column(Integer, nullable=True, index=True, comment='来源定投计划ID（#2138，NULL=非定投）')
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


# #2137 费用拆分列名（与上方四个 Column 一一对应，供事件与读取端共用）
FEE_BREAKDOWN_COLUMNS = ('commission', 'stamp_duty', 'transfer_fee', 'other_fee')


@event.listens_for(Transaction, 'before_insert')
@event.listens_for(Transaction, 'before_update')
def _validate_transaction_fee_breakdown(mapper, connection, target: 'Transaction') -> None:
    """费用拆分不变量（#2137）：要么四列全 NULL（未拆分），要么四列齐全且和=fee。

    为什么挂 mapper 事件而不是靠各写入路径自觉传对：本仓写流水的入口有近十处
    （买入/卖出/孤儿/现金/分红/转换/导入……），「拆分和=总额」这种跨字段约束
    漏任何一处都会静默落出错数（费用汇总对不上、用户以为漏记一笔佣金）。
    事件挂在模型上，写入路径无论怎么绕都会经过，与
    ``positions`` 的 ``symbol_norm`` / ``account_name`` 回填同法。

    全 NULL 不校验：存量数据与现金/分红/转换等 fee=0 场景没有拆分事实，
    强行要求四列反而是逼写入方编 0。
    """
    parts = [getattr(target, col) for col in FEE_BREAKDOWN_COLUMNS]
    if all(p is None for p in parts):
        return
    if any(p is None for p in parts):
        missing = [c for c, p in zip(FEE_BREAKDOWN_COLUMNS, parts) if p is None]
        raise ValueError(f'费用拆分必须四列齐全（缺的类别显式传 0）：未提供 {missing}')
    total = sum(parts)
    if total != (target.fee or 0):
        raise ValueError(f'费用拆分之和({total})与聚合 fee({target.fee or 0})不一致（#2137）')
