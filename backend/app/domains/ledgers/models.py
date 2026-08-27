# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : models.py
"""资金容器/账户模型"""

# -*- coding: utf-8 -*-
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text

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
        comment=(
            '类型: stock(股票账户) / fund(基金账户) / e_account(基金E账户汇总,由E账户导入自动创建) '
            '/ property(实物资产) / bank(现金账户) / family(家庭账户)'
        ),
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

    # 归档状态：True=活跃（参与日常视图/默认出现在账户列表），False=已归档
    # （保留全部交易/持仓/流水数据，仅从日常视图默认隐藏；数据仍参与收益计算）。
    # 默认活跃，与 is_archived 反向语义相比更贴合「绝大多数账户活跃」的现实。
    # 有交易/持仓/资产的账户禁止删除，只能归档（见 views.delete_ledger 守卫）。
    is_active = Column(Boolean, nullable=False, default=True, comment='是否活跃（False=已归档）')

    # 组内手动排序序号：同一 ledger_type 内有序。NULL 表示尚未手动排序，
    # 前端回退按持仓金额降序（#1083）。拖拽落库时对该类型全部账户赋 1..N。
    display_order = Column(
        Integer,
        nullable=True,
        default=None,
        comment='组内手动排序序号（null=按持仓金额降序默认排序）；同类型内有序',
    )

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
    sales_institution_id = Column(
        Integer,
        ForeignKey('sales_institutions.id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的基金销售机构（AMAC 权威名录，可选自选字段；用户创建账户时自选，不选为 NULL）',
    )
