# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 19:33
# File : views.py
from datetime import datetime

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.database import get_db
from app.core.money import Money
from app.domains.funds.models import FeeRatio, Fund, Manager, PurchaseRule, RedeemRule
from app.domains.funds.schemas import FundNavRequest
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.fund_data_service import get_fund_nav_map

bp = APIBlueprint('funds', __name__, url_prefix='/api/funds')


@bp.get('/search/')
def search_funds():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'data': [], 'message': 'ok'})
    with get_db() as db:
        funds = (
            db.query(Fund)
            .filter((Fund.fund_code.ilike(f'%{q}%')) | (Fund.name.ilike(f'%{q}%')) | (Fund.pinyin_abbr.ilike(f'%{q}%')))
            .limit(20)
            .all()
        )
        result = []
        for f in funds:
            # 🔥 核心修改：搜索时同时拉取该基金真实的“申购费率”
            rate_record = (
                db.query(FeeRatio).filter(FeeRatio.fund_code == f.fund_code, FeeRatio.fee_type == 'purchase').first()
            )
            # 数据库没录则为 0.015（或者可以根据需求调整）
            default_rate = 0.015
            rate = float(rate_record.rate) if rate_record and rate_record.rate is not None else default_rate

            result.append(
                {
                    'code': f.fund_code,
                    'name': f.name,
                    'type': 'fund',
                    'subscription_rate': rate,  # ✅ 返回真实费率
                }
            )
        return jsonify({'data': result, 'message': 'ok'})


@bp.get('/managers/search/')
def search_managers():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'data': [], 'message': 'ok'})
    with get_db() as db:
        mgrs = db.query(Manager).filter(Manager.name.ilike(f'%{q}%')).limit(20).all()
        result = [{'code': m.mgr_code, 'name': m.name, 'type': m.mgr_type} for m in mgrs]
        return jsonify({'data': result, 'message': 'ok'})


@bp.post('/nav/')
@bp.input(FundNavRequest, location='json')
def get_fund_nav_by_date(json_data: FundNavRequest):
    target_date = json_data.target_date
    symbols = json_data.symbols

    with get_db() as db:
        nav_map = get_fund_nav_map(db, symbols, target_date)

    result = list()
    for code, nav in nav_map.items():
        result.append({'fund_code': code, 'unit_nav': float(nav), 'date': target_date.strftime('%Y-%m-%d')})
    return jsonify({'data': result, 'message': 'ok'})


@bp.get('/<string:fund_code>/fee-rates/')
def get_fund_fee_rates(fund_code: str):
    """获取指定基金的申购和赎回费率结构（用于前端展示和计算）"""
    with get_db() as db:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'data': None, 'message': '基金代码不存在'}), 404

        # 2. 查询申购费率规则 (Purchase)
        purchase_rates = []
        purchase_ratios = (
            db.query(FeeRatio, PurchaseRule)
            .join(PurchaseRule, FeeRatio.purchase_rule_id == PurchaseRule.id)
            .filter(FeeRatio.fund_code == fund_code, FeeRatio.fee_type == 'purchase')
            .all()
        )
        for ratio, rule in purchase_ratios:
            # 🔥 防御性修复：防止数据库里存在字符串 "0.015" 导致 SQLAlchemy 崩溃
            safe_rate = 0.0
            if ratio.rate is not None:
                try:
                    safe_rate = float(ratio.rate)
                except (ValueError, TypeError):
                    safe_rate = 0.0

            purchase_rates.append(
                {
                    'start_quota': Money.cents_to_yuan(rule.start_quota),
                    'end_quota': Money.cents_to_yuan(rule.end_quota) if rule.end_quota else None,
                    'rate': safe_rate,
                }
            )

        # 3. 查询赎回费率规则 (Redeem)
        redeem_rates = []
        redeem_ratios = (
            db.query(FeeRatio, RedeemRule)
            .join(RedeemRule, FeeRatio.redeem_rule_id == RedeemRule.id)
            .filter(FeeRatio.fund_code == fund_code, FeeRatio.fee_type == 'redeem')
            .all()
        )
        for ratio, rule in redeem_ratios:
            # 🔥 防御性修复：同上，防止字符串类型的费率导致炸裂
            safe_rate = 0.0
            if ratio.rate is not None:
                try:
                    safe_rate = float(ratio.rate)
                except (ValueError, TypeError):
                    safe_rate = 0.0

            redeem_rates.append({'start_day': rule.start_day, 'end_day': rule.end_day, 'rate': safe_rate})

        return jsonify({'data': {'purchase': purchase_rates, 'redeem': redeem_rates}, 'message': 'ok'})


