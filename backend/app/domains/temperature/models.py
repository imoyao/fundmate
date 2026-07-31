# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/22 22:55
# File : models.py
# backend/app/domains/temperature/models.py
"""
市场温度数据模型

三表设计：
  - market_single_values：单值指标（永久保存）
  - market_composites：复合指标（保留 1 年）
  - market_multi_items：多维列表（保留 1 年）

符合 SPEC §2.7 全局命名规范（带领域前缀）
"""

from sqlalchemy import JSON, Boolean, Column, Date, Index, String, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin
from app.core.db_utils import SafeNumeric


class MarketSingleValue(Base, PrimaryKeyMixin, TimestampMixin):
    """
    单值指标表（永久保存）

    适用数据源：
      - eastmoney_volume: 全市场成交额
      - qieman: 且慢市场温度
      - youzhiyouxing: 有知有行全市场温度
      - jiucaishuo_fear: 韭圈儿恐惧贪婪指数
      - jiucaishuo_medium: 韭圈儿中长期温度
      - jisilu_cb: 集思录可转债温度
    """

    __tablename__ = 'market_single_values'

    source = Column(String(30), nullable=False, index=True, comment='数据源标识')
    name = Column(String(50), nullable=False, comment='指标名称')
    value = Column(SafeNumeric(16, 4), nullable=True, comment='数值')
    label = Column(String(30), nullable=True, comment='文字标签（数据源原始标签）')
    unit = Column(String(10), nullable=True, comment='单位：%/亿/无')
    collected_at = Column(Date, nullable=False, index=True, comment='数据日期')
    stale = Column(Boolean, default=False, comment='是否失效')

    __table_args__ = (
        UniqueConstraint('source', 'name', 'collected_at', name='uq_single_source_name_date'),
        Index('idx_single_collected', 'collected_at', 'source'),
    )

    def __repr__(self):
        return f'<MarketSingleValue {self.source}.{self.name}: {self.value}>'


class MarketComposite(Base, PrimaryKeyMixin, TimestampMixin):
    """
    复合指标表（保留最近 1 年）

    适用数据源：
      - jisilu_indicator: 集思录估值指标（中位PB/PE、温度等）
      - self_calc: 自算估值分位（沪深300 PE + 股债利差）
      - er_niao: 二鸟说手抄报
    """

    __tablename__ = 'market_composites'

    source = Column(String(30), nullable=False, index=True, comment='数据源标识')
    collected_at = Column(Date, nullable=False, index=True, comment='数据日期')
    data = Column(JSON, nullable=False, comment='完整原始数据（JSON）')
    stale = Column(Boolean, default=False, comment='是否失效')

    __table_args__ = (
        UniqueConstraint('source', 'collected_at', name='uq_composite_source_date'),
        Index('idx_composite_collected', 'collected_at', 'source'),
    )

    def __repr__(self):
        return f'<MarketComposite {self.source} @ {self.collected_at}>'


class MarketMultiItem(Base, PrimaryKeyMixin, TimestampMixin):
    """
    多维列表数据表（保留最近 1 年）

    适用数据源：
      - bias: 乖离度（多行业/多品种）
      - industry_crowding: 行业拥挤度（31行业）
      - sector_flow: 板块资金流（多行业/概念）
    """

    __tablename__ = 'market_multi_items'  # ✅ 统一为 market_ 前缀

    source = Column(String(30), nullable=False, index=True, comment='数据源标识')
    item_type = Column(String(30), nullable=False, comment='品种类型：index/industry/etf/fund/concept')
    item_code = Column(String(20), nullable=False, comment='品种代码')
    item_name = Column(String(50), nullable=False, comment='品种名称')
    data = Column(JSON, nullable=False, comment='该品种的完整数据')
    collected_at = Column(Date, nullable=False, index=True, comment='数据日期')
    stale = Column(Boolean, default=False, comment='是否失效')

    __table_args__ = (
        UniqueConstraint('source', 'item_type', 'item_code', 'collected_at', name='uq_multi_source_type_code_date'),
        Index('idx_multi_collected', 'collected_at', 'source'),
        Index('idx_multi_type', 'source', 'item_type'),
    )

    def __repr__(self):
        return f'<MarketMultiItem {self.source}.{self.item_type}:{self.item_code} @ {self.collected_at}>'
