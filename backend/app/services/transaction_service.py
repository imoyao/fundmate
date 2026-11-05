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

import csv
import io
from datetime import timedelta

from sqlalchemy import func, or_

from app.core.constants import DIVIDEND_TXN_TYPES
from app.core.money import Money
from app.core.time_utils import today_shanghai
from app.core.utils import iso_date_only, paginate
from app.domains.positions.models import Position
from app.domains.transactions.dates import (
    filter_by_effective_range,
)
from app.domains.transactions.dates import (
    order_by_effective_day as _order_by_effective_day,
)
from app.domains.transactions.models import Transaction
from app.services.symbol_scope import build_transaction_symbol_conditions
from app.services.trade_timeline import build_contribution_map
from app.services.txn_name_resolver import (
    POSITION_STATE_CLEARED,
    display_asset_name,
    resolve_transaction_asset_types,
    resolve_transaction_display_names,
    resolve_transaction_position_states,
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


def order_by_effective_day(query, *, descending: bool = True):
    """按**有效交易日**排序（``COALESCE(trade_date, confirm_date)``，并列用 ``id`` 兜底）。

    #2171 / #2712 起全站唯一的流水排序口径；#2914 起表达式本身收进
    :mod:`app.domains.transactions.dates`——**排序键必须与筛选键、展示值是同一个值**，
    否则「列表里看得见、按时间筛出来却看不见」这类自相矛盾永远查不完（此前筛选用的是
    裸 ``trade_date``，把只有确认日的行整批漏掉）。完整 WHY 见该模块 docstring。
    """
    return _order_by_effective_day(query, descending=descending)


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


def filters_from_args(args) -> dict:
    """从请求 query 解析筛选参数（列表与汇总**共用一份**字段名映射）。

    为什么抽出来：汇总条与列表必须跟随**同一组**筛选，否则「列表 3 条、汇总却按全量算」
    ——这类不一致不会报错，只会让用户拿着汇总条去核列表时永远差一截。字段名到后端
    参数的映射只写一处，加筛选项时两边同时生效。
    """
    return {
        'op_type': args.get('type'),
        'time_range': args.get('time_range'),
        'start_date': args.get('start_date'),
        'end_date': args.get('end_date'),
        'status': args.get('status'),
        'asset_type': args.get('asset_type'),
        'symbol': args.get('symbol'),
    }


def _filtered_transaction_query(db, family_id: int, filters: dict):
    """按筛选条件构造流水查询（列表 / 汇总 / 后续任何读路径共用同一套 WHERE）。"""
    query = db.query(Transaction).filter(Transaction.family_id == family_id)

    op_type = filters.get('op_type')
    if op_type:
        # 「分红」两个码并存（`dividend` 历史码 / `dividend_cash` 新码，真机实测 69 + 33 笔）。
        # 只筛一个码会让列表和汇总同时少掉一批现金分红，而两边少的是同一批——看起来
        # 完全自洽，就是和账对不上。
        if op_type == 'dividend':
            query = query.filter(Transaction.txn_type.in_(DIVIDEND_TXN_TYPES))
        else:
            query = query.filter(Transaction.txn_type == op_type)

    # 筛选：时间范围（#2914 修）
    # 此前用裸 `trade_date >= ?`：真实库 1,491/1,930 笔 `trade_date` 为 NULL（历史导入只填
    # 确认日），「近 30 天」实测漏 28/61 笔、「近 365 天」漏 660/916 笔——用户看着屏幕上
    # 有日期（`TransactionTable` 印的就是确认日），筛出来却没有。现改用与**排序同一把键**
    # （有效日），漏行与「排序键 ≠ 筛选键」两个问题一起消失。
    time_range = filters.get('time_range')
    _RANGE_DAYS = {'1m': 30, '3m': 90, '6m': 180, '1y': 365}
    if time_range in _RANGE_DAYS:
        query = filter_by_effective_range(query, start=today_shanghai() - timedelta(days=_RANGE_DAYS[time_range]))
    elif time_range == 'custom':
        query = filter_by_effective_range(query, start=filters.get('start_date'), end=filters.get('end_date'))

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
    # 匹配口径与持仓列表 #1966 / 持有年化 #1972 同源（`symbol_scope`）。
    # 原先走「两步法」：先按 symbol 取该产品持仓行、收集真实写法再对流水 IN —— 其前提
    # 「持仓与流水写法一致」并不成立（实测持仓 `001937`、流水 `SZ001937`），字面量 IN
    # 会显示「暂无交易记录」假阴性。现 `transactions.symbol_norm` 已具备，直接判定。
    symbol = filters.get('symbol')
    if symbol:
        query = query.filter(or_(*build_transaction_symbol_conditions(symbol)))

    return query


def build_transaction_list(db, family_id: int, page: int, per_page: int, filters: dict) -> dict:
    """交易流水列表：多维筛选 + 分页 + 行组装（#1642 B 块，从视图层下沉）。

    与下沉前逐字段一致：type→txn_type；time_range(1m/3m/6m/1y) 与 custom(start_date/end_date)
    都按**有效日**做 [start, end] 闭区间筛选（#2914 起口径在 `dates.filter_by_effective_range`）；
    status→status 等值过滤；asset_type
    经 positions 表关联（position_id.in_(...)）过滤。返回原 jsonify 的内层 data 字典
    （视图负责补 message）。筛选条件本身在 `_filtered_transaction_query`，与汇总条共用。
    """
    query = _filtered_transaction_query(db, family_id, filters)

    # 排序与分页：有效交易日倒序（口径与 WHY 全在 `order_by_effective_day`，三处共用）
    query = order_by_effective_day(query)
    items, total = paginate(query, page=page, per_page=per_page)

    # #2372：position_name/account_name 是冗余快照，漏写时按**真外键**回解析
    # （position_id→持仓名 / ledger_id→账户名，悬空 position_id 再按 symbol 兜底），
    # 不再把「快照没写」直接显示成「未知资产/未知账户」。
    pos_names, ledger_names = resolve_transaction_display_names(db, items)
    # #2712：asset_type 快照为空时回解析（价格列精度依赖它，详见 txn_name_resolver）
    asset_types = resolve_transaction_asset_types(db, items)
    # 持仓状态（已清仓 / 持有 / 资金流水）：判据要看 ownership_status 与「持仓行是否还在」，
    # 前端只有 position_id，猜不出来——故服务端下发，见 txn_name_resolver 的 WHY。
    position_states = resolve_transaction_position_states(db, items)

    results = [
        transaction_row(
            t,
            pos_names=pos_names,
            ledger_names=ledger_names,
            asset_types=asset_types,
            position_states=position_states,
        )
        for t in items
    ]
    # #2857：按 symbol 过滤时，把「当时成本 / 收益贡献」并进主表响应。
    # 只在按 symbol 过滤时重放——账本全量列表既不显示这两列，逐页重放等于白烧 CPU。
    # 传参用 `filters['symbol']` 而非去重后的 symbol，与 `_filtered_transaction_query`
    # 的匹配口径（symbol_scope）同源：重放与列表必须命中同一批流水，否则两列又会错位。
    symbol = filters.get('symbol')
    if symbol:
        figures = build_contribution_map(db, symbol=symbol, family_id=family_id)
        empty_figures = {'cost_after_yuan': None, 'profit_contribution_yuan': None}
        for row in results:
            row.update(figures.get(row['id'], empty_figures))

    return {'data': results, 'total': total, 'page': page, 'per_page': per_page}


def build_transaction_summary(db, family_id: int, filters: dict) -> dict:
    """汇总条数据（跟随筛选；口径见 docs/design/transaction-flow-redesign.md §四）。

    ## 公式（文档与实现必须逐字一致，前端不做二次求和）

       买入    = Σ amount WHERE type='buy'          （成交额，**不含**手续费）
       卖出    = Σ amount WHERE type='sell'
       分红    = Σ amount WHERE type ∈ {dividend, dividend_cash}
       手续费  = Σ fee（全类型）
       净投入  = 买入 + 手续费 − 卖出 − 分红

    **分红是两个码的合计**：历史导入写 `dividend`，新链路写 `dividend_cash`，真机库里
    并存（实测 69 + 33 笔）。只认一个码不会报错，只会让「分红」少一截、净投入多一截，
    而且列表和汇总少的是同一批——看起来自洽，就是和账对不上。见 `DIVIDEND_TXN_TYPES`。

    ## 为什么手续费不摊进买入

    摊进去后「买入金额」就不再等于成交额，用户拿汇总条去核表格的金额列会差一笔，
    而差在哪儿看不出来。四个数各自可核，比少一个数更重要。

    ## 为什么在这里一次 `GROUP BY`，而不是复用列表逐行累加

    列表是分页的（每页 20 条），拿它求和得到的是「这一页的汇总」——一个看起来很
    像总计、实际只覆盖 20 行的数字，这是最坏的一种错：不会报错，只会骗人。
    所以汇总走独立查询，且**全程用分做整数运算**，只在出口换算成元
    （浮点累加在几百行上就会出现 0.01 的漂移，而这是要印在屏幕上的钱）。

    Returns:
        ``{'buy': {'count', 'amount'}, 'sell': …, 'dividend': …, 'fee', 'net_invested'}``
        ——金额单位元、``fee`` / ``net_invested`` 为标量。``net_invested`` 保留符号
        （负数＝净取出），前端必须显示正负号。
    """
    rows = (
        _filtered_transaction_query(db, family_id, filters)
        .with_entities(
            Transaction.txn_type,
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.amount), 0),
            func.coalesce(func.sum(Transaction.fee), 0),
        )
        .group_by(Transaction.txn_type)
        .all()
    )

    cents_by_type = {}
    fee_cents = 0
    for txn_type, count, amount_cents, fee_sum_cents in rows:
        cents_by_type[txn_type] = (int(count), int(amount_cents or 0))
        fee_cents += int(fee_sum_cents or 0)

    def bucket(txn_type: str) -> dict:
        count, amount_cents = cents_by_type.get(txn_type, (0, 0))
        return {'count': count, 'amount': Money.cents_to_yuan(amount_cents)}

    # 分红按**两码合计**（`dividend` + `dividend_cash`）：真机库里两个码并存，只认一个
    # 会少掉一批现金分红——数字看着正常，只是和账对不上。口径见 `DIVIDEND_TXN_TYPES`。
    dividend_count = sum(cents_by_type.get(t, (0, 0))[0] for t in DIVIDEND_TXN_TYPES)
    dividend_cents = sum(cents_by_type.get(t, (0, 0))[1] for t in DIVIDEND_TXN_TYPES)

    buy_cents = cents_by_type.get('buy', (0, 0))[1]
    sell_cents = cents_by_type.get('sell', (0, 0))[1]

    return {
        'buy': bucket('buy'),
        'sell': bucket('sell'),
        'dividend': {'count': dividend_count, 'amount': Money.cents_to_yuan(dividend_cents)},
        'fee': Money.cents_to_yuan(fee_cents),
        'net_invested': Money.cents_to_yuan(buy_cents + fee_cents - sell_cents - dividend_cents),
    }


