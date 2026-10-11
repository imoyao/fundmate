# -*- coding: utf-8 -*-
"""投顾组合资料聚合（#1975 · 详情页投顾组合区块）。

重点覆盖四件事：

1. **按 `code` 精确命中** —— `code` 是 `advisor_portfolios` 的表级唯一键（本机实测
   105/105 唯一），而 `name` 没有唯一约束，故入参用 code；
2. **实测 0% 填充的字段返回 None 而不是 0** —— `strategy_type` / `cum_return` /
   `running_days` / `benchmark` / `excess_return` 在生产库填充率**全为 0%**，
   返回 0 会被前端读成「累计收益 0%」这类假数值；
3. **有值时正常透出** —— 防「一律 None」的实现蒙混过关：本机实测 `org_name` /
   `risk_level` / `annual_return` / 区间收益 / 回撤 / 波动率 / 夏普 填充率 91~100%，
   这些正是区块的主要内容，不能一起被降级；
4. **持仓 / 调仓计数** —— 前端据此决定那一块要不要渲染、请求要不要发（实测调仓只覆盖
   **16/105** 个组合，多数组合点进来「没有调仓」才是正常态）。

⚠️ 测试数据一律造在 **market 域**会话：`advisor_portfolios` 及附属表属 market 域，
生产下是独立引擎（同 `test_manager_profile.py`）。
"""

from contextlib import closing
from datetime import date

from app.core.db_factory import market_session_factory
from app.domains.funds.models import AdvisorAdjustHistory, AdvisorHolding, AdvisorPortfolio
from app.services.advisor_profile import build_advisor_profile

PROFILE_URL = '/api/products/advisor-profile/?code='


def _seed_advisor(code, name='测试投顾组合', platform='QIEMAN', **fields):
    """建投顾组合，返回 code（标量）。

    只回 code 而非 ORM 实例：commit 后实例属性过期（expire_on_commit），
    session 关闭后再取属性会抛 DetachedInstanceError（同 `test_manager_profile.py`）。
    """
    with closing(market_session_factory()()) as db:
        row = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code == code).first()
        if row is None:
            row = AdvisorPortfolio(code=code, name=name, platform=platform, **fields)
            db.add(row)
        else:
            row.name = name
            row.platform = platform
            for key, value in fields.items():
                setattr(row, key, value)
        db.commit()
        return code


def _portfolio_id(code):
    with closing(market_session_factory()()) as db:
        row = db.query(AdvisorPortfolio.id).filter(AdvisorPortfolio.code == code).first()
        return row[0] if row else None


def _seed_holding(code, fund_code, as_of_date=date(2026, 1, 5), **fields):
    """建一条成分持仓。NOT NULL：portfolio_id / as_of_date / fund_code / source。"""
    pid = _portfolio_id(code)
    with closing(market_session_factory()()) as db:
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
                AdvisorHolding(portfolio_id=pid, fund_code=fund_code, as_of_date=as_of_date, source='qieman', **fields)
            )
            db.commit()


def _seed_adjust(code, adjust_date, fund_code, **fields):
    """建一条调仓明细。NOT NULL：portfolio_id / adjust_date / fund_code / source。"""
    pid = _portfolio_id(code)
    with closing(market_session_factory()()) as db:
        exists = (
            db.query(AdvisorAdjustHistory)
            .filter(
                AdvisorAdjustHistory.portfolio_id == pid,
                AdvisorAdjustHistory.adjust_date == adjust_date,
                AdvisorAdjustHistory.fund_code == fund_code,
            )
            .first()
        )
        if exists is None:
            db.add(
                AdvisorAdjustHistory(
                    portfolio_id=pid,
                    adjust_date=adjust_date,
                    fund_code=fund_code,
                    source='qieman',
                    **fields,
                )
            )
            db.commit()


# ── 基本命中 ──────────────────────────────────────────────────────────────


def test_returns_none_for_unknown_code():
    """组合不存在返回 None（由调用方转 404），不抛异常。"""
    with closing(market_session_factory()()) as db:
        assert build_advisor_profile(db, 'NOSUCHCODE') is None


def test_raises_on_empty_code():
    """空入参抛 ValueError（由调用方转 400）。"""
    with closing(market_session_factory()()) as db:
        try:
            build_advisor_profile(db, '   ')
        except ValueError:
            return
        raise AssertionError('空 code 应抛 ValueError')


def test_lookup_by_code():
    """按 code 命中，档案字段原样透出。"""
    _seed_advisor('ZH900001', name='测试组合甲', platform='QIEMAN', org_name='盈米基金', risk_level='中风险')

    with closing(market_session_factory()()) as db:
        data = build_advisor_profile(db, 'ZH900001')

    assert data['code'] == 'ZH900001'
    assert data['name'] == '测试组合甲'
    assert data['platform'] == 'QIEMAN'
    assert data['org_name'] == '盈米基金'
    assert data['risk_level'] == '中风险'


