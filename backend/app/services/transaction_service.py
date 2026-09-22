# -*- coding: utf-8 -*-
"""交易流水域的查询 / 展示行组装服务（#1642 B 块，从 views 下沉，承 #1606）。

WHY 下沉
    `list_transactions` 长在视图里（76 行）：多维筛选（操作类型 / 时间范围 / 状态 / 资产类型）
    + 分页 + 逐行金额换算组装，属纯读组装，却只能挂在 HTTP 栈下测。本模块收口，视图只做
    入参解析 + 调服务 + 组响应信封。

边界
    - 不碰 ``g`` / ``request``：family_id 与筛选参数由调用方显式传入，可脱离请求上下文单测；
    - 只读组装：不写库、不提交事务；
    - 对外 API 契约零变更（``conventions.md`` §2.4）：返回字段名、嵌套结构与下沉前逐字一致。
"""

from datetime import date, timedelta

from app.core.money import Money
from app.core.utils import paginate
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction


def build_transaction_list(db, family_id: int, page: int, per_page: int, filters: dict) -> dict:
    """交易流水列表：多维筛选 + 分页 + 行组装（#1642 B 块，从视图层下沉）。

    与下沉前逐字段一致：type→txn_type；time_range(1m/3m/6m/1y) 按 trade_date 阈值过滤，
    custom 用 start_date/end_date 做 [start, end] 边界；status→status 等值过滤；asset_type
    经 positions 表关联（position_id.in_(...)）过滤。返回原 jsonify 的内层 data 字典
    （视图负责补 message）。
    """
    query = db.query(Transaction).filter(Transaction.family_id == family_id)

    op_type = filters.get('op_type')
    if op_type:
        query = query.filter(Transaction.txn_type == op_type)

    # 筛选：时间范围
    time_range = filters.get('time_range')
    if time_range == '1m':
        query = query.filter(Transaction.trade_date >= date.today() - timedelta(days=30))
    elif time_range == '3m':
        query = query.filter(Transaction.trade_date >= date.today() - timedelta(days=90))
    elif time_range == '6m':
        query = query.filter(Transaction.trade_date >= date.today() - timedelta(days=180))
    elif time_range == '1y':
        query = query.filter(Transaction.trade_date >= date.today() - timedelta(days=365))
    elif time_range == 'custom':
        start = filters.get('start_date')
        end = filters.get('end_date')
        if start:
            query = query.filter(Transaction.trade_date >= start)
        if end:
            query = query.filter(Transaction.trade_date <= end)

    # 筛选：交易状态
    status = filters.get('status')
    if status:
        query = query.filter(Transaction.status == status)

    # 筛选：资产类型（通过 positions 表关联）
    asset_type = filters.get('asset_type')
    if asset_type:
        position_ids = (
            db.query(Position.id).filter(Position.asset_type == asset_type, Position.family_id == family_id).all()
        )
        pids = [p.id for p in position_ids]
        query = query.filter(Transaction.position_id.in_(pids))

    # 排序与分页
    query = query.order_by(Transaction.created_at.desc())
    items, total = paginate(query, page=page, per_page=per_page)

    results = []
    for t in items:
        results.append(
            {
                'id': t.id,
                'ledger_id': t.ledger_id,
                'position_id': t.position_id,
                'position_name': t.position_name or '未知资产',
                'type': t.txn_type,
                'asset_type': t.asset_type,
                'trade_date': t.trade_date.strftime('%Y-%m-%d') if t.trade_date else None,
                'confirm_date': t.confirm_date.strftime('%Y-%m-%d') if t.confirm_date else None,
                'quantity': Money.min_unit_to_shares(t.quantity),
                'price': Money.price_units_to_yuan(t.price),
                'fee': Money.cents_to_yuan(t.fee),
                'amount': Money.cents_to_yuan(t.amount),
                'status': t.status,
                'account_name': t.account_name or '未知账户',
                'notes': t.notes,
                'source': t.source,
                'created_at': t.created_at.isoformat() if t.created_at else None,
            }
        )

    return {'data': results, 'total': total, 'page': page, 'per_page': per_page}
