# -*- coding: utf-8 -*-
"""跨组合对比（#调仓解读付费功能 · L3）—— 我的账户集 vs 投顾组合。

重点覆盖：

1. **基金代码级三集合** —— 交集 / 投顾独有 / 我独有 判定正确；
2. **货基 / 债基剔除** —— 投顾侧按 `fund_types.name`（货币型/债券型）剔除，
   我侧按 `positions.type`（bond/money_fund）剔除；
3. **「混合型」不剔除** —— 库里无「偏股/偏债」二级分类，混合型归入权益类；
4. **降级契约** —— 组合不存在 → ValueError；取数失败 → degraded=True（不拿 0 冒充）；
5. **指标透出为 float** —— 回撤/夏普/收益 None 时保留 key 值为 None，有值时 float。

数据域：投顾（`advisor_portfolios`/`advisor_holdings`）在 **market 域**，我的持仓
（`positions`）在 **user 域**。测试用路由会话 `db` fixture 跨域读写（conftest 已把
`_engines` 映射到分离的内存引擎）。
"""

from contextlib import closing
from datetime import date

from app.core.db_factory import market_session_factory
from app.domains.funds.models import AdvisorHolding, AdvisorPortfolio, Fund, FundType
from app.services.advisor_comparison import build_advisor_comparison


def _seed_fund_type(market_db, name):
    """建/取 fund_types 行，返回 id。"""
    row = market_db.query(FundType).filter(FundType.name == name).first()
    if row is None:
        row = FundType(name=name)
        market_db.add(row)
        market_db.flush()
    return row.id


def _seed_fund(market_db, code, type_name):
    """建/取 funds 行（挂 fund_type_id），供投顾成分基金的货基/债基剔除判定。"""
    type_id = _seed_fund_type(market_db, type_name)
    row = market_db.query(Fund).filter(Fund.fund_code == code).first()
    if row is None:
        row = Fund(fund_code=code, name=f'测试基金{code}', fund_type_id=type_id)
        market_db.add(row)
        market_db.flush()
    return row


def _seed_advisor(db, code, name='测试投顾组合', platform='QIEMAN', **fields):
    """建/取投顾组合（market 域，走 `db` 路由会话，与 service 的读一致）。"""
    row = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code == code).first()
    if row is None:
        row = AdvisorPortfolio(code=code, name=name, platform=platform, **fields)
        db.add(row)
    else:
        row.name = name
        row.platform = platform
        for key, value in fields.items():
            setattr(row, key, value)
    db.flush()
    return row


def _seed_advisor_holding(db, code, fund_code, as_of_date=date(2026, 1, 5), **fields):
    """造一条投顾持仓（market 域，走 `db` 路由会话，与 service 的读一致）。"""
    pid = db.query(AdvisorPortfolio.id).filter(AdvisorPortfolio.code == code).scalar()
    exists = (
        db.query(AdvisorHolding)
        .filter(
            AdvisorHolding.portfolio_id == pid,
            AdvisorHolding.fund_code == fund_code,
            AdvisorHolding.as_of_date == as_of_date,
        )
        .first()
    )
    if exists is None:
        db.add(
            AdvisorHolding(
                portfolio_id=pid,
                fund_code=fund_code,
                as_of_date=as_of_date,
                source='qieman',
                **fields,
            )
        )
        db.flush()


def _seed_my_position(db, symbol, asset_type, name=None, **fields):
    """造一条我的持仓（user 域，走 `db` 路由会话）。"""
    from app.domains.positions.models import Position

    kwargs = dict(
        family_id=1,
        symbol=symbol,
        asset_type=asset_type,
        name=name or symbol,
        ownership_status='active',
    )
    kwargs.update(fields)
    pos = Position(**kwargs)
    db.add(pos)
    db.flush()
    return pos


# ── 基金代码级三集合 ──────────────────────────────────────────────────────


