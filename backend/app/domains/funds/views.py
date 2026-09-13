from datetime import datetime

from apiflask import APIBlueprint
from flask import jsonify, request
from sqlalchemy import func

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
            return jsonify({'data': None, 'message': '日期格式错误，应为 YYYY-MM-DD'}), 400

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


# ── 投顾组合明细只读接口（#1468）──
# advisor_holdings / advisor_adjust_histories 此前一直是「只写不读」：同步任务落库，
# 但全后端没有任何接口暴露，调仓与持仓数据事实上锁在库里。这里补两个只读口子，
# 供自选「投顾组合」速览抽屉消费（market 域公开参照数据，无需登录）。


def _f(v) -> float | None:
    """SafeNumeric 读回是 Decimal，Flask jsonify 会把它序列化成字符串，必须显式转 float。"""
    return float(v) if v is not None else None


@bp.get('/advisors/<string:code>/holdings/')
def get_advisor_holdings(code: str):
    """投顾组合当前持仓（只读）。

    返回最新快照日的成分基金与占比。每只基金带 `in_local_db` —— 该基金是否已收录进
    本地 `funds` 表（组合成分可能暂缺于本地名录，如 QDII），前端据此决定能否跳详情。
    """
    from app.domains.funds.models import AdvisorHolding, AdvisorPortfolio, Fund

    with get_db() as db:
        portfolio = db.query(AdvisorPortfolio).filter_by(code=code).first()
        if portfolio is None:
            return jsonify({'data': None, 'message': '投顾组合不存在'}), 404

        as_of = db.query(func.max(AdvisorHolding.as_of_date)).filter_by(portfolio_id=portfolio.id).scalar()
        if as_of is None:
            return jsonify(
                {
                    'data': {
                        'code': portfolio.code,
                        'name': portfolio.name,
                        'platform': portfolio.platform,
                        'as_of_date': None,
                        'holdings': [],
                    },
                    'message': 'ok',
                }
            )

        rows = (
            db.query(AdvisorHolding)
            .filter_by(portfolio_id=portfolio.id, as_of_date=as_of)
            .order_by(AdvisorHolding.after_ratio.desc())
            .all()
        )
        codes = [r.fund_code for r in rows]
        # 两步法关联（模型注释：组合成分不建硬外键，避免暂缺基金阻塞写入）
        known = {c for (c,) in db.query(Fund.fund_code).filter(Fund.fund_code.in_(codes)).all() if c}

    holdings = [
        {
            'fund_code': r.fund_code,
            'fund_name': r.fund_name,
            'pre_ratio': _f(r.pre_ratio),
            'after_ratio': _f(r.after_ratio),
            'op_name': r.op_name,
            'in_local_db': r.fund_code in known,
        }
        for r in rows
    ]
    return jsonify(
        {
            'data': {
                'code': portfolio.code,
                'name': portfolio.name,
                'platform': portfolio.platform,
                'as_of_date': as_of.isoformat(),
                'holdings': holdings,
            },
            'message': 'ok',
        }
    )


@bp.get('/advisors/<string:code>/adjusts/')
def get_advisor_adjusts(code: str):
    """投顾组合调仓明细（只读），按调仓日倒序分组。

    查询参数：
    - `limit`：最近 N 个调仓日，缺省 10，上限 50；
    - `date`：只取指定调仓日（YYYY-MM-DD），与 limit 互斥时优先 date。

    来源差异写进每条的 `source`：且慢无历史调仓接口，明细由我们的持仓快照序列推导
    （`qieman`，`reason` 记录推导所依据的上一次快照日）；天天来自官方接口（`tiantian`）。
    """
    from app.domains.funds.models import AdvisorAdjustHistory, AdvisorPortfolio

    raw_limit = request.args.get('limit', '10')
    try:
        limit = max(1, min(50, int(raw_limit)))
    except ValueError:
        limit = 10
    only_date = request.args.get('date')

    with get_db() as db:
        portfolio = db.query(AdvisorPortfolio).filter_by(code=code).first()
        if portfolio is None:
            return jsonify({'data': None, 'message': '投顾组合不存在'}), 404

        q = db.query(AdvisorAdjustHistory.adjust_date).filter_by(portfolio_id=portfolio.id)
        if only_date:
            dates = [d for (d,) in q.distinct().all() if d.isoformat() == only_date]
        else:
            dates = [d for (d,) in q.distinct().order_by(AdvisorAdjustHistory.adjust_date.desc()).limit(limit).all()]
        if not dates:
            return jsonify(
                {
                    'data': {
                        'code': portfolio.code,
                        'name': portfolio.name,
                        'platform': portfolio.platform,
                        'adjusts': [],
                    },
                    'message': 'ok',
                }
            )

        rows = (
            db.query(AdvisorAdjustHistory)
            .filter(
                AdvisorAdjustHistory.portfolio_id == portfolio.id,
                AdvisorAdjustHistory.adjust_date.in_(dates),
            )
            .order_by(
                AdvisorAdjustHistory.adjust_date.desc(),
                AdvisorAdjustHistory.after_ratio.desc(),
            )
            .all()
        )

    # 按调仓日分组；reason 同日冗余存储，取首条即可
    grouped: dict[str, dict] = {}
    for r in rows:
        d = r.adjust_date.isoformat()
        bucket = grouped.setdefault(d, {'adjust_date': d, 'reason': r.reason, 'source': r.source, 'items': []})
        if not bucket['reason'] and r.reason:
            bucket['reason'] = r.reason
        bucket['items'].append(
            {
                'fund_code': r.fund_code,
                'fund_name': r.fund_name,
                'op_name': r.op_name,
                'pre_ratio': _f(r.pre_ratio),
                'after_ratio': _f(r.after_ratio),
            }
        )
    adjusts = [grouped[d.isoformat()] for d in sorted(dates, reverse=True) if d.isoformat() in grouped]
    return jsonify(
        {
            'data': {
                'code': portfolio.code,
                'name': portfolio.name,
                'platform': portfolio.platform,
                'adjusts': adjusts,
            },
            'message': 'ok',
        }
    )
