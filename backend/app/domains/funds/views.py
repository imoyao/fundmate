from datetime import datetime

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.funds.schemas import FundNavRequest
from app.services.fund_service import FundService

bp = APIBlueprint('funds', __name__, url_prefix='/api/funds')


@bp.get('/search/')
def search_funds():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'data': [], 'message': 'ok'})
    with get_db() as db:
        results = FundService.search_funds(db, q)
    return jsonify({'data': results, 'message': 'ok'})


@bp.get('/managers/search/')
def search_managers():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'data': [], 'message': 'ok'})
    with get_db() as db:
        from app.domains.funds.models import Manager

        mgrs = db.query(Manager).filter(Manager.name.ilike(f'%{q}%')).limit(20).all()
        result = [{'code': m.mgr_code, 'name': m.name, 'type': m.mgr_type} for m in mgrs]
    return jsonify({'data': result, 'message': 'ok'})


@bp.post('/nav/')
def get_fund_nav_by_date():
    json_data: FundNavRequest = parse_body(FundNavRequest)
    target_date = json_data.target_date
    symbols = json_data.symbols
    with get_db() as db:
        nav_map = FundService.get_fund_nav_map(db, symbols, target_date)
    result = [
        {'fund_code': code, 'unit_nav': float(nav), 'date': target_date.strftime('%Y-%m-%d')}
        for code, nav in nav_map.items()
    ]
    return jsonify({'data': result, 'message': 'ok'})


@bp.get('/<string:fund_code>/fee-rates/')
def get_fund_fee_rates(fund_code: str):
    with get_db() as db:
        data = FundService.get_fund_fee_rates(db, fund_code)
        if data is None:
            return jsonify({'data': None, 'message': '基金代码不存在'}), 404
    return jsonify({'data': data, 'message': 'ok'})


@bp.post('/redeem-fee/estimate/')
def estimate_redeem_fee():
    """预估赎回费用及费率分布，兼容全仓与指定份额两种模式"""
    data = request.get_json()
    position_id = data.get('position_id')
    sell_date_str = data.get('sell_date')

    # 细化参数缺失提示
    if not position_id:
        return jsonify({'data': None, 'message': '缺少持仓 ID'}), 400
    if not sell_date_str:
        return jsonify({'data': None, 'message': '缺少卖出日期'}), 400

    try:
        sell_date = datetime.strptime(sell_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'data': None, 'message': '日期格式错误'}), 400

    raw_shares = data.get('shares')
    sell_shares = None
    if raw_shares is not None:
        try:
            val = float(raw_shares)
            if val > 0:
                sell_shares = val
        except (TypeError, ValueError):
            return jsonify({'data': None, 'message': '份额格式错误'}), 400

    with get_db() as db:
        try:
            result = FundService.estimate_redeem_fee(
                db=db,
                position_id=position_id,
                sell_date=sell_date,
                sell_shares=sell_shares,
                family_id=get_family_id(),
            )
            return jsonify({'data': result, 'message': 'ok'})
        except ValueError as e:
            return jsonify({'data': None, 'message': str(e)}), 400


@bp.post('/<string:fund_code>/fee-sync/')
def sync_fund_fees(fund_code: str):
    """同步指定基金的费率信息"""
    with get_db() as db:
        success = FundService.sync_fund_fees(db, fund_code)
        if success:
            return jsonify({'data': {'message': '费率同步成功'}, 'message': 'ok'})
        else:
            return jsonify({'data': None, 'message': '同步失败，请稍后重试'})
