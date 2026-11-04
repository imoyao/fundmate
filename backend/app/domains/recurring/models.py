# -*- coding: utf-8 -*-
"""定投计划模型（#2138）。

一张表只回答三件事：**投什么、每期投多少、什么时候投**。

与流水的关联靠 ``transactions.plan_id``（迁移见
``core.migrations.migrate_transaction_plan_id``）——计划表**不落**执行状态：
「下次扣款日 / 累计投入 / 是否逾期」全部按需从计划 + 流水派生
（``services/recurring_service.py``），避免第二份事实源与流水对不上。

归属：家庭共享层的账本数据 → ``FamilyScopedMixin``（``family_id``），
登记在 ``db_factory.DATA_DOMAIN_REGISTRY`` 的 user 域。
"""

from sqlalchemy import CheckConstraint, Column, Date, ForeignKey, Index, Integer, String, Text

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin

#: 定投频率词表。前端下拉与后端校验共用一份，新增值必须同时改 CheckConstraint。
RECURRING_FREQUENCIES = ('weekly', 'biweekly', 'monthly')

#: 计划状态。paused = 用户手动暂停（不推进下次扣款日）；ended = 已结束（终态，可再启用）。
RECURRING_STATUSES = ('active', 'paused', 'ended')


class RecurringPlan(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """定投计划（#2138）。"""

    __tablename__ = 'recurring_plans'

    ledger_id = Column(
        Integer,
        ForeignKey('ledgers.id', ondelete='RESTRICT'),
        nullable=True,
        comment='关联账户ID（真外键，ledgers 同属 user 域，无跨库 FK）',
    )
    account_name = Column(String(100), nullable=True, comment='账户名称快照（账户改名不断链）')
    symbol = Column(String(30), nullable=False, comment='标的代码')
    position_name = Column(String(100), nullable=True, comment='标的名称快照')
    asset_type = Column(String(20), nullable=True, comment='资产类型快照')
    amount = Column(Integer, nullable=False, comment='每期投入金额(分)，与 transactions.amount 同口径')
    frequency = Column(String(20), nullable=False, default='monthly', comment='频率：weekly/biweekly/monthly')
    day_of_period = Column(
        Integer,
        nullable=True,
        comment='每月第几日(1~28) 或 每周第几日(1=周一)；NULL=沿用 start_date 的日',
    )
    start_date = Column(Date, nullable=False, comment='首次扣款日')
    end_date = Column(Date, nullable=True, comment='结束日期（NULL=长期有效）')
    status = Column(String(20), nullable=False, default='active', comment='active/paused/ended')
    note = Column(Text, nullable=True, comment='备注')

    __table_args__ = (
        CheckConstraint(
            "frequency in ('weekly', 'biweekly', 'monthly')",
            name='ck_recurring_plans_frequency',
        ),
        CheckConstraint(
            "status in ('active', 'paused', 'ended')",
            name='ck_recurring_plans_status',
        ),
        CheckConstraint('amount > 0', name='ck_recurring_plans_amount_positive'),
        # 列表页默认按 family + status 过滤，逾期/在投是高频查询形态。
        Index('ix_recurring_plans_family_status', 'family_id', 'status'),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试可读性
        return f'<RecurringPlan id={self.id} {self.symbol} {self.frequency} {self.status}>'
