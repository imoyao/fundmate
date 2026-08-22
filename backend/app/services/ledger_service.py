# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/17 22:16
# File : ledger_service.py
# -*- coding: utf-8 -*-
"""账户业务逻辑服务层"""

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.core.constants import ALLOCATION_LABELS, LEDGER_TYPE_LABELS, TYPE_LABELS
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.summary_service import orphan_money_fund_net_by_ledger


class LedgerService:
    """账户维度数据聚合与计算服务，所有方法均为纯函数，不持有状态"""

    @staticmethod
    def get_overview_stats(db: Session, family_id: int) -> dict:
        """账户资金全景：按类型分组市值、负债、净资产（覆盖游离数据）"""
        # 轻量列加载（避免全量 ORM 实体）；持仓市值聚合必须保留逐行 ROUND_HALF_UP 语义（tech-debt §13，#911 M4）
        all_positions = (
            db.query(Position.ledger_id, Position.current_price, Position.quantity)
            .filter(Position.family_id == family_id)
            .all()
        )
        all_assets = (
            db.query(Asset.ledger_id, Asset.amount, Asset.major_category).filter(Asset.family_id == family_id).all()
        )

        # 孤儿货基/逆回购流水净额（分）按 ledger_id 归组；None → 0（游离）。
        # 与 positions/assets 的游离聚合统一按同一 key 合并（并入 deleted 分组），
        # 避免重复计数、口径一致（悬空数据语义等同「已删除账户」）。
        orphan_map = orphan_money_fund_net_by_ledger(db, family_id)

        # 按 ledger_id 聚合持仓市值（分），ledger_id 为 None 统一归入 key=0
        pos_map: dict[int, int] = {}
        for lid, cp, qty in all_positions:
            lid = lid or 0  # None → 0 表示游离
            mv_cents = Money.multiply_price_quantity(cp, qty)
            pos_map[lid] = pos_map.get(lid, 0) + mv_cents

        # 按 ledger_id 聚合非负资产金额
        asset_map: dict[int, int] = {}
        for lid, amount, major_category in all_assets:
            if major_category != 'liability':
                lid = lid or 0
                asset_map[lid] = asset_map.get(lid, 0) + amount

        # 获取当前家庭所有账户
        ledgers = db.query(Ledger).filter(Ledger.family_id == family_id).order_by(Ledger.created_at.asc()).all()
        ledger_id_to_type = {led.id: led.ledger_type for led in ledgers}

        # 按类型分组
        type_groups: dict[str, dict] = {}
        for ledger in ledgers:
            t = ledger.ledger_type
            if t not in type_groups:
                type_groups[t] = {
                    'type': t,
                    'label': LEDGER_TYPE_LABELS.get(t, t),
                    'count': 0,
                    'total': 0.0,
                }
            total_cents = pos_map.get(ledger.id, 0) + asset_map.get(ledger.id, 0) + orphan_map.get(ledger.id, 0)
            type_groups[t]['count'] += 1
            type_groups[t]['total'] += Money.cents_to_yuan(total_cents)

        # 处理已删除账户和游离数据（ledger_id 无效或为 None）
        orphan_cents = 0
        orphan_ledger_ids = set()
        for lid in set(list(pos_map.keys()) + list(asset_map.keys()) + list(orphan_map.keys())):
            if lid == 0:
                # 游离数据：ledger_id IS NULL
                orphan_ledger_ids.add(0)
                orphan_cents += pos_map.get(0, 0) + asset_map.get(0, 0) + orphan_map.get(0, 0)
            elif lid not in ledger_id_to_type:
                # 已删除账户
                orphan_ledger_ids.add(lid)
                orphan_cents += pos_map.get(lid, 0) + asset_map.get(lid, 0) + orphan_map.get(lid, 0)

        if orphan_ledger_ids:
            type_groups['deleted'] = {
                'type': 'deleted',
                'label': '已删除账户',
                'count': len(orphan_ledger_ids),
                'total': Money.cents_to_yuan(orphan_cents),
            }

        # 负债总额（分 → 元）
        liability_cents = sum(amount for _, amount, major_category in all_assets if major_category == 'liability')
        liability_yuan = Money.cents_to_yuan(liability_cents)

        total_assets = sum(g['total'] for g in type_groups.values())
        net_worth = round(total_assets - liability_yuan, 2)

        order = ['bank', 'stock', 'fund', 'e_account', 'property', 'deleted']
        sorted_groups = [type_groups[t] for t in order if t in type_groups]

        return {
            'groups': sorted_groups,
            'liability_total': round(liability_yuan, 2),
            'net_worth': net_worth,
        }

    @staticmethod
    def get_portfolio_stats(db: Session, ledger_id: int) -> dict:
        """通用持仓统计（适用于 stock / fund 账户）"""
        positions = db.query(Position).filter(Position.ledger_id == ledger_id).all()

        if not positions:
            return {
                'total_market_value': 0.0,
                'total_cost': 0.0,
                'position_pnl': 0.0,
                'position_count': 0,
                'allocation_distribution': {},
                'type_distribution': {},
            }

        total_mv = sum(Money.multiply_price_quantity(p.current_price, p.quantity) for p in positions)
        total_cost = sum(Money.multiply_price_quantity(p.avg_price, p.quantity) for p in positions)

        alloc_map: dict[str, int] = {}
        type_map: dict[str, int] = {}
        for p in positions:
            val = Money.multiply_price_quantity(p.current_price, p.quantity)
            alloc = p.allocation or 'longterm'
            alloc_map[alloc] = alloc_map.get(alloc, 0) + val
            # 按资产大类聚合市值（type_distribution），后端唯一出口，前端不再自行聚合
            type_label = TYPE_LABELS.get(p.asset_type, p.asset_type or '其他')
            type_map[type_label] = type_map.get(type_label, 0) + val

        return {
            'total_market_value': Money.cents_to_yuan(total_mv),
            'total_cost': Money.cents_to_yuan(total_cost),
            'position_pnl': Money.cents_to_yuan(total_mv - total_cost),
            'position_count': len(positions),
            'allocation_distribution': {k: Money.cents_to_yuan(v) for k, v in alloc_map.items()},
            'type_distribution': {k: Money.cents_to_yuan(v) for k, v in type_map.items()},
        }

    @staticmethod
    def get_cumulative_return(db: Session, ledger_id: int) -> float:
        """累计收益（SQL 聚合，利用 idx_txn_ledger_date 索引）"""
        stats = (
            db.query(
                Transaction.txn_type,
                func.coalesce(func.sum(Transaction.amount), 0).label('total_amount'),
            )
            .filter(
                Transaction.ledger_id == ledger_id,
                Transaction.txn_type.in_(['buy', 'sell', 'dividend']),
            )
            .group_by(Transaction.txn_type)
            .all()
        )

        amounts = {'buy': 0, 'sell': 0, 'dividend': 0}
        for txn_type, total_amount in stats:
            if txn_type in amounts:
                amounts[txn_type] = total_amount

        return Money.cents_to_yuan(amounts['sell'] + amounts['dividend'] - amounts['buy'])

    @staticmethod
    def get_cash_balance(db: Session, ledger: Ledger) -> float | None:
        """获取关联现金账户的活期余额"""
        if not ledger.linked_cash_ledger_id:
            return None
        cash_ledger = db.get(Ledger, ledger.linked_cash_ledger_id)
        if not cash_ledger or cash_ledger.family_id != ledger.family_id:
            return None
        current = (
            db.query(func.coalesce(func.sum(Asset.amount), 0))
            .filter(
                Asset.ledger_id == cash_ledger.id,
                Asset.major_category == 'current',
            )
            .scalar()
        )
        return Money.cents_to_yuan(current)

    @staticmethod
    def get_money_fund_stats(db: Session, ledger_id: int) -> dict:
        """计算货基持仓占比及金额"""
        positions = db.query(Position).filter(Position.ledger_id == ledger_id).all()
        valid_positions = [p for p in positions if p.current_price and p.quantity]

        total_mv = sum(Money.multiply_price_quantity(p.current_price, p.quantity) for p in valid_positions)
        if total_mv == 0:
            return {'money_fund_ratio': 0.0, 'money_fund_amount': 0.0}

        money_fund_mv = sum(
            Money.multiply_price_quantity(p.current_price, p.quantity)
            for p in valid_positions
            if p.asset_type == 'money_fund'
        )
        return {
            'money_fund_ratio': round(money_fund_mv / total_mv * 100, 2),
            'money_fund_amount': Money.cents_to_yuan(money_fund_mv),
        }

    @staticmethod
    def get_bank_stats(db: Session, ledger_id: int) -> dict:
        # 1. 现金/活期余额
        current_amount = (
            db.query(func.coalesce(func.sum(Asset.amount), 0))
            .filter(Asset.ledger_id == ledger_id, Asset.major_category == 'current')
            .scalar()
        )
        # 2. 理财/基金持仓
        positions = db.query(Position).filter(Position.ledger_id == ledger_id).all()
        fund_mv = sum(Money.multiply_price_quantity(p.current_price, p.quantity) for p in positions)
        total_balance = current_amount + fund_mv

        # 🔥 3. 新增：查询该银行卡下关联的负债（房贷）
        liability_cents = (
            db.query(func.coalesce(func.sum(Asset.amount), 0))
            .filter(Asset.ledger_id == ledger_id, Asset.major_category == 'liability')
            .scalar()
        )

        return {
            'total_market_value': Money.cents_to_yuan(total_balance),
            'current_balance': Money.cents_to_yuan(current_amount),
            'cash_balance': Money.cents_to_yuan(current_amount),
            'fund_value': Money.cents_to_yuan(fund_mv),
            'position_count': len(positions),
            # 🔥 新增字段，直接暴露给视图层
            'linked_liability': Money.cents_to_yuan(liability_cents) if liability_cents else 0.0,
        }

    @staticmethod
    def get_property_stats(db: Session, ledger_id: int) -> dict:
        """实物资产：总估值 + 数量"""
        total_est = db.query(func.coalesce(func.sum(Asset.amount), 0)).filter(Asset.ledger_id == ledger_id).scalar()
        count = db.query(Asset).filter(Asset.ledger_id == ledger_id).count()
        return {
            'total_market_value': Money.cents_to_yuan(total_est),
            'asset_count': count,
        }

    @staticmethod
    def get_positions_paginated(
        db: Session, ledger_id: int, page: int, per_page: int, search: str | None = None
    ) -> tuple[list[dict], int]:
        """获取持仓分页列表（修复命名与 B5 精度）。

        search（#982）：按产品名称/代码模糊匹配；None 表示不过滤。
        注意：total_mv_cents 汇总保持账本全量口径（账户级总市值基线），
        不随搜索过滤——搜索只影响列表行，不动汇总分母。
        """
        query = db.query(Position).filter(Position.ledger_id == ledger_id)
        if search:
            like = f'%{search}%'
            query = query.filter(or_(Position.name.ilike(like), Position.symbol.ilike(like)))
        total = query.count()
        positions = (
            query.order_by(desc(Position.current_price * Position.quantity / 10000.0))
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        # 总市值：Python 聚合（分）。逐行 ROUND_HALF_UP 语义必须保留（tech-debt §13，
        # SQL 聚合 sum(price×qty)/10000 与逐行四舍五入有分位差异），仅轻量加载两列避免全量 ORM 实体（#911 M4）
        total_mv_cents = sum(
            Money.multiply_price_quantity(cp, qty)
            for cp, qty in (
                db.query(Position.current_price, Position.quantity).filter(Position.ledger_id == ledger_id).all()
            )
        )

        items = []
        for p in positions:
            mv_cents = Money.multiply_price_quantity(p.current_price, p.quantity)
            pnl_cents = Money.multiply_price_quantity(p.current_price - p.avg_price, p.quantity) if p.avg_price else 0
            cur = p.current_price  # 分
            avg = p.avg_price  # 分
            pnl_rate = round((cur - avg) / avg * 100, 2) if avg else 0.0

            # 🔥 修复 B5：确保 total_mv_cents=0 时返回 0.0 (浮点数)，防止前端解析为整数 0
            ratio = float(round(mv_cents / total_mv_cents * 100, 2)) if total_mv_cents else 0.0

            back = None
            if cur and avg and cur < avg:
                back = round((avg - cur) / cur * 100, 2)

            items.append(
                {
                    'id': p.id,
                    'symbol': p.symbol,
                    'name': p.name,
                    'type_label': TYPE_LABELS.get(p.asset_type, p.asset_type),
                    'market_value': Money.cents_to_yuan(mv_cents),
                    'pnl': Money.cents_to_yuan(pnl_cents),
                    'pnl_rate': pnl_rate,
                    'avg_price': Money.cents_to_yuan(avg),
                    'current_price': Money.cents_to_yuan(cur),
                    'allocation': p.allocation,
                    'allocation_label': ALLOCATION_LABELS.get(p.allocation, p.allocation or '未配置'),
                    'position_ratio': ratio,  # 绝对为 float
                    'back_to_cost_rate': back,
                    'fund_category': None,
                }
            )

        return items, total

    @staticmethod
    def get_transactions_paginated(
        db: Session, ledger_id: int, page: int, per_page: int, search: str | None = None
    ) -> tuple[list[dict], int]:
        """获取交易记录分页列表（修复命名）。

        search（#982）：按产品名称/代码模糊匹配；None 表示不过滤。
        """
        query = db.query(Transaction).filter(Transaction.ledger_id == ledger_id)
        if search:
            like = f'%{search}%'
            query = query.filter(or_(Transaction.position_name.ilike(like), Transaction.symbol.ilike(like)))
        total = query.count()
        txn_list = (
            query.order_by(
                Transaction.confirm_date.desc().nullslast(),
                Transaction.created_at.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        items = []
        for t in txn_list:
            items.append(
                {
                    'id': t.id,
                    'confirm_date': t.confirm_date.isoformat() if t.confirm_date else None,
                    'txn_type': t.txn_type,
                    'position_name': t.position_name or '未知资产',
                    'symbol': t.symbol or '',
                    'price': Money.cents_to_yuan(t.price),
                    'quantity': Money.min_unit_to_shares(t.quantity),
                    'amount': Money.cents_to_yuan(t.amount),
                    'fee': Money.cents_to_yuan(t.fee),
                    'notes': t.notes,
                }
            )

        return items, total
