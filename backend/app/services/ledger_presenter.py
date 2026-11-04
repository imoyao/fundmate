# -*- coding: utf-8 -*-
"""账户（Ledger）的展示层序列化（唯一出口）。

为什么在 services 而不是 `domains/ledgers/views.py`（#1606 / #1173）：

- **守卫判据**：`scripts/check_view_thickness.py` 的判据是「业务规则请下沉
  `app/services/`，视图只做 HTTP 编排」。出参序列化（字段名、label 兜底、
  单位换算）属于**口径**，不是 HTTP 编排——留在视图里会让账户域视图随字段增长
  持续变厚，而这类变厚没有任何收益。
- **既有先例**：`services/position_presenter.py`（`enrich_position_dict`）已经把
  持仓侧的同类序列化下沉到 services，两侧视图各自 import。本模块与它同构。
- **成员归属字段（#1173）**：账户要带出「归属家庭成员」的 ID 与称谓。称谓映射
  由调用方**一次性查好**传入（`family_member_service.member_name_map`），
  本模块不做 ORM 查询——逐账户 join 会让账户域视图的 `orm_queries` 维度变差。

不变量：字段与数值口径与迁移前**逐字一致**（仅模块位置变化）。
"""

import json
from typing import Any, Optional

from app.core.constants import ALLOCATION_LABELS
from app.domains.ledgers.models import Ledger


def ledger_to_dict(
    ledger: Ledger,
    last_used_at: Optional[Any] = None,
    member_names: Optional[dict] = None,
) -> dict:
    """把 `Ledger` 序列化为接口返回字典（含 label 兜底与展示单位换算）。

    ``member_names``：成员 ID → 称谓的映射（services 层查好后传入）。
    """
    # 处理 fee_config：数据库中是字符串，需要反序列化
    fee_config = None
    if ledger.fee_config:
        try:
            fee_config = json.loads(ledger.fee_config)
        except (json.JSONDecodeError, TypeError):
            fee_config = None

    owner_member_id = ledger.owner_member_id
    owner_member_name = (member_names or {}).get(owner_member_id) if owner_member_id else None

    return {
        'id': ledger.id,
        'name': ledger.name,
        'ledger_type': ledger.ledger_type,
        'default_allocation': ledger.default_allocation,
        'default_allocation_label': ALLOCATION_LABELS.get(ledger.default_allocation, '未配置'),
        'fee_config': fee_config,
        'notes': ledger.notes,
        'portfolio_id': ledger.portfolio_id,
        'linked_cash_ledger_id': ledger.linked_cash_ledger_id,
        # 归属家庭成员（#1173）：null = 未归属/家庭共有
        'owner_member_id': owner_member_id,
        'owner_member_name': owner_member_name,
        # 类现金产品绑定（#1137）：绑定 funds 标的（余额宝概念）。
        # 入参用基金代码（前端搜索结果即 code），存储用 funds.id；出参附带 code/name 便于回显。
        'linked_money_fund_id': ledger.linked_money_fund_id,
        'linked_money_fund_code': ledger.linked_money_fund.fund_code if ledger.linked_money_fund else None,
        'linked_money_fund_name': ledger.linked_money_fund.name if ledger.linked_money_fund else None,
        'auto_purchase_money_fund': bool(ledger.auto_purchase_money_fund),
        # 关联的销售机构（AMAC 名录），可选；前端回显与编辑依赖该字段
        'sales_institution_id': ledger.sales_institution_id,
        # 聚合/系统账本标记与交易前端标签（#1101，前端展示/编辑用）
        'is_aggregation': ledger.is_aggregation,
        'frontend_app': ledger.frontend_app,
        'is_active': ledger.is_active,
        # 渠道分类（#1101 重设计，铁律见设计文档 §2.3）：用户可见分组/类型标签，只读本字段做展示。
        'channel_category': ledger.channel_category,
        # 外部资金账户/凭证标识（#1100/#1101，物理隔离维度，默认 MAIN；导入取真实资金账号）。
        'external_account_code': ledger.external_account_code,
        # 组内手动排序序号；null 表示用户尚未手动排序（前端回退按持仓金额降序）。
        'display_order': ledger.display_order,
        'created_at': ledger.created_at.isoformat() if ledger.created_at else None,
        'updated_at': ledger.updated_at.isoformat() if ledger.updated_at else None,
        # 最近使用时间：取该账户最后一笔交易的确认日期（无交易则为 null），
        # 用于导入向导步骤一下拉的"最近使用优先"排序。
        'last_used_at': last_used_at.isoformat() if last_used_at else None,
    }
