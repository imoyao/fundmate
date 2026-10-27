from datetime import datetime

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.funds.schemas import FundNavRequest
from app.services.fund_service import FundService
from app.services.fund_style_service import get_fund_style_box, get_fund_style_history, portfolio_style_exposure
from app.services.similar_fund_service import get_similar_funds

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


@bp.get('/<string:fund_code>/nav/')
def get_fund_nav(fund_code: str):
    """确认日净值自动回填（#948）：≤date 的最近一条单位净值。

    ?date=YYYY-MM-DD 缺省取最新一条。无匹配（未回填/新基金）返回 data=null，
    前端保持用户手输不阻塞。
    """
    raw = request.args.get('date')
    target = None
    if raw:
        try:
            from datetime import date as _date

            target = _date.fromisoformat(raw)
        except ValueError:
            return jsonify({'data': None, 'message': '日期格式错误，应为 YYYY-MM-DD', 'error_code': 1001}), 400

    with get_db() as db:
        from app.domains.funds.models import DailyWorth

        q = db.query(DailyWorth).filter(DailyWorth.fund_code == fund_code)
        if target is not None:
            q = q.filter(DailyWorth.date <= target)
        row = q.order_by(DailyWorth.date.desc()).first()
        if not row or row.unit_nav is None:
            return jsonify({'data': None, 'message': 'ok'})
        return jsonify(
            {
                'data': {
                    'fund_code': row.fund_code,
                    'date': row.date.isoformat(),
                    'unit_nav': float(row.unit_nav),
                    'acc_nav': float(row.acc_nav) if row.acc_nav is not None else None,
                },
                'message': 'ok',
            }
        )


@bp.get('/<string:fund_code>/fee-rates/')
def get_fund_fee_rates(fund_code: str):
    with get_db() as db:
        data = FundService.get_fund_fee_rates(db, fund_code)
        if data is None:
            return jsonify({'data': None, 'message': '基金代码不存在', 'error_code': 1002}), 404
    return jsonify({'data': data, 'message': 'ok'})


@bp.post('/redeem-fee/estimate/')
def estimate_redeem_fee():
    """预估赎回费用及费率分布，兼容全仓与指定份额两种模式"""
    data = request.get_json()
    position_id = data.get('position_id')
    sell_date_str = data.get('sell_date')

    # 细化参数缺失提示
    if not position_id:
        return jsonify({'data': None, 'message': '缺少持仓 ID', 'error_code': 1001}), 400
    if not sell_date_str:
        return jsonify({'data': None, 'message': '缺少卖出日期', 'error_code': 1001}), 400

    try:
        sell_date = datetime.strptime(sell_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'data': None, 'message': '日期格式错误', 'error_code': 1001}), 400

    raw_shares = data.get('shares')
    sell_shares = None
    if raw_shares is not None:
        try:
            val = float(raw_shares)
            if val > 0:
                sell_shares = val
        except (TypeError, ValueError):
            return jsonify({'data': None, 'message': '份额格式错误', 'error_code': 1001}), 400

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
            return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400


@bp.post('/<string:fund_code>/fee-sync/')
def sync_fund_fees(fund_code: str):
    """同步指定基金的费率信息"""
    with get_db() as db:
        success = FundService.sync_fund_fees(db, fund_code)
        if success:
            return jsonify({'data': {'message': '费率同步成功'}, 'message': 'ok'})
        else:
            return jsonify({'data': None, 'message': '同步失败，请稍后重试'})


# ── 投顾组合明细只读接口（#1468）──
# advisor_holdings / advisor_adjust_histories 此前一直是「只写不读」：同步任务落库，
# 但全后端没有任何接口暴露，调仓与持仓数据事实上锁在库里。这里补两个只读口子，
# 供自选「投顾组合」速览抽屉消费（market 域公开参照数据，无需登录）。


# ── 基金投资风格箱只读接口（#2478）──
# 数据来自 fund_style_exposures（韭圈儿 get-style-history，月度）。三个口子对应
# 三个消费场景：详情页风格箱 / 漂移序列 / 组合加权透视。风格箱只覆盖基金与 ETF，
# 股票持仓不在口径内；QDII 上游映射存疑（270042 纳指100 实测「固收风格 81.28」），
# 透出原值，由前端按需注明来源。


