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

from sqlalchemy import String, cast, func

from app.core.money import Money
from app.core.utils import iso_date_only, paginate
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.symbol_scope import collect_transaction_symbol_variants, query_positions_by_symbol
from app.services.txn_name_resolver import (
    resolve_transaction_asset_types,
    resolve_transaction_display_names,
)

# #2137 费用拆分：Transaction 列名 → 输出键（元）
_FEE_BREAKDOWN_FIELDS = (
    ('commission', 'commission'),
    ('stamp_duty', 'stamp_duty'),
    ('transfer_fee', 'transfer_fee'),
    ('other_fee', 'other_fee'),
)


def fee_breakdown_yuan(txn: Transaction):
    """流水费用拆分明细（#2137，分 → 元）；未拆分（四列全 NULL）返回 None。

    与模型不变量同口径：要么四列齐全、要么全空，不存在「拆了一半」的行。
    """
    values = [getattr(txn, col) for col, _key in _FEE_BREAKDOWN_FIELDS]
    if any(v is None for v in values):
        return None
    return {key: Money.cents_to_yuan(v) for (_col, key), v in zip(_FEE_BREAKDOWN_FIELDS, values)}


def transaction_edit_payload(txn: Transaction) -> dict:
    """交易编辑接口的响应 data（#2137 起含 fee_breakdown）。

    组装从 `ledgers/views.py` 下沉至此（该视图文件被 `check_view_thickness.py`
    冻结「只减不增」）：Money 反算 + 日期归一属展示组装，放 services 可脱离
    HTTP 栈单测，也让编辑响应与列表响应共用同一套拆分口径。
    """
    from datetime import datetime as _dt

    def _ymd(value):
        # trade_date 为 DateTime 列（读回为 datetime），confirm_date 为 Date 列（date）；
        # 若本次仅赋过 .date() 则为 date。统一输出 YYYY-MM-DD。
        if not value:
            return None
        if isinstance(value, _dt):
            value = value.date()
        return value.isoformat()

    return {
        'id': txn.id,
        'quantity': Money.min_unit_to_shares(txn.quantity),
        'price': Money.price_units_to_yuan(txn.price),
        'amount': Money.cents_to_yuan(txn.amount),
        'fee': Money.cents_to_yuan(txn.fee),
        # #2137 费用拆分明细（元）：未拆分为 None，前端按 fee 单值展示
        'fee_breakdown': fee_breakdown_yuan(txn),
        'trade_date': _ymd(txn.trade_date),
        'confirm_date': _ymd(txn.confirm_date),
        'notes': txn.notes,
        'import_hash': txn.import_hash,
    }


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

    # 筛选：产品代码（产品详情页「交易记录」区块，#2104）。
    # 复用 `symbol_scope` 的「同一产品」口径（与持仓列表 #1966 / 持有年化 #1972 一致）：
    # `transactions.symbol` 是字面量快照、无 norm 列，故先按 symbol 取该产品持仓行、
    # 收集真实写法再做 `IN`（数据策略硬约束 §3 应用层两步法），`SZ000001` 与
    # `000001.SZ`、`SZ159915` 与 `159915` 视为同一只产品——字面量等值会让详情页
    # URL 写法与流水快照写法不一致时显示「暂无交易记录」假阴性。
    symbol = filters.get('symbol')
    if symbol:
        positions = query_positions_by_symbol(db, symbol, family_id)
        variants = collect_transaction_symbol_variants(symbol, positions)
        query = query.filter(Transaction.symbol.in_(variants))

    # 排序与分页 —— 按**交易日期倒序**（#2171 反馈修正）
    #
    # 旧口径是 `created_at.desc()`，而 `created_at` 是**写入时间**不是交易时间：批量导入的
    # 历史流水会让整张表退化成「导入批次顺序」。真机实测 `SZ000638` 的 24 笔排出来是
    # `2023-02-03 → 2023-02-15 → 2023-02-07 → 2023-03-16 → 2023-03-13 → 2023-03-20`（乱序，
    # 因同一批 created_at 挤在毫秒内、并列区间顺序未定义），用户在详情页看到的正是它。
    #
    # 口径与展示层同源（`components/TransactionTable` 的 `formatDate`：交易日优先、确认日兜底）
    # ——排序键必须与屏幕上印的那个日期一致，否则「看起来乱序」永远说不清是谁的错。
    # 真机 1,921 笔里有 1,211 笔 `trade_date` 为空（历史导入只填了确认日），只按 trade_date
    # 排会把它们整批沉底，而屏上显示的却是确认日。
    #
    # `id` 兜底不是装饰：同一天的多笔必须有**确定**的相对顺序，否则翻页会在并列区间内
    # 重复或漏行（批量导入的行 created_at 常精确到同一微秒）。
    # 两个日期列类型不同（trade_date 是 DateTime / confirm_date 是 Date），合并前都要转文本：
    # **不能转 DateTime** —— SQLite 对 `CAST('2025-06-20' AS DATETIME)` 走 NUMERIC 亲和性，
    # 把日期当成「以年份开头的数字」（→ 2025.0），而数字在 SQLite 里恒排于文本之前，
    # 于是「只有确认日」的行会被整批甩到最前（开发实测踩到）。
    # 转成文本后两边都是 ISO 形式（`YYYY-MM-DD[ HH:MM:SS]`），字典序即时间序，跨 SQLite /
    # Postgres 行为一致（`CAST(x AS VARCHAR)` 两边都合法）。
    effective_day = func.coalesce(
        cast(Transaction.trade_date, String),
        cast(Transaction.confirm_date, String),
    )
    query = query.order_by(effective_day.desc(), Transaction.id.desc())
    items, total = paginate(query, page=page, per_page=per_page)

    # #2372：position_name/account_name 是冗余快照，漏写时按**真外键**回解析
    # （position_id→持仓名 / ledger_id→账户名，悬空 position_id 再按 symbol 兜底），
    # 不再把「快照没写」直接显示成「未知资产/未知账户」。
    pos_names, ledger_names = resolve_transaction_display_names(db, items)
    # #2712：asset_type 快照为空时回解析（价格列精度依赖它，详见 txn_name_resolver）
    asset_types = resolve_transaction_asset_types(db, items)

    results = []
    for t in items:
        results.append(
            {
                'id': t.id,
                'ledger_id': t.ledger_id,
                'position_id': t.position_id,
                'position_name': t.position_name or pos_names.get(t.id) or '未知资产',
                'type': t.txn_type,
                'asset_type': t.asset_type or asset_types.get(t.id),
                'symbol': t.symbol,
                'trade_date': iso_date_only(t.trade_date),
                'confirm_date': iso_date_only(t.confirm_date),
                'quantity': Money.min_unit_to_shares(t.quantity),
                'price': Money.price_units_to_yuan(t.price),
                'fee': Money.cents_to_yuan(t.fee),
                # #2137 费用拆分：四列齐全才给明细（元），未拆分为 None——
                # 前端 None 时按聚合 fee 单值展示，与存量行为一致。
                'fee_breakdown': fee_breakdown_yuan(t),
                'amount': Money.cents_to_yuan(t.amount),
                'status': t.status,
                'account_name': t.account_name or ledger_names.get(t.id) or '未知账户',
                'notes': t.notes,
                'source': t.source,
                'created_at': t.created_at.isoformat() if t.created_at else None,
            }
        )

    return {'data': results, 'total': total, 'page': page, 'per_page': per_page}
