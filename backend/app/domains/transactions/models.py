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

from loguru import logger
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
from app.core.symbol_utils import symbol_identity


class Transaction(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    __tablename__ = 'transactions'

    position_id = Column(Integer)
    symbol = Column(String(30), nullable=True, comment='资产代码快照')
    # ── 归一身份键（#1662 遗留：positions 做了，流水表当时被漏掉）──
    # symbol 是**快照原貌**（场内带前缀 / 场外裸码，见 core/venues），symbol_norm 是**身份**形态：
    # `EXCHANGE:SZ159915` / `OTC:004369` / `NO_VENUE:MGR_xxx`（构造见 core/symbol_utils.symbol_identity）。
    #
    # 为什么流水层也必须要有它：`SZ001937` 与 `001937` 是同一只场外基金，但字面量不同 ——
    # 读侧 `Transaction.symbol == position.symbol` 是**字面量等值**，两种写法互不命中，
    # 于是同一标的的流水在按 symbol 聚合的路径上被拆成两半（本机实测 16 条漏算）。
    #
    # 与 positions.symbol_norm 的关键差异：**流水不加唯一约束**。同一标的天然有多笔交易，
    # 唯一化会把第二笔买入打回。故本列只作「身份查询键」，幂等去重仍归 `uq_txn_import_hash`。
    #
    # 由 `_fill_transaction_symbol_norm` 在落库前自动填充，不依赖 14 处写入路径各自传参。
    symbol_norm = Column(
        String(64),
        nullable=False,
        default='',
        comment='#1662 归一身份键 {VENUE}:{规范形态代码}(EXCHANGE:SZ159915/OTC:004369)，读侧按它匹配',
    )
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


@event.listens_for(Transaction, 'before_insert')
@event.listens_for(Transaction, 'before_update')
def _fill_transaction_symbol_norm(mapper, connection, target: 'Transaction') -> None:
    """落库前把 `symbol_norm` 算出来（#1662 遗留项，与 `_fill_position_symbol_norm` 同法）。

    ## 为什么需要

    同一只场外基金在库里有两个字面量：持仓存裸码 `001937`（OTC 约定），流水存
    `SZ001937`（历史误加交易所前缀）。读侧按 `Transaction.symbol == position.symbol`
    做**字面量等值**，两种写法互不命中 —— 本机实测 16 条流水在按 symbol 聚合的路径上
    被漏掉（`resolved` 见 `docs/`）。`symbol_norm` 给两侧一个共同的身份键。

    ## 为什么挂在 mapper 事件

    本仓写流水的入口有十四处（`trading.TransactionService.create` 被 6 个 service 调用、
    导入提交 4 处、`position_service` 8 处……）。`TransactionService.create` 只是
    `Transaction(**kwargs)` 的透传，**不做任何归一**；靠各调用方自觉传 `symbol_norm`
    必然漏，而漏掉的那条路径不会报错，只会在读侧静默少算。事件挂在模型上绕不过。

    ## 为什么不在这里猜 venue

    `symbol_identity` 在 `asset_type` 缺失时返回 `NO_VENUE:{字面量}`（不猜市场 —— 见
    `core/venues` 的 `000651` 双重身份教训）。流水里 `asset_type` 有存量 NULL，
    补它是**迁移**的职责（按基金名录 + `position_name` 快照回填），不是本事件的职责：
    事件只做纯函数计算，保证「symbol / asset_type 一定，身份一定」。
    写侧因此有义务传准 `asset_type`——它本来就是 `Transaction` 的既有字段。

    计算是纯函数，`before_update` 重算幂等；`symbol` 为空的现金流水返回空串。

    ## 为什么 asset_type 为空要出声

    `symbol_identity` 在 `asset_type` 为空时只能返回 `NO_VENUE:{字面量}` —— 这是**已知降级**，
    靠它撑住不猜的底线。但降级行与同标的的正常行（`OTC:…` / `EXCHANGE:…`）身份不等，
    会让读侧跨表匹配再次落空，正是本卡要消灭的形态。故此处显性告警：
    存量由迁移回填，新增则当场暴露「谁漏传了 asset_type」，不静默。
    """
    target.symbol_norm = symbol_identity(target.symbol, target.asset_type)
    if target.symbol and not target.asset_type:
        logger.warning(
            f'流水缺少 asset_type（symbol={target.symbol!r}），symbol_norm 退化为 '
            f'{target.symbol_norm!r}，跨表身份匹配将失效；请补齐写入方传参'
        )
