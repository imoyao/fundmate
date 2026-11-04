# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 21:46
# File : position_display.py

"""
持仓「读 / 展示」簇（issue #2873 安全首抽第一步）。

本模块承载 ``position_service.py`` 中**只读 / 展示**相关的纯函数，以及
``PositionService.build_position_list`` 的实现体 ``build_position_list_impl``。
所有**写命令**与**写侧私有 helper** 仍留在 ``position_service.py``，本模块
**严禁从 ``position_service`` 反向 import**，以免形成循环依赖。

行为保证：本文件内的函数与 ``position_service.py`` 原实现逐字一致，仅做物理搬迁，
不改动任何逻辑、签名或返回值；``position_service`` 通过 re-export 保 facade。
"""

from typing import Optional

from sqlalchemy import false, func, or_
from sqlalchemy.orm import Session

from app.core.constants import ALLOCATION_LABELS, MARKET_LABELS, TYPE_LABELS
from app.core.money import Money
from app.core.utils import iso_date_only, paginate
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.family_member_service import ledger_ids_for_member
from app.services.position_presenter import enrich_position_dict
from app.services.position_scope import active_holdings
from app.services.symbol_scope import (
    build_position_symbol_conditions,
    build_transaction_symbol_conditions,
)
from app.services.transaction_service import order_by_effective_day


def query_transactions_by_identity(db: Session, position: Position):
    """按**身份键**构造流水查询（#2372）：``(ledger_id, symbol)``，未归档持仓只匹配未归档流水。

    ## 为什么不是 ``(symbol, account_name)``

    ``account_name`` 是 ``ledgers.name`` 的**可编辑快照**——账户改名后，改名前落库的
    流水与新名字天然对不上；真库还存在重名账户（支付宝×2 / 天天基金×2），按名称过滤会
    把**另一个账户**的交易一并卷进来。持仓明细页的兜底查询因此必须按 ``ledger_id`` 收敛。

    ``ledger_id`` 为 NULL（未归档持仓 / 探市迁移行）时，只匹配同属未归档的流水——
    宁可少查，也不拿名字去猜（猜错的表现是明细里混入别人账户的交易，且不会报错）。

    ## 为什么放在 service 而不是视图层

    视图层的判据是「只做 HTTP 编排」（``decisions.md`` 2026-09-19），且
    ``scripts/check_view_thickness.py`` 会按行数拦截视图层变厚。同一段兜底过滤在
    ``get_position_transactions`` 与 ``delete_position`` 两处都需要，下沉后一处定义、两处复用。
    """
    # 匹配口径走 symbol_scope（#1662 遗留项）：此前是字面量 `Transaction.symbol == position.symbol`，
    # 而流水快照与持仓写法可以不同（实测流水 `SZ001937`、持仓 `001937`），字面量等值会漏掉整批流水。
    query = db.query(Transaction).filter(or_(*build_transaction_symbol_conditions(position.symbol)))
    if position.ledger_id is not None:
        return query.filter(Transaction.ledger_id == position.ledger_id)
    return query.filter(Transaction.ledger_id.is_(None))


def list_position_transactions(db: Session, position: Position) -> list[Transaction]:
    """某持仓的交易流水（持仓抽屉数据源）。

    取数口径：#2372 的「优先 ``position_id``、悬空时按身份键兜底」保持不变；
    排序统一走 ``order_by_effective_day``（#2712）——此前这里是
    ``confirm_date DESC NULLS LAST, created_at DESC``，只有交易日的行被甩到末尾，
    批量导入又退化成「导入批次顺序」（#2171），与详情页顺序对不上。
    """
    if position.id:
        rows = db.query(Transaction).filter(Transaction.position_id == position.id).first()
        if rows is not None:
            return order_by_effective_day(db.query(Transaction).filter(Transaction.position_id == position.id)).all()
    return order_by_effective_day(query_transactions_by_identity(db, position)).all()


def serialize_position_transaction(txn: Transaction, position: Optional[Position] = None) -> dict:
    """持仓抽屉的流水行（唯一出口，#2712）。

    与 ``/api/transactions`` 同口径：

    - 日期给**两个真字段**（``trade_date`` / ``confirm_date``），由前端按「交易日优先、
      确认日兜底」展示。此前这里把 ``confirm_date or trade_date`` 塞进 ``trade_date``：
      字段名与语义错位，同一笔流水在抽屉与详情页可以显示不同天。
    - ``asset_type`` 在流水快照为空时用持仓自身类型兜底：前端价格列按
      ``pricePrecision(asset_type)`` 取位数（基金 4 位 / 其余 2 位），缺失会把
      净值 ``1.2200`` 印成 ``1.22``。
    """
    return {
        'id': txn.id,
        'ledger_id': txn.ledger_id,
        'symbol': txn.symbol,
        'trade_date': iso_date_only(txn.trade_date),
        'confirm_date': iso_date_only(txn.confirm_date),
        'txn_type': txn.txn_type,
        'asset_type': txn.asset_type or (position.asset_type if position else None),
        'quantity': Money.min_unit_to_shares(txn.quantity),
        'price': Money.price_units_to_yuan(txn.price),
        'amount': Money.cents_to_yuan(txn.amount),
        'fee': Money.cents_to_yuan(txn.fee),
        'notes': txn.notes,
    }