# ── 降级契约：0% 填充字段必须是 None（不是 0）─────────────────────────────


def test_unfilled_fields_are_none_not_zero():
    """实测 0% 填充的字段必须是 None —— 0 会被前端读成「累计收益 0%」这种假数值。"""
    _seed_advisor('ZH900002', name='只有必填字段的组合')

    with closing(market_session_factory()()) as db:
        data = build_advisor_profile(db, 'ZH900002')

    for field in ('strategy_type', 'cum_return', 'running_days', 'benchmark', 'excess_return'):
        assert field in data, f'{field} 必须返回 key（固定契约），前端才知道该位置要降级「—」'
        assert data[field] is None, f'{field} 未落库时必须 None，不能是 0'


def test_filled_metric_fields_are_returned_as_float():
    """有值必须透出且为 float（防「一律 None」蒙混，也防 Decimal 直接进 JSON）。"""
    _seed_advisor(
        'ZH900003',
        name='指标齐全的组合',
        annual_return=12.34,
        return_1m=1.23,
        return_1y=9.87,
        max_drawdown=-15.6,
        volatility=18.2,
        sharpe_ratio=0.85,
    )

    with closing(market_session_factory()()) as db:
        data = build_advisor_profile(db, 'ZH900003')

    assert data['annual_return'] == 12.34
    assert isinstance(data['annual_return'], float)
    assert data['return_1m'] == 1.23
    assert data['return_1y'] == 9.87
    assert data['max_drawdown'] == -15.6
    assert data['volatility'] == 18.2
    assert data['sharpe_ratio'] == 0.85
    # 同一批里没值的仍为 None（不能因为「有值就整批透出」）
    assert data['return_ytd'] is None


def test_dates_are_iso_strings():
    """成立日 / 净值日转 ISO 字符串；净值转 float。"""
    _seed_advisor('ZH900004', name='带日期的组合', estab_date=date(2020, 5, 20), nav=1.2345, nav_date=date(2026, 1, 5))

    with closing(market_session_factory()()) as db:
        data = build_advisor_profile(db, 'ZH900004')

    assert data['estab_date'] == '2020-05-20'
    assert data['nav_date'] == '2026-01-05'
    assert data['nav'] == 1.2345


# ── 持仓 / 调仓计数 ───────────────────────────────────────────────────────


def test_counts_reflect_child_tables():
    """计数让前端决定那一块要不要渲染、请求要不要发。

    实测调仓只覆盖 16/105 个组合 —— 多数组合点进来「没有调仓」才是正常态，
    故计数必须准确：为 0 时前端直接显示空态，而不是先白发两个请求。
    """
    _seed_advisor('ZH900005', name='有持仓的组合')
    _seed_holding('ZH900005', '000001')
    _seed_holding('ZH900005', '000002')
    _seed_adjust('ZH900005', date(2026, 1, 5), '000001')

    _seed_advisor('ZH900006', name='无持仓无调仓的组合')

    with closing(market_session_factory()()) as db:
        with_children = build_advisor_profile(db, 'ZH900005')
        without_children = build_advisor_profile(db, 'ZH900006')

    assert with_children['holding_count'] == 2
    assert with_children['adjust_count'] == 1
    assert without_children['holding_count'] == 0
    assert without_children['adjust_count'] == 0


def test_counts_are_scoped_to_this_portfolio():
    """计数只算本组合 —— 串到别的组合会让空态判断失效。"""
    _seed_advisor('ZH900007', name='组合A')
    _seed_advisor('ZH900008', name='组合B')
    _seed_holding('ZH900008', '000001')

    with closing(market_session_factory()()) as db:
        data = build_advisor_profile(db, 'ZH900007')

    assert data['holding_count'] == 0


# ── 端点级 ────────────────────────────────────────────────────────────────


def test_endpoint_returns_envelope(client):
    _seed_advisor('ZH900009', name='端点组合', org_name='测试机构')

    resp = client.get(PROFILE_URL + 'ZH900009')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['code'] == 'ZH900009'
    assert data['name'] == '端点组合'


def test_endpoint_404_for_unknown_code(client):
    resp = client.get(PROFILE_URL + 'NOSUCHCODE')
    assert resp.status_code == 404


def test_endpoint_422_for_missing_code(client):
    """缺 code 由 pydantic 查询契约拦下 → 422（与 `/trend/`、`/stock-profile/` 同一入口约定）。

    关键不是 400 还是 422，而是**不能是 500、也不能是 404**：
    「参数没传」与「组合不存在」必须分开，否则前端分不清「我的链接错了」还是「这个组合没收录」。
    """
    resp = client.get('/api/products/advisor-profile/')

    assert resp.status_code == 422
    assert resp.get_json()['error_code'] == 1001  # ErrorCode.INVALID_PARAMS