@bp.post('/redeem-fee/estimate/')
def estimate_redeem_fee():
    """计算基金卖出预估手续费及费率分布（严格遵循 FIFO 扣减）"""
    data = request.get_json()
    position_id = data.get('position_id')
    sell_shares = data.get('shares')  # 准备卖出的份额
    sell_date_str = data.get('sell_date')  # 目标赎回日期

    if not sell_date_str:
        return jsonify({'data': None, 'message': '缺少卖出日期'}), 400
    if not position_id:
        return jsonify({'data': None, 'message': '缺少持仓 ID'}), 400

    try:
        sell_date = datetime.strptime(sell_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'data': None, 'message': '卖出日期格式错误'}), 400

    with get_db() as db:
        position = db.query(Position).get(position_id)
        if not position or position.asset_type != 'fund':
            return jsonify({'data': None, 'message': '无效持仓或非基金'}), 400
        fund_code = position.symbol

        redeem_rules = (
            db.query(RedeemRule.start_day, RedeemRule.end_day, FeeRatio.rate)
            .select_from(FeeRatio)
            .join(RedeemRule, FeeRatio.redeem_rule_id == RedeemRule.id)
            .filter(FeeRatio.fund_code == fund_code, FeeRatio.fee_type == 'redeem')
            .order_by(RedeemRule.start_day.asc())
            .all()
        )

        buy_transactions = (
            db.query(Transaction)
            .filter(Transaction.position_id == position_id, Transaction.txn_type == 'buy')
            .order_by(Transaction.confirm_date.asc())
            .all()
        )
        if not buy_transactions:
            return jsonify({'data': None, 'message': '该持仓无历史买入记录'}), 400

        remaining_to_sell = sell_shares
        total_fee = 0.0

        fee_distribution = {f'{float(r.rate):.6f}': 0.0 for r in redeem_rules}
        fee_distribution['0.000000'] = 0.0

        for txn in buy_transactions:
            if remaining_to_sell <= 0:
                break

            txn_shares = Money.min_unit_to_shares(txn.quantity)
            deduct_shares = min(remaining_to_sell, txn_shares)
            txn_price = Money.cents_to_yuan(txn.price)
            txn_confirm_date = txn.confirm_date

            if not txn_confirm_date:
                continue

            days = (sell_date - txn_confirm_date).days

            matched_rate = 0.0
            for rule in redeem_rules:
                if days >= rule.start_day:
                    if rule.end_day is None or days < rule.end_day:
                        matched_rate = float(rule.rate)
                        break

            fee = deduct_shares * txn_price * matched_rate
            total_fee += fee

            key = f'{matched_rate:.6f}'
            current_shares = fee_distribution.get(key, 0.0)
            fee_distribution[key] = current_shares + deduct_shares

            remaining_to_sell -= deduct_shares

        if remaining_to_sell > 0:
            return jsonify({'data': None, 'message': '持仓份额不足，无法卖出指定数量'}), 400

        # 🔥 核心修复：去掉 if 过滤条件，保证所有费率阶梯都输出，哪怕份额为 0！
        details = []
        for rule in redeem_rules:
            rate_key = f'{float(rule.rate):.6f}'
            shares = fee_distribution.get(rate_key, 0.0)
            range_label = f'{rule.start_day}~{rule.end_day}天(不含)' if rule.end_day else f'≥{rule.start_day}天'
            details.append({'range': range_label, 'shares': shares, 'rate': float(rule.rate)})

        return jsonify({'data': {'total_fee': round(total_fee, 2), 'details': details}, 'message': 'ok'})