def test_three_way_overlap(db):
    """投顾持仓 3 只（含 1 只货基剔除），我的持仓 3 只（含 1 只 bond 剔除）⇒ 交集 1 只。"""
    with closing(market_session_factory()()) as mdb:
        _seed_fund(mdb, '000001', '股票型')
        _seed_fund(mdb, '000002', '债券型')  # 债基 → 投顾侧剔除
        _seed_fund(mdb, '000003', '货币型')  # 货基 → 投顾侧剔除
        mdb.commit()

    _seed_advisor(db, 'ZH990001')
    _seed_advisor_holding(db, 'ZH990001', '000001', after_ratio=50.0)  # 股票型，保留
    _seed_advisor_holding(db, 'ZH990001', '000002', after_ratio=30.0)  # 债券型，剔除
    _seed_advisor_holding(db, 'ZH990001', '000003', after_ratio=20.0)  # 货币型，剔除

    _seed_my_position(db, '000001', 'fund')  # 权益，交集命中
    _seed_my_position(db, '000004', 'fund')  # 权益，我独有
    _seed_my_position(db, '000005', 'bond')  # 债券，我侧剔除
    db.commit()

    result = build_advisor_comparison(db, 'ZH990001', 1)

    advisor_codes = {h['fund_code'] for h in result['advisor']['holdings']}
    assert advisor_codes == {'000001'}, '投顾侧应只保留股票型（剔除债基+货基）'

    mine_codes = {h['fund_code'] for h in result['mine']['holdings']}
    assert mine_codes == {'000001', '000004'}, '我侧应剔除 bond'

    ov = result['overlap']
    assert {c['fund_code'] for c in ov['common']} == {'000001'}
    assert {c['fund_code'] for c in ov['advisor_only']} == set()
    assert {c['fund_code'] for c in ov['mine_only']} == {'000004'}


def test_mixed_type_is_not_excluded(db):
    """「混合型」不剔除（库里无偏股/偏债二级分类，归入权益类兜底）。"""
    with closing(market_session_factory()()) as mdb:
        _seed_fund(mdb, '110001', '混合型')
        mdb.commit()

    _seed_advisor(db, 'ZH990002')
    _seed_advisor_holding(db, 'ZH990002', '110001', after_ratio=80.0)
    _seed_my_position(db, '110001', 'fund')
    db.commit()

    result = build_advisor_comparison(db, 'ZH990002', 1)
    assert {h['fund_code'] for h in result['advisor']['holdings']} == {'110001'}
    assert {c['fund_code'] for c in result['overlap']['common']} == {'110001'}


# ── 降级契约 ──────────────────────────────────────────────────────────────


def test_raises_on_unknown_code(db):
    """组合不存在 → ValueError（调用方转 404），不抛异常返回空。"""
    try:
        build_advisor_comparison(db, 'NOSUCHCODE', 1)
    except ValueError:
        return
    raise AssertionError('组合不存在应抛 ValueError')


def test_raises_on_empty_code(db):
    """空 code → ValueError。"""
    try:
        build_advisor_comparison(db, '   ', 1)
    except ValueError:
        return
    raise AssertionError('空 code 应抛 ValueError')


def test_empty_holdings_return_empty_three_way(db):
    """无持仓快照 → 三集合全空，不 500、不拿 0 冒充。"""
    _seed_advisor(db, 'ZH990003')

    result = build_advisor_comparison(db, 'ZH990003', 1)

    assert result['advisor']['as_of_date'] is None
    assert result['advisor']['holdings'] == []
    assert result['overlap']['common'] == []
    assert result['overlap']['advisor_only'] == []
    assert result['overlap']['mine_only'] == []


# ── 指标透出 ──────────────────────────────────────────────────────────────


def test_metrics_transparent_as_float_or_none(db):
    """指标有值 → float；无值 → 保留 key 值为 None（固定契约，前端据此降级「—」）。"""
    _seed_advisor(db, 'ZH990004', max_drawdown=-15.6, sharpe_ratio=0.85, volatility=18.2)

    result = build_advisor_comparison(db, 'ZH990004', 1)
    adv = result['advisor']

    assert adv['max_drawdown'] == -15.6
    assert isinstance(adv['max_drawdown'], float)
    assert adv['sharpe_ratio'] == 0.85
    assert adv['volatility'] == 18.2
    # 未落库的收益字段保留 key 值为 None
    assert 'annual_return' in adv
    assert adv['annual_return'] is None


# ── 端点级 ────────────────────────────────────────────────────────────────


def test_endpoint_returns_envelope(db, client):
    _seed_advisor(db, 'ZH990005', name='端点组合')
    db.commit()
    resp = client.get('/api/funds/advisors/ZH990005/compare/')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['advisor']['code'] == 'ZH990005'
    assert data['advisor']['name'] == '端点组合'
    assert 'overlap' in data
    assert 'caveats' in data


def test_endpoint_404_for_unknown_code(client):
    resp = client.get('/api/funds/advisors/NOSUCHCODE/compare/')
    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == 1002
