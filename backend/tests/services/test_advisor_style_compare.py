# -*- coding: utf-8 -*-
"""投顾组合 vs 我的账户·方向对照（五方向风格暴露）——离线测试。

覆盖的口径（对应 `advisor_style_compare` 的模块 docstring）：

1. **组合侧加权**：披露权重 `after_ratio` × 基金各自最新箱体，归一到「有箱体的权重合计」；
2. **无箱体基金**：不进加权、进 `missing`、把覆盖率拉低——覆盖率是结论的一部分，
   **不能**在缺失 8% 权重时仍按 100% 分布呈现；
3. **八分类聚五组**：我侧由 `portfolio_style_exposure` 的八类结果求和得来，
   不在本模块重算市值（避免两处口径漂移）；
4. **降级契约**：组合不存在 → ValueError；我侧取数失败 → degraded=True + 空方向
   （**不拿五个 0 冒充**——0% 是「都没配」这个结论）；无快照 → 空方向而非全 0。
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domains.funds.models import AdvisorHolding, AdvisorPortfolio, FundStyleExposure
from app.domains.positions.models import Position
from app.services import advisor_style_compare as asc


def _seed_portfolio(db, code='ZHTEST', **fields):
    row = AdvisorPortfolio(code=code, name='测试组合', platform='QIEMAN', **fields)
    db.add(row)
    db.flush()
    return row


def _seed_holding(db, portfolio_id, fund_code, ratio, as_of=date(2026, 11, 24)):
    db.add(
        AdvisorHolding(
            portfolio_id=portfolio_id,
            fund_code=fund_code,
            fund_name=f'基金{fund_code}',
            after_ratio=ratio,
            as_of_date=as_of,
            source='qieman',
        )
    )
    db.flush()


def _seed_box(db, fund_code, box, stat_date=date(2026, 10, 30)):
    for name, value in box.items():
        db.add(
            FundStyleExposure(
                fund_code=fund_code,
                stat_date=stat_date,
                style_name=name,
                value=Decimal(str(value)),
                source='jiucaishuo_style',
            )
        )
    db.flush()


def _by_key(directions):
    return {d['key']: d['value'] for d in directions}


# ── 组合侧 ──


def test_advisor_directions_weighted_by_disclosed_ratio(db):
    """60% 大盘 + 40% 固收 → 大盘 60 / 固收 40，其余方向补 0（0 是结论不是缺数）。"""
    portfolio = _seed_portfolio(db)
    _seed_holding(db, portfolio.id, '000001', 60.0)
    _seed_holding(db, portfolio.id, '000002', 40.0)
    _seed_box(db, '000001', {'大盘成长': 60.0, '大盘价值': 40.0})
    _seed_box(db, '000002', {'固收风格': 100.0})

    result = asc.build_advisor_style_compare(db, 'ZHTEST', 1)
    advisor = result['advisor']
    assert advisor['has_snapshot'] is True
    assert advisor['coverage_pct'] == pytest.approx(100.0)
    assert _by_key(advisor['directions']) == {
        '大盘': 60.0,
        '中盘': 0.0,
        '小盘': 0.0,
        '港股': 0.0,
        '固收': 40.0,
    }
    assert advisor['missing'] == []


def test_missing_box_excluded_from_weight_but_lowers_coverage(db):
    """无箱体的基金不计入加权，但必须把覆盖率拉低并进 missing——不能按 100% 呈现。"""
    portfolio = _seed_portfolio(db, code='ZHMISS')
    _seed_holding(db, portfolio.id, '000001', 75.0)
    _seed_holding(db, portfolio.id, '000002', 25.0)
    _seed_box(db, '000001', {'小盘成长': 100.0})

    advisor = asc.build_advisor_style_compare(db, 'ZHMISS', 1)['advisor']
    # 分母是有箱体的权重 75 → 小盘仍为 100%，但覆盖率只有 75%
    assert _by_key(advisor['directions'])['小盘'] == pytest.approx(100.0)
    assert advisor['coverage_pct'] == pytest.approx(75.0)
    assert advisor['covered_weight_pct'] == pytest.approx(75.0)
    assert [m['fund_code'] for m in advisor['missing']] == ['000002']


def test_no_snapshot_returns_empty_directions_not_zeros(db):
    """组合存在但没有持仓快照：方向为空，而不是五个 0（那是「都不配」的结论）。"""
    _seed_portfolio(db, code='ZHEMPTY')
    advisor = asc.build_advisor_style_compare(db, 'ZHEMPTY', 1)['advisor']
    assert advisor['has_snapshot'] is False
    assert advisor['directions'] == []
    assert advisor['coverage_pct'] is None


def test_unknown_portfolio_raises_value_error(db):
    with pytest.raises(ValueError):
        asc.build_advisor_style_compare(db, 'NOSUCHCODE', 1)


# ── 我侧 ──


def _seed_my_holding(db, symbol, asset_type, market_value_yuan, box=None):
    """造一条我的持仓（quantity 单位 0.0001 份，current_price 单位分）。"""
    db.add(
        Position(
            family_id=1,
            symbol=symbol,
            name=f'我的{symbol}',
            asset_type=asset_type,
            quantity=1000000,
            current_price=int(market_value_yuan * 100),
        )
    )
    db.flush()
    if box:
        _seed_box(db, symbol[:6], box)


def test_mine_side_groups_eight_styles_into_five(db):
    """八分类求和成五组：大盘成长 + 大盘价值 → 大盘，依此类推。

    夹具的每只箱体合计恒为 100（上游口径），三只等市值 →
    五组占比 = 各组风格值之和 / 3。
    """
    _seed_portfolio(db, code='ZMINE')
    _seed_my_holding(db, '000101', 'fund', 1000, {'大盘成长': 30.0, '大盘价值': 20.0, '中盘成长': 50.0})
    _seed_my_holding(db, '000102', 'fund', 1000, {'中盘价值': 40.0, '小盘成长': 60.0})
    _seed_my_holding(db, '000103', 'etf', 1000, {'港股风格': 70.0, '固收风格': 30.0})

    mine = asc.build_advisor_style_compare(db, 'ZMINE', 1)['mine']
    assert mine['degraded'] is False
    assert _by_key(mine['directions']) == {
        '大盘': pytest.approx(16.67, abs=0.01),
        '中盘': pytest.approx(30.0, abs=0.01),
        '小盘': pytest.approx(20.0, abs=0.01),
        '港股': pytest.approx(23.33, abs=0.01),
        '固收': pytest.approx(10.0, abs=0.01),
    }
    assert mine['total_market_value_cents'] == 300000


def test_mine_side_degraded_on_error(monkeypatch, db):
    """我侧取数失败 → degraded=True 且方向为空，**不拿 0 冒充**。"""
    _seed_portfolio(db, code='ZDEG')

    def boom(*_args, **_kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(asc, 'portfolio_style_exposure', boom)
    mine = asc.build_advisor_style_compare(db, 'ZDEG', 1)['mine']
    assert mine['degraded'] is True
    assert mine['directions'] == []
    assert mine['total_market_value_cents'] == 0
