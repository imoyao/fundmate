# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : models.py
"""资金容器/账户模型"""

# -*- coding: utf-8 -*-
from sqlalchemy import Column, ForeignKey, Integer, String, Text

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class Ledger(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """
    fee_config JSON 结构示例
    股票账户 (ledger_type='stock')
    {
      "commission": {
        "rate": 0.00025,
        "min": null,
        "comment": "佣金费率万2.5，min为null表示免5"
      },
      "stamp_duty": {
        "rate": 0.005,
        "scope": "sell_only",
        "comment": "印花税，仅卖出收取"
      },
      "transfer_fee": {
        "rate": 0.0001,
        "scope": "both",
        "comment": "过户费，双边收取"
      },
      "bond_commission": {
        "rate": 0.0001,
        "min": null,
        "comment": "可转债专用佣金"
      }
    }

    基金账户 (ledger_type='fund')
    {
      "subscription_discount": 0.1,
      "comment": "申购费打1折。0.1=1折，0.01=0.1折，0=免申购费"
    }
    """

    __tablename__ = 'ledgers'

    name = Column(String(100), nullable=False, comment='账户名称，如"华泰证券"')
    ledger_type = Column(
        String(20),
        default='bank',
        comment='类型: stock(股票账户) / fund(基金账户) / property(实物资产) / bank(现金账户) / family(家庭账户)',
    )
    default_allocation = Column(
        String(20),
        default='longterm',
        comment='默认五笔钱配置目标: liquid / stable / longterm / speculative / security',
    )
    fee_config = Column(
        Text,
        nullable=True,
        comment='费率配置，JSON格式。stock账户记录佣金/印花税等；fund账户记录subscription_discount（申购费折扣）',
    )
    notes = Column(Text, comment='备注')
    portfolio_id = Column(
        Integer,
        ForeignKey('portfolios.id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的投资组合（删除组合时自动解绑）',
    )
    linked_cash_ledger_id = Column(
        Integer,
        ForeignKey('ledgers.id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的现金账户（仅 stock/fund 类型可用）',
    )