def transaction_row(
    t: Transaction,
    *,
    pos_names: dict,
    ledger_names: dict,
    asset_types: dict,
    position_states: dict,
) -> dict:
    """单条流水的**列表行**结构（列表与详情共用，避免两条路径各声明一套字段）。

    为什么抽函数：本仓已经因为「三条序列化路径各自拼字典」漏过一个字段（account 详情
    页永远显示「—」，见 position_presenter 的注释）。详情端点若再手抄一份，下次加字段
    就是同样的坑重演一次。

    这里只放**列表本身要用的字段**；费用拆分历史上已在列表里（#2137，有测试钉住
    「列表回显 fee_breakdown」），本次不动它——删一个已生效的键去换几百字节，
    收益抵不上契约风险。详情额外追加的是列表**确实没有**的那部分：导入溯源
    （import_hash / plan_id / updated_at）与持仓现状（position）。
    """
    return {
        'id': t.id,
        'ledger_id': t.ledger_id,
        'position_id': t.position_id,
        # #2844：收益类流水（券商原文不给标的）用「资产类型 + 收益种类」兜底，
        # 不再一律显示「未知资产」——判据与文案都在 display_asset_name 里，改一处即可。
        'position_name': display_asset_name(
            position_name=t.position_name or pos_names.get(t.id),
            asset_type=t.asset_type or asset_types.get(t.id),
            txn_type=t.txn_type,
        ),
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
        # 持仓状态：held（仍持有）/ cleared（已清仓，含持仓行已删的历史数据）/
        # account（资金流水，本来没有持仓行）。前端据此渲染胶囊，不再自行按
        # position_id === null 推断——那判据在 #2343「清仓不删行」之后已经失效。
        'position_state': position_states.get(t.id, POSITION_STATE_CLEARED),
        'created_at': t.created_at.isoformat() if t.created_at else None,
        # #2857：「当时成本 / 收益贡献」两列并入主表。
        # 默认 None = 「无口径」（拆分 / 扣税 / 其他不参与重放），前端据此渲染 `--`；
        # 只有 `build_transaction_list` 在按 symbol 过滤时用重放结果覆写这两个键。
        # 不要在这里给 0.0：`0` 是「这笔不产生已实现」（买入建仓），与「没有数据」
        # 是两件事，共用一个值就等于允许它们互相冒充。
        'cost_after_yuan': None,
        'profit_contribution_yuan': None,
    }


