# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : models.py
"""资金容器/账户模型"""

# -*- coding: utf-8 -*-
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

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
            '类型(内部资产类键,用户不可见): stock(股票账户) / fund(基金账户) '
            '/ e_account(基金E账户汇总,由E账户导入自动创建) / property(实物资产) '
            '/ bank(现金账户) / family(家庭账户)。'
            '权威说明见 docs/working-notes/ledger-channel-category-redesign-2026-08-28.md §2.1/§2.3：'
            '本字段只进计算/费率/视图分支逻辑，不出现在用户面；账户列表分组、类型标签、排序、筛选'
            '一律只读 channel_category，绝不读本字段当展示。ledger_type 由系统维护/派生'
            '(创建时据 channel_category 或销售机构 org_type 推导)，编辑带数据账户时不可变(改类型返回409)。'
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
    # 类现金产品绑定（#1137）：账户的「余额宝」，指向基金标的（funds.id）。
    # 绑定标的而非持仓——持仓卖光会悬空；回款是否自动申购见 auto_purchase_money_fund。
    linked_money_fund_id = Column(
        Integer,
        ForeignKey('funds.id', ondelete='SET NULL'),
        nullable=True,
        comment='账户绑定的类现金产品（余额宝），指向 funds.id（仅 stock/fund 类型可用）',
    )
    # 自动申购开关（#1137）：默认关闭——用户不操作系统不代劳，回款留在账户现金。
    auto_purchase_money_fund = Column(
        Boolean,
        nullable=False,
        default=False,
        comment='卖出/赎回回款是否自动申购绑定的类现金产品（默认关闭）',
    )
    # 回显用：绑定产品的代码与名称（只读，不参与写入）
    linked_money_fund = relationship('Fund', foreign_keys=[linked_money_fund_id], lazy='selectin')
    sales_institution_id = Column(
        Integer,
        ForeignKey('sales_institutions.id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的基金销售机构（AMAC 权威名录，可选自选字段；用户创建账户时自选，不选为 NULL）',
    )

    # 聚合/系统账本标记（#1101）：True=聚合视图类账本（如基金E账户），从用户账户列表默认隐藏。
    # 用于替代在列表查询里硬编码 ledger_type='e_account'，前向兼容未来聚合账本。
    is_aggregation = Column(
        Boolean,
        nullable=False,
        default=False,
        comment='是否聚合/系统账本（True=从账户列表隐藏，如基金E账户）',
    )

    # 交易前端（聚合前端）标签（#1101）：用户通过哪个前端软件查看该账户（同花顺/东方财富/券商APP）。
    # 仅展示用途，不参与任何资产计算或业务逻辑。
    frontend_app = Column(
        String(20),
        nullable=True,
        default=None,
        comment='交易前端标签(展示用): tonghuashun/eastmoney/self/other，不参与计算',
    )

    # ── 渠道分类（#1101 后续重设计，权威说明见 docs/working-notes/ledger-channel-category-redesign-2026-08-28.md）──
    # 与 ledger_type 正交，维护者务必分清（铁律见该文档 §2.3）：
    #   - ledger_type：内部资产类键（stock/fund/bank/property…），只进计算/费率/视图分支，用户不可见，不当展示标签。
    #   - channel_category：用户可见的"机构渠道类别"（bank/securities/fund_platform/insurance/futures/other），
    #     同时作为账户列表分组与账户类型标签。分组/标签/排序/筛选只读本字段，绝不读 ledger_type 当展示。
    # 本字段完全由系统维护：建账/导入时由 sales_institution_id→org_type 映射写入；手动账本由用户选的"分组"推导写入，用户从不直接编辑。
    channel_category = Column(
        String(20),
        nullable=True,
        default=None,
        comment='渠道分类(用户可见分组/类型标签): bank/securities/fund_platform/insurance/futures/other；系统维护，不参与计算',
    )