@bp.get('/style/portfolio/')
def get_portfolio_style():
    """组合加权风格暴露（持仓透视，家庭 / 组合 / 账户三级口径）。

    作用域（2026-10-27）：不传 = 家庭级；``?portfolio_id=`` = 组合口径（显式归属 +
    成员账本继承，唯一出口 ``services/scope.py``）；``?ledger_id=`` = 单账户；同传 400
    （``error_code=1001``，与穿透 / 归因同款）。加这两个参数是因为组合详情页此前直接
    复用家庭级结果却标题「组合风格构成」（同类问题 #2595 在穿透面板修过）。

    无持仓 / 全无风格箱数据时 styles 为空数组、coverage_pct=0——前端据此显示
    「暂无数据」，不显示全零箱体（「0 暴露」与「没有数据」是两件事）。
    """
    try:
        with get_db() as db:
            data = portfolio_style_exposure(
                db,
                get_family_id(),
                portfolio_id=request.args.get('portfolio_id', type=int),
                ledger_id=request.args.get('ledger_id', type=int),
            )
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        # scope 参数冲突 / 组合不存在（services/scope.py 约定），与穿透 / 归因端点同款 400
        return jsonify({'data': {}, 'message': str(e), 'error_code': 1001}), 400


@bp.get('/<string:fund_code>/style/latest/')
def get_fund_style_latest(fund_code: str):
    """最新风格箱（详情页首屏）。无数据返回 data=null，前端降级「—」。"""
    with get_db() as db:
        data = get_fund_style_box(db, fund_code)
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/<string:fund_code>/style/history/')
def get_fund_style_history_view(fund_code: str):
    """风格漂移序列（月度倒序，wide 形态）。

    `?limit=` 时点数，默认 60（≈5 年），硬上限 500（上游实测最长 283 点）。
    非法值静默回退默认——展示接口不该因一个查询参数 400。
    """
    raw = request.args.get('limit')
    limit = None
    if raw:
        try:
            limit = int(raw)
        except ValueError:
            limit = None
    with get_db() as db:
        data = get_fund_style_history(db, fund_code, limit)
    return jsonify({'data': data, 'message': 'ok'})


# ── 相似基金只读接口（#2480）──
# 按需取韭圈儿相似度名单（不落库，缓存在 service 侧）。上游失败走降级：
# data.items 为空 + degraded=true，不 500——展示接口不该因一个外部源整体挂掉。


@bp.get('/<string:fund_code>/similar/')
def get_similar_funds_view(fund_code: str):
    """相似基金列表（详情页「相似基金」块）。

    返回 ``{fund_code, items: [{fund_code, fund_name, similarity,
    income_1y_pct, window}], degraded, error, source, fetched_at}``；
    degraded=true 表示上游取数失败（items 为空），前端显示「暂时取不到」。
    相似度口径为上游黑盒，前端须注明「数据来源：韭圈儿」。
    """
    data = get_similar_funds(fund_code)
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/advisors/<string:code>/holdings/')
def get_advisor_holdings(code: str):
    """投顾组合当前持仓（只读）。

    返回最新快照日的成分基金与占比。每只基金带 `in_local_db` —— 该基金是否已收录进
    本地 `funds` 表（组合成分可能暂缺于本地名录，如 QDII），前端据此决定能否跳详情。
    """
    with get_db() as db:
        try:
            data = FundService.build_advisor_holdings(db, code)
        except ValueError as e:
            return jsonify({'data': None, 'message': str(e), 'error_code': 1002}), 404
        return jsonify({'data': data, 'message': 'ok'})


@bp.get('/advisors/<string:code>/adjusts/')
def get_advisor_adjusts(code: str):
    """投顾组合调仓明细（只读），按调仓日倒序分组。

    查询参数：
    - `limit`：最近 N 个调仓日，缺省 10，上限 50；
    - `date`：只取指定调仓日（YYYY-MM-DD），与 limit 互斥时优先 date。

    来源差异写进每条的 `source`：且慢无历史调仓接口，明细由我们的持仓快照序列推导
    （`qieman`，`reason` 记录推导所依据的上一次快照日）；天天来自官方接口（`tiantian`）。
    """
    raw_limit = request.args.get('limit', '10')
    try:
        limit = max(1, min(50, int(raw_limit)))
    except ValueError:
        limit = 10
    only_date = request.args.get('date')

    with get_db() as db:
        try:
            data = FundService.build_advisor_adjusts(db, code, limit, only_date)
        except ValueError as e:
            return jsonify({'data': None, 'message': str(e), 'error_code': 1002}), 404
        return jsonify({'data': data, 'message': 'ok'})
