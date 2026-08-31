# -*- coding: utf-8 -*-
"""统一对账框架三表模型（#1232 §8.1 / P1）。

- discrepancies：活跃差异（按业务键 upsert，非按 run 重建，is_permanent 逃生舱挂行）。
- reconciliation_runs：对账运行记录（历史与摘要，幂等可重跑）。
- adjustment_logs：审计日志（仅用户主动操作；系统自动行为不写，§5.5）。

三表均含 family_id → user 域，须在 db_factory.DATA_DOMAIN_REGISTRY 登记。
"""

from sqlalchemy import Boolean, Column, Date, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class ReconciliationDiscrepancy(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """活跃对账差异（按业务键 upsert，非按 run 重建）。

    差异是持续状态（没解决就一直存在）；is_permanent 永久忽略挂在本行，
    否则下期 run 重建会丢失（设计文档 §8.1）。
    """

    __tablename__ = 'discrepancies'

    domain = Column(String(2), nullable=False, comment='对账域: A|B|C')
    ledger_id = Column(Integer, nullable=True, comment='账户ID')
    symbol = Column(String(30), nullable=False, comment='资产代码')
    discrepancy_type = Column(String(20), nullable=False, comment='差异类型: quantity|cost|cash|orphan')
    expected_value = Column(Integer, nullable=True, comment='理论值（分/最小单位，按类型口径）')
    actual_value = Column(Integer, nullable=True, comment='实际值')
    diff = Column(Integer, nullable=True, comment='差值 = expected - actual')
    status = Column(String(20), default='pending', comment='pending|cleared|ignored')
    is_permanent = Column(Boolean, default=False, comment='永久忽略逃生舱')
    ignored_reason = Column(Text, nullable=True, comment='忽略原因')
    ignored_at = Column(DateTime, nullable=True, comment='忽略时间')
    ignored_by = Column(Integer, nullable=True, comment='操作用户ID')
    last_run_id = Column(Integer, nullable=True, comment='最近一次 run ID')
    first_detected_at = Column(DateTime, nullable=True, comment='首次发现时间')

    __table_args__ = (
        # 业务键唯一：同一域+账户+标的+差异类型只保留一条活跃记录（upsert 定位）
        UniqueConstraint(
            'family_id',
            'domain',
            'ledger_id',
            'symbol',
            'discrepancy_type',
            name='uq_discrepancies_business_key',
        ),
        # 查询加速：按域 + 状态筛
        Index('idx_discrepancies_family_status', 'family_id', 'status'),
        Index('idx_discrepancies_domain', 'family_id', 'domain'),
    )


class ReconciliationRun(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """对账运行记录（历史与摘要，幂等可重跑）。"""

    __tablename__ = 'reconciliation_runs'

    domain = Column(String(2), nullable=False, comment='对账域: A|B|C')
    data_date = Column(Date, nullable=True, comment='数据日期（快照/导入日）')
    started_at = Column(DateTime, nullable=True, comment='开始时间')
    finished_at = Column(DateTime, nullable=True, comment='结束时间')
    triggered_by = Column(
        String(20),
        nullable=True,
        comment='manual|import|schedule；import 含「导入完成后自动触发」（域C）；'
        'schedule 为未来扩展保留，当前未实现（项目无队列基础设施）',
    )
    summary_json = Column(Text, nullable=True, comment='pending/cleared/ignored 计数')

    __table_args__ = (
        Index('idx_runs_family_domain', 'family_id', 'domain'),
        Index('idx_runs_started_at', 'family_id', 'started_at'),
    )


class AdjustmentLog(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """审计日志（仅用户主动操作，§5.5）。

    action 语义：ignore_temporary / ignore_permanent / supplement / adjust / cover。
    """

    __tablename__ = 'adjustment_logs'

    run_id = Column(Integer, nullable=True, comment='关联 run ID')
    discrepancy_id = Column(Integer, nullable=True, comment='关联差异 ID')
    action = Column(String(30), nullable=False, comment='ignore_temporary|ignore_permanent|supplement|adjust|cover')
    before_json = Column(Text, nullable=True, comment='操作前快照(JSON)')
    after_json = Column(Text, nullable=True, comment='操作后快照(JSON)')
    reason = Column(Text, nullable=True, comment='用户填写的操作原因')
    operator = Column(Integer, nullable=True, comment='操作用户ID')

    __table_args__ = (
        Index('idx_adjustment_logs_family', 'family_id', 'created_at'),
        Index('idx_adjustment_logs_disc', 'discrepancy_id'),
    )