def build_transaction_detail(db, family_id: int, transaction_id: int):
    """单条流水详情（行展开详情按需取用，见 docs/design/transaction-flow-redesign.md §十二 第 4 条）。

    WHY 单独一个端点，而不是把字段全塞进列表：展开详情要的是「费用拆分 / 导入溯源 /
    持仓现状 / 备注全文」——这些都是**一次只看一行**的数据。塞进列表意味着 20 行各算
    一遍、响应体跟着涨，而其中绝大部分行永远不会被展开。

    返回 ``None`` 表示不存在或不属于本家庭，由视图转 404（不在这里 abort，服务层
    不依赖 HTTP 栈）。
    """
    t = db.query(Transaction).filter(Transaction.id == transaction_id, Transaction.family_id == family_id).first()
    if not t:
        return None

    pos_names, ledger_names = resolve_transaction_display_names(db, [t])
    asset_types = resolve_transaction_asset_types(db, [t])
    position_states = resolve_transaction_position_states(db, [t])

    row = transaction_row(
        t,
        pos_names=pos_names,
        ledger_names=ledger_names,
        asset_types=asset_types,
        position_states=position_states,
    )
    row.update(
        {
            # 以下键**列表里没有**，正是「展开才取」的理由：
            'import_hash': t.import_hash,
            'updated_at': t.updated_at.isoformat() if t.updated_at else None,
            # 定投计划来源（#2138）：用户要知道这笔记账是手工的还是计划自动产生的
            'plan_id': t.plan_id,
            # 持仓现状（份额 / 清仓时间）：展开一行的常见诉求是「这条卖出之后还剩多少」
            'position': _position_brief(db, t),
        }
    )
    return row


