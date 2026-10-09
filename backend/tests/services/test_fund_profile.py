# -*- coding: utf-8 -*-
"""基金资料聚合（#1968 · 详情页基金详情区块）。

重点覆盖三件事：
1. **日涨跌由最近两日净值算出**（funds 域没有端点直出这个值）；
2. **只有一条净值时返回 None 而不是 0** ——「没数据」不能被读成「今天没涨」；
3. **基金经理从关联表取**（funds 域此前没有任何端点能给出「某只基金的经理」）。

⚠️ 测试数据一律造在 **market 域**会话：`funds` / `daily_worth` 属 market 域，生产下是
独立引擎，端点与「读市场数据必须经 market_session_factory」的硬规则都要求如此。
"""

from contextlib import closing
from datetime import date, timedelta

from app.core.db_factory import market_session_factory
from app.domains.funds.models import DailyWorth, Fund, FundManager, Manager
from app.services.fund_profile import build_fund_profile

PROFILE_URL = '/api/products/fund-profile/?code=004369'


def _seed_fund(fund_code='004369', name='测试基金'):
    with closing(market_session_factory()()) as db:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if fund is None:
            fund = Fund(fund_code=fund_code, name=name)
            db.add(fund)
            db.flush()
        return fund


def _seed_navs(fund_code='004369', values=(2.0, 2.1)):
    """写入若干日净值（values[0] 最新）。

    先清该 code 的历史净值：conftest 的 ``clean_db`` 只清当前会话引擎实际存在的表，
    **market 域残留不保证被清**，而本服务取的是「最近两条」——残留会直接把断言改掉
    （想让只有 1 条净值，结果拿到上一轮留下的 3 条）。
    """
    with closing(market_session_factory()()) as db:
        db.query(DailyWorth).filter(DailyWorth.fund_code == fund_code).delete()
        db.flush()
        base = date.today()
        db.add_all(
            DailyWorth(fund_code=fund_code, date=base - timedelta(days=i), unit_nav=value)
            for i, value in enumerate(values)
        )
        db.commit()


def _seed_manager(fund, mgr_code='MGR_001', name='张三', is_classic=False):
    with closing(market_session_factory()()) as db:
        manager = db.query(Manager).filter(Manager.mgr_code == mgr_code).first()
        if manager is None:
            manager = Manager(mgr_code=mgr_code, name=name)
            db.add(manager)
            db.flush()
        linked = (
            db.query(FundManager.id).filter(FundManager.fund_id == fund.id, FundManager.mgr_id == manager.id).first()
        )
        if linked is None:
            db.add(FundManager(fund_id=fund.id, mgr_id=manager.id, is_classic=is_classic))
            db.commit()


def _market_db():
    return market_session_factory()()


# ── service 层 ────────────────────────────────────────────────────────
def test_profile_returns_nav_and_change_pct():
    """首屏三项：单位净值 + 净值日期 + 日涨跌。"""
    _seed_fund()
    _seed_navs(values=(2.10, 2.00))

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert profile['unit_nav'] == 2.10
    assert profile['prev_unit_nav'] == 2.00
    assert profile['nav_date'] and profile['prev_nav_date']
    # (2.10 - 2.00) / 2.00 = 5.0%
    assert profile['change_pct'] == 5.0


def test_change_pct_is_none_when_only_one_nav():
    """只有一条净值 → 日涨跌为 None，不是 0（「没数据」≠「没涨」）。"""
    _seed_fund()
    _seed_navs(values=(2.00,))

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert profile['unit_nav'] == 2.00
    assert profile['change_pct'] is None


def test_profile_returns_none_for_unknown_fund():
    with closing(_market_db()) as db:
        assert build_fund_profile(db, 'NOPE00') is None


def test_profile_lists_managers():
    """经理从 fund_managers 关联表取（此前无任何端点能给出）。"""
    fund = _seed_fund()
    _seed_manager(fund)

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert '张三' in [m['name'] for m in profile['managers']]


def test_manager_is_classic_read_from_link_table():
    """代表作品标记只存在于 fund_managers 关联表，须经关联表 join 才能取到。

    顺带锁住「True / False 都要如实返回」：``bool(None)`` 也应为 False，前端据此决定
    是否挂「代表作」徽标，若把缺值当成 True 会给所有经理都打上徽标。
    """
    fund = _seed_fund()
    _seed_manager(fund, mgr_code='MGR_CLASSIC', name='李四', is_classic=True)
    _seed_manager(fund, mgr_code='MGR_PLAIN', name='王五', is_classic=False)

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    flags = {m['name']: m['is_classic'] for m in profile['managers']}
    assert flags['李四'] is True
    assert flags['王五'] is False


def test_fee_rates_degrade_to_none():
    """费率取不到时降级为 None，不让整个资料 500。"""
    _seed_fund()
    _seed_navs(values=(2.0, 2.1))

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert 'fee_rates' in profile


# ── 端点 ──────────────────────────────────────────────────────────────
def test_endpoint_returns_404_for_unknown_fund(client, db):
    resp = client.get('/api/products/fund-profile/?code=NOPE00')

    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == 1002  # ErrorCode.RESOURCE_NOT_FOUND


def test_endpoint_returns_profile(client, db):
    _seed_fund()
    _seed_navs(values=(2.10, 2.00))

    resp = client.get(PROFILE_URL)

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['fund_code'] == '004369'
    assert data['unit_nav'] == 2.10
    assert data['change_pct'] == 5.0


def test_endpoint_blank_code_returns_400(client, db):
    """缺 code → 400（不是 404：参数缺失与「不存在」要分开）。"""
    resp = client.get('/api/products/fund-profile/')

    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001  # ErrorCode.INVALID_PARAMS
