# -*- coding: utf-8 -*-
"""站内通知表模型。

数据准入四问（AGENTS.md「数据策略」要求留痕）：
  1. 谁在用？—— 前端 `lay-notice` 消息盒（layout/components/lay-notice）与首页未读提示条
     （views/welcome/components/WelcomeGreeting.vue），二者此前均为前端假数据/恒 false。
  2. 什么场景用？—— 用户打开任意页面时看铃铛红点；策略/自选规则触发后点开消息盒查看。
  3. 缺了会怎样？—— 提醒无处落地，策略引擎算出的信号只能「当场看一眼」，不构成闭环，
     也谈不上纪律。无降级替代（前端写死假数据是现状，不是降级方案）。
  4. 成本多大？—— 每家庭每天最多「触发规则数 × 单标的 1 条」，dedup_key 唯一约束天然封顶；
     全部本地计算，无外部请求。

去重的实现选择：用 (family_id, dedup_key) **唯一约束**而不是「先查再插」——
生产双库 + 可能的并发扫描下，先查再插存在竞态；唯一约束是数据库层保证，
配合 `emit` 里的 IntegrityError 兜底，语义为「同键一天只留一条」。
"""

from sqlalchemy import Boolean, Column, DateTime, Index, String, UniqueConstraint

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class Notification(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """站内通知（家庭级）。

    家庭级而非用户级：本产品账本以家庭共享（family_id 为隔离键），
    提醒描述的是「这个组合发生了什么」，一人已读即视为家庭已读，
    避免多成员重复提醒——这本身就是「宁可漏报，不可滥报」的一部分。
    """

    __tablename__ = 'notifications'

    level = Column(
        String(4),
        nullable=False,
        default='P1',
        comment='P0 强（首页横栏 + 消息盒）/ P1 中（消息盒）/ P2 弱（消息盒周级）',
    )
    category = Column(
        String(20),
        nullable=False,
        default='system',
        comment='strategy 策略 / watchlist 自选 / system 系统',
    )
    title = Column(String(120), nullable=False, comment='消息标题（客观陈述，不含投资建议措辞）')
    body = Column(String(500), nullable=True, comment='消息正文（客观陈述）')
    dedup_key = Column(
        String(120),
        nullable=False,
        comment='去重键：来源类型 + 业务键 + 日期，如 allocation:000300:2026-10-16',
    )
    source_type = Column(
        String(30),
        nullable=False,
        comment='产生来源：allocation_deviation（配比偏离）/ trend_signal（趋势）等',
    )
    source_key = Column(String(80), nullable=True, comment='来源业务键（多为标的代码）')
    is_read = Column(Boolean, nullable=False, default=False, comment='是否已读')
    read_at = Column(DateTime, nullable=True, comment='已读时间')

    __table_args__ = (
        UniqueConstraint('family_id', 'dedup_key', name='uq_notification_family_dedup'),
        Index('idx_notification_family_read', 'family_id', 'is_read'),
    )
