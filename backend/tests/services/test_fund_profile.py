# -*- coding: utf-8 -*-
"""基金资料聚合（#1968 · 详情页基金详情区块）。

重点覆盖三件事：
1. **日涨跌由最近两日净值算出**（funds 域没有端点直出这个值）；
2. **只有一条净值时返回 None 而不是 0** ——「没数据」不能被读成「今天没涨」；
3. **基金经理从关联表取**（funds 域此前没有任何端点能给出「某只基金的经理」）。

另覆盖第 4 件（#1440）：**晨星 3 年期评级三列**随资料一并带出，且「无评级」降级为
None 而不是 0（详情页「基金资料」区展示用）。

⚠️ 测试数据一律造在 **market 域**会话：`funds` / `daily_worth` 属 market 域，生产下是
独立引擎，端点与「读市场数据必须经 market_session_factory」的硬规则都要求如此。
"""

from contextlib import closing
from datetime import date, timedelta

import pytest

from app.core.db_factory import market_session_factory
from app.domains.funds.models import DailyWorth, Fund, FundManager, Manager
from app.services import fund_profile as fund_profile_module
from app.services.fund_profile import build_fund_profile

PROFILE_URL = '/api/products/fund-profile/?code=004369'


@pytest.fixture(autouse=True)
def _no_network_backfill(monkeypatch):
    """切断「基金公司按需回填」的外部请求（#2037 方案 A）。

    本文件此前是纯本地测试；#2037 之后 `build_fund_profile` 在 `company_id` 为空时会
    调 `ensure_fund_company` 打东财接口。不隔离的话，单测会在每次打开 `004369` 时
    真发一次外网请求——慢、且随上游波动随机变红（失败降级 None 就会让断言偶尔失败）。

    回填逻辑本身由 `tests/services/test_fund_company_backfill.py` 单独覆盖（那里用
    monkeypatch 替换取数口，不触网），此处只保证聚合层测试与网络无关。
    """
    monkeypatch.setattr(fund_profile_module, 'ensure_fund_company', lambda db, code: None)


def _seed_fund(fund_code='004369', name='测试基金'):
    """确保基金存在，返回其 **id**（int，不是 ORM 实例）。

    两个容易踩的点：

    1. **必须 commit**，只 ``flush`` 不够——``closing`` 退出即关 session，未提交的写入
       会被回滚，于是 ``funds`` 里查不到该 code，随后 ``_seed_navs`` 插 ``daily_worth``
       就撞外键（``daily_worth.fund_code`` 外键指向 ``funds.fund_code``）：
       ``sqlite3.IntegrityError: FOREIGN KEY constraint failed``。
    2. **只回 id**：commit 后实例属性已过期（expire_on_commit），session 关闭后再取
       ``fund.id`` 会抛 DetachedInstanceError。
    """
    with closing(market_session_factory()()) as db:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if fund is None:
            fund = Fund(fund_code=fund_code, name=name)
            db.add(fund)
            db.commit()
        return fund.id


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


def _seed_manager(fund_id, mgr_code='MGR_001', name='张三', is_classic=False):
    """关联一只基金与一位经理（``fund_managers``），返回是否新建的关联行。"""
    with closing(market_session_factory()()) as db:
        manager = db.query(Manager).filter(Manager.mgr_code == mgr_code).first()
        if manager is None:
            manager = Manager(mgr_code=mgr_code, name=name)
            db.add(manager)
            db.flush()
        linked = (
            db.query(FundManager.id).filter(FundManager.fund_id == fund_id, FundManager.mgr_id == manager.id).first()
        )
        if linked is None:
            db.add(FundManager(fund_id=fund_id, mgr_id=manager.id, is_classic=is_classic))
            db.commit()


def _market_db():
    return market_session_factory()()