def resolve_portfolio_change(
    db: Session,
    update_data: dict,
    family_id: int,
) -> Optional[str]:
    """校验持仓改派的目标组合存在且归属本家庭（禁止跨家庭串仓）。

    返回 ``None`` 表示通过；返回字符串是**给调用方 abort(404) 的文案**（HTTP 语义留在
    视图层，本方法不 import flask）。

    与 `resolve_ledger_change` 同一形态、同一个理由：这类「目标资源存在性 + 归属」
    校验是业务规则，留在视图里会让每个新增的可改派字段都往 views 里再加一段 query
    （#1606 视图层职责边界；本文件 positions/views.py 早已在冻结基线内，只减不增）。
    `portfolio_id` 未传 / 显式置空（解除关联）均直接放行，不查库。
    """
    portfolio_id = update_data.get('portfolio_id')
    if portfolio_id is None:
        return None
    target = db.query(Portfolio).filter(Portfolio.id == portfolio_id, Portfolio.family_id == family_id).first()
    if not target:
        return '目标组合不存在或无权访问'
    return None


def resolve_ledger_change(
    db: Session,
    position: Position,
    update_data: dict,
    family_id: int,
) -> Optional[str]:
    """处理持仓的 `ledger_id` 变更：校验目标账户存在，并同步 `account_name` 快照。

    返回 ``None`` 表示通过；返回字符串是**给调用方 abort(404) 的文案**（HTTP 语义留在
    视图层，本方法不 import flask）。原地修改 ``update_data`` 补上快照字段。

    ## 为什么两件事必须一起做

    只校验不同步 ⇒ 归档 / 迁移后留下「外键指向新账户、展示名还是旧账户」的漂移行，
    账户改名时 `sync_account_name_snapshots` 按 `ledger_id` 级联刷新，把用户刚迁走的
    持仓显示名**刷回旧账户**——一次「迁移」在界面上被静默还原（#2372 症状 3 同构）。
    只同步不校验 ⇒ 允许绑定一个不存在的幽灵账本，外键失去意义。

    幂等：`ledger_id` 未变化（含未传）时直接返回，不写任何字段。
    """
    new_id = update_data.get('ledger_id')
    if new_id is None or new_id == position.ledger_id:
        return None
    ledger = db.query(Ledger).filter_by(id=new_id, family_id=family_id).first()
    if not ledger:
        return '目标账户不存在'
    update_data['account_name'] = ledger.name
    return None