def _position_brief(db, t: Transaction):
    """详情里的持仓现状摘要；无 position_id 或持仓行已删时返回 None。

    与 ``position_state`` 配套：状态回答「是哪一态」，摘要回答「那现在这仓怎么样了」。
    用户展开一行的常见诉求就是「这条卖出之后我还剩多少」——列表给不了，这里给。
    """
    if not t.position_id:
        return None
    p = db.query(Position).filter(Position.id == t.position_id).first()
    if not p:
        # 悬空 position_id：历史删行。如实回 None，前端按 cleared 文案说明，不编造持仓。
        return None
    return {
        'id': p.id,
        'name': p.name,
        'symbol': p.symbol,
        'asset_type': p.asset_type,
        # 份额与流水同单位（万分之一份 → 份），与 quantity 列口径一致
        'quantity': Money.min_unit_to_shares(p.quantity),
        # 不返回 ownership_status：它与行级 `position_state` 是同一件事的两种写法，
        # 前端要是同时看到两个会不知道该用哪个（且第二个没有中文 label 下发）。
        # 清仓时间才是这里多出来的信息：「已清仓」之外还能答「什么时候清的」。
        'cleared_at': p.cleared_at.isoformat() if p.cleared_at else None,
    }


# CSV 导出列（与导入模板列对齐，导出的文件可直接再导入）
_EXPORT_HEADERS = (
    '交易日期',
    '确认日期',
    '资产类型',
    '代码',
    '名称',
    '业务类型',
    '账户',
    '数量',
    '价格',
    '手续费',
    '金额',
    '状态',
    '备注',
)


def _csv_day(value) -> str:
    """CSV 日期单元格：None 为空串（如实缺示，不兜底成别的日期）。

    只做格式归一（`date` / `datetime` 都出 `YYYY-MM-DD`），**不做** trade_date →
    confirm_date 的兜底——兜底是排序键的事（见 `order_by_effective_day`），
    单元格里替换日期会让用户以为原始交易日就是确认日。
    """
    if value is None:
        return ''
    return value.strftime('%Y-%m-%d')


def _csv_money(cents) -> str:
    """分 → 元的 CSV 友好格式化（沿用 Money 换算，空值输出 0）。"""
    return f'{Money.cents_to_yuan(cents or 0):.2f}'


def build_transactions_csv(db, family_id: int) -> str:
    """家庭全部交易流水的 CSV 文本（#2720 从 `transactions/views.py` 下沉）。

    视图只留「取会话 → 调本函数 → 包 Response」，取数/排序/逐行换算都在这里，
    可脱离 HTTP 栈单测。排序复用 `order_by_effective_day(descending=False)`：
    导出按时间正序读，且与列表页共用同一份「有效交易日」口径——两边各写一份
    `coalesce` 必然漂（#2720 初版即如此，且顺手把兜底写回 trade_date 单列）。
    """
    items = order_by_effective_day(
        db.query(Transaction).filter(Transaction.family_id == family_id),
        descending=False,
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_EXPORT_HEADERS)
    for t in items:
        writer.writerow(
            [
                _csv_day(t.trade_date),
                _csv_day(t.confirm_date),
                t.asset_type or '',
                t.symbol or '',
                t.position_name or '',
                t.txn_type or '',
                t.account_name or '',
                Money.min_unit_to_shares(t.quantity),
                f'{Money.price_units_to_yuan(t.price or 0):.2f}',
                _csv_money(t.fee),
                _csv_money(t.amount),
                t.status or '',
                t.notes or '',
            ]
        )
    return output.getvalue()