# ── service 层 ────────────────────────────────────────────────────────
def test_profile_returns_nav_and_change_pct():
    """首屏三项：单位净值 + 净值日期 + 日涨跌。"""
    _seed_fund()
    _seed_navs(values=(2.10, 2.00))

    # 锁死回归（#1968 CI 曾整文件红）：种子基金必须**已提交**落库——
    # daily_worth.fund_code 有外键指向 funds.fund_code，若种子只 flush 不 commit，
    # closing 关 session 时写入被回滚，插净值就撞 FOREIGN KEY constraint failed。
    with closing(_market_db()) as db:
        assert db.query(Fund).filter(Fund.fund_code == '004369').first() is not None

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
    fund_id = _seed_fund()
    _seed_manager(fund_id)

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert '张三' in [m['name'] for m in profile['managers']]


def test_manager_is_classic_read_from_link_table():
    """代表作品标记只存在于 fund_managers 关联表，须经关联表 join 才能取到。

    顺带锁住「True / False 都要如实返回」：``bool(None)`` 也应为 False，前端据此决定
    是否挂「代表作」徽标，若把缺值当成 True 会给所有经理都打上徽标。
    """
    fund_id = _seed_fund()
    _seed_manager(fund_id, mgr_code='MGR_CLASSIC', name='李四', is_classic=True)
    _seed_manager(fund_id, mgr_code='MGR_PLAIN', name='王五', is_classic=False)

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    flags = {m['name']: m['is_classic'] for m in profile['managers']}
    assert flags['李四'] is True
    assert flags['王五'] is False


def test_source_is_site_name_not_internal_table():
    """来源必须是**站点名**（#1969）：此前脚注写的是 `daily_worth` / `funds` 表名。

    用户看不懂表名，脚注要说「哪个网站」。基金净值 / 费率 / 基础资料整条链路都走
    天天基金，故固定为「天天基金」。
    """
    _seed_fund()
    _seed_navs(values=(2.10, 2.00))

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert profile['source'] == '天天基金'
    assert 'daily_worth' not in str(profile['source'])


def test_fee_rates_degrade_to_none():
    """费率取不到时降级为 None，不让整个资料 500。"""
    _seed_fund()
    _seed_navs(values=(2.0, 2.1))

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert 'fee_rates' in profile


# ── 晨星评级（#1440）────────────────────────────────────────────────────
def _seed_rating(fund_code='004369', rating=None, delta=None, asof=None):
    """写入晨星评级三列（#1440）。

    **每次都显式覆盖**（含 None）：`_seed_fund` 只在基金不存在时才建，market 域
    残留不保证被 conftest 清掉——不覆盖的话，本轮的 None 断言会被上一轮残留
    的评级值改掉（与 `_seed_navs` 先删后插同因）。
    """
    with closing(market_session_factory()()) as db:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if fund is None:
            return
        fund.morningstar_rating = rating
        fund.morningstar_rating_delta = delta
        fund.morningstar_rating_asof = asof
        db.commit()


def test_profile_carries_morningstar_rating():
    """资料页带出晨星 3 年期评级三列：值 + 较上期变化 + 快照日期。

    数据源是东财评级总汇页，与净值/费率链路**不同源**——故三列单列，
    不并入页脚的 `source` 标签（前端在格内自带「3年期」口径）。
    """
    _seed_fund()
    _seed_rating(rating=3, delta=-1, asof=date(2026, 10, 24))

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert profile['morningstar_rating'] == 3
    assert profile['morningstar_rating_delta'] == -1
    assert profile['morningstar_rating_asof'] == '2026-10-24'


def test_profile_rating_none_when_not_collected():
    """未采集到评级 → 三字段全 None。

    「没有评级」是货基 / 新基金的**常态**，不是故障；显示「0 星」是编造数据。
    """
    _seed_fund()
    _seed_rating(rating=None, delta=None, asof=None)

    with closing(_market_db()) as db:
        profile = build_fund_profile(db, '004369')

    assert profile is not None
    assert profile['morningstar_rating'] is None
    assert profile['morningstar_rating_delta'] is None
    assert profile['morningstar_rating_asof'] is None


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