def build_position_list_impl(
    db,
    family_id: int,
    group_by: str,
    page: int,
    per_page: int,
    ledger_id_raw: str,
    symbol: str = '',
    market: str = '',
    member_id_raw: str = '',
) -> dict:
    """list_positions 的核心：过滤 + 按账户分组 / 分页组装（#1642 B 块，从 views 下沉）。

    与下沉前逐字段一致：``ledger_id='null'`` 仅取未归档持仓；``group_by='account'`` 按
    **ledger_id** 分组（#2372：可编辑的 account_name 不做分组键；None 归 'unfiled'）并补
    首次买入确认日（优先交易流水，回退 position.confirm_date）；否则分页
    + enrich_position_dict。返回原 jsonify 的「内层 data 字典」（视图负责补 message）。

    ``symbol`` / ``market``（#1966）：产品维度过滤，供详情页「我的持仓」区块用。
    **下推到 SQL**——取全表后内存筛违反数据策略硬约束 §6。

    ``member_id``（#1173）：按家庭成员筛选。持仓**经账户间接归属**
    （``Position.ledger_id → Ledger.owner_member_id``），不在持仓表冗余成员列——
    冗余列要跟着导入/转换/清仓等所有写路径双写，一处漏了就出「同一笔持仓在两个
    成员名下」的矛盾账。过滤同样**下推 SQL**（``ledger_id IN (子查询)``）。
    注意：未绑定账户的持仓（``ledger_id IS NULL``）不属于任何成员，不会被命中。

    ``ownership_status``：只要 ``active``。``shadow`` 是 E账户导入写下的**对账镜像行**
    （``ledger_id`` 恒为 NULL、``account_name`` 恒为「基金E账户」），它表示「E账户说有这笔、
    系统还没认领」，不是用户持有的账户，也不是可买卖的账户。放进这里会以「基金E账户」
    的名义凭空多出一组持仓：本地库实测 021180 因此显示两个渠道（基金E账户 3,421.96 份 +
    微众银行 3,421.9622 份），市值翻倍。镜像行的归宿只有对账工作台
    （``get_reconciliation``），那边直接查 ``ownership_status='shadow'``，不依赖本接口。
    """
    query = db.query(Position).filter(Position.family_id == family_id)
    # 只要真实持仓：同时排掉 `cleared`（已清仓，行保留作锚点）与 `shadow`
    # （E账户对账镜像行）。见 services/position_scope.py。
    query = active_holdings(query)
    # 未归档过滤：ledger_id 显式传 'null' 时仅返回未绑定账户的持仓
    if ledger_id_raw == 'null':
        query = query.filter(Position.ledger_id.is_(None))
    elif ledger_id_raw:
        query = query.filter(Position.ledger_id == int(ledger_id_raw))
    if member_id_raw:
        # 成员 → 账户 → 持仓：下推过滤，避免取全表后内存筛。
        # 账户集合口径收口在 `family_member_service.ledger_ids_for_member`
        # （与汇总/盈亏拿同一份集合，见 #1173 单一出口纪律）。
        member_ledger_ids = ledger_ids_for_member(db, family_id, int(member_id_raw))
        if not member_ledger_ids:
            # 该成员名下没有账户 → 结果必为空；直接给恒假条件，
            # 不用 `IN ()`（各方言行为不一致，PG 会直接语法错）
            query = query.filter(false())
        else:
            query = query.filter(Position.ledger_id.in_(member_ledger_ids))
    if symbol:
        # symbol 同时匹配「展示形态」与 #1662 的「归一身份键」，取并集：存量行
        # symbol_norm 可能为空、只有新写入行保证有值，只用其一都会漏命中。
        # 判定收口在 `services/symbol_scope.py`（三种 venue 归一候选的详细理由见其模块注释），
        # 与产品级 XIRR（#1972 `scope=symbol`）**共用同一份口径**——两边各写一份，
        # 迟早漂移成「列表里有三行、年化只算了两行」的自相矛盾详情页。
        query = query.filter(or_(*build_position_symbol_conditions(symbol)))
    if market:
        query = query.filter(Position.market == market)
    query = query.order_by(Position.updated_at.desc())

    if group_by == 'account':
        positions = query.all()
        result: dict = {}

        # 一次性查询所有持仓的首次买入确认日（性能优化）
        pos_ids = [p.id for p in positions]
        first_buy_dates: dict = {}
        if pos_ids:
            buy_dates_query = (
                db.query(Transaction.position_id, func.min(Transaction.confirm_date).label('confirm_date'))
                .filter(
                    Transaction.position_id.in_(pos_ids),
                    Transaction.txn_type.in_(['buy', 'deposit']),
                )
                .group_by(Transaction.position_id)
                .all()
            )
            first_buy_dates = {row.position_id: row.confirm_date for row in buy_dates_query}

        for p in positions:
            # #2372：分组键用 ledger_id（真外键）而非 account_name（可编辑快照）——
            # 重名账户按名称会并成一组（真库：支付宝×2 / 天天基金×2），账户改名后
            # 前端按名回查整组落空。None（未归档持仓）归哨兵键 'unfiled'。
            # 行内仍带 ledger_id + account_name 快照供展示，键才是关联依据。
            #
            # 与 #2404 的 `p.account_name or '未指定账户'` 兜底同源同目的（避开
            # jsonify sort_keys 对 None 键的 TypeError），但用哨兵键把它**结构性
            # 消除**：None 根本不会成为键，无需靠文案兜底；且键与账户一一对应，
            # 不再受改名 / 重名影响——故保留本实现，移除 #2404 兜底。
            key = str(p.ledger_id) if p.ledger_id is not None else 'unfiled'
            if key not in result:
                result[key] = []

            # 获取首次买入确认日
            buy_confirm = first_buy_dates.get(p.id)
            if buy_confirm is None:
                buy_confirm = p.confirm_date  # 兼容无交易记录的回退

            result[key].append(
                {
                    'id': p.id,
                    'symbol': p.symbol,
                    'name': p.name,
                    'type': p.asset_type,
                    'type_label': TYPE_LABELS.get(p.asset_type, p.asset_type),
                    'market': p.market,
                    'market_label': MARKET_LABELS.get(p.market, p.market),
                    'allocation': p.allocation,
                    'allocation_label': ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类'),
                    'quantity': Money.min_unit_to_shares(p.quantity),
                    'avg_price': Money.price_units_to_yuan(p.avg_price),
                    'currency': p.currency,
                    'current_price': Money.price_units_to_yuan(p.current_price),
                    'confirm_date': buy_confirm.isoformat() if buy_confirm else None,
                    'ledger_id': p.ledger_id,
                    'account_name': p.account_name,
                }
            )
        return {'data': result}

    # 分页模式保持不变
    items, total = paginate(query, page=page, per_page=per_page)
    data = [enrich_position_dict(p) for p in items]
    return {'data': data, 'total': total, 'page': page, 'per_page': per_page}
