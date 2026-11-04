# -*- coding: utf-8 -*-
"""首页「最新收益」卡的数据出口（#今日收益卡）。

钉住四件事——它们都是「看起来正常、其实在编数字」的高发区：

1. **卡内自洽**：Σ 分项盈亏 ≡ 合计，Σ 分项市值 ≡ 投资类资产；
2. **估 / 确认**：官方净值缺失时用收盘估值定格并标 `estimated`，
   官方到位后同一场景翻 `confirmed`（用户 2026-11-03 拍板的展示契约）；
3. **不把「还没数据」画成 0**：今日无任何当日报价时回退到最近有价的一天，
   并给出 `is_today=false`，由前端标注「截至某日」；
4. **无持仓 != 零收益**：`total_pnl` 为 None，不是 0.00。
"""

import datetime as dt

import pytest

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.funds.models import DailyWorth, FundValuationDaily
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.today_pnl import build_today_pnl

TODAY = dt.date(2026, 11, 3)  # 周二
PREV = dt.date(2026, 11, 2)  # 周一
OLDER = dt.date(2026, 10, 30)  # 上周五（差分基准）


@pytest.fixture
def frozen_today(monkeypatch):
    """钉住「今天」并让交易日历按工作日判定（周末跑测试也稳定）。

    两处都要打：`today_pnl` 与 `pnl_calendar` 各自 `from ... import now_shanghai`，
    只打一处会得到「服务认为今天是 A、引擎认为今天是 B」的错位。
    """
    import app.services.pnl_calendar as calendar
    import app.services.today_pnl as service

    fixed = dt.datetime(2026, 11, 3, 16, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    monkeypatch.setattr(calendar, 'now_shanghai', lambda: fixed)
    monkeypatch.setattr(service, 'now_shanghai', lambda: fixed)
    monkeypatch.setattr(calendar, 'is_trading_day', lambda d: d.weekday() < 5)
    return fixed


def _nav(db, code, day, nav):
    db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav))
    db.commit()


def _bar(db, sec_id, symbol, day, close):
    db.add(PriceHistory(security_id=sec_id, symbol=symbol, trade_date=day, close=close, adj_close=close))
    db.commit()


def _seed_stock(db, make_position, make_transaction, symbol='SH600519', quantity=100, cost=10.0):
    sec = Security(symbol=symbol, name='测试股', market='CN_A', type='stock')
    db.add(sec)
    db.commit()
    # 账户页 / 首页市值都走 `market_value_cents`（读 current_price 快照价）。
    # 夹具必须把快照价写成与当日收盘价一致，否则会造出「引擎有价、账本没价」
    # 的假数据，测出来的市值少一整类。
    pos = make_position(
        symbol=symbol,
        name='测试股',
        quantity=quantity,
        avg_price=cost,
        asset_type='stock',
        current_price=11.0,
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=quantity,
        price=cost,
        confirm_date=TODAY - dt.timedelta(days=60),
        symbol=symbol,
    )
    return sec, pos


def _seed_fund(db, make_position, make_transaction, code='000001', quantity=1000, cost=1.0):
    # 场外优先用 `NavService` 最新净值；没有净值行时 `market_value_cents` 回退
    # current_price，故这里也要给出与当日净值一致的快照价。
    pos = make_position(
        symbol=code,
        name='测试基金',
        quantity=quantity,
        avg_price=cost,
        asset_type='fund',
        current_price=1.1,
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=quantity,
        price=cost,
        confirm_date=TODAY - dt.timedelta(days=60),
        symbol=code,
    )
    return pos


def test_分项之和等于合计且确认态(db, make_position, make_transaction, frozen_today):
    """股票涨、基金涨，两类都拿到当日官方价 ⇒ confirmed，Σ 分项 ≡ 合计。"""
    sec, _ = _seed_stock(db, make_position, make_transaction)  # 100 股，成本 10 → 现价 11
    _seed_fund(db, make_position, make_transaction)  # 1000 份，成本 1 → 净值 1.1
    _bar(db, sec.id, 'SH600519', OLDER, 10.0)
    _bar(db, sec.id, 'SH600519', PREV, 10.0)
    _bar(db, sec.id, 'SH600519', TODAY, 11.0)
    _nav(db, '000001', OLDER, 1.0)
    _nav(db, '000001', PREV, 1.0)
    _nav(db, '000001', TODAY, 1.1)

    data = build_today_pnl(db, family_id=1)

    assert data['date'] == TODAY.isoformat()
    assert data['is_today'] is True
    assert data['status'] == 'confirmed'
    assert data['total_pnl'] == pytest.approx(200.0)
    assert data['total_rate'] == pytest.approx(10.0)  # 200 / 上一基准日 2000
    assert data['invested_value'] == pytest.approx(2200.0)

    classes = {c['key']: c for c in data['classes']}
    assert classes['stock']['pnl'] == pytest.approx(100.0)
    assert classes['fund']['pnl'] == pytest.approx(100.0)
    assert classes['stock']['market_value'] == pytest.approx(1100.0)
    assert classes['fund']['market_value'] == pytest.approx(1100.0)
    # 卡内自洽：分项之和 = 合计（不是前端再算一遍，是这里就该成立）
    assert sum(c['pnl'] for c in data['classes']) == pytest.approx(data['total_pnl'])
    assert sum(c['market_value'] for c in data['classes']) == pytest.approx(data['invested_value'])

    # 盘中价格替换的输入：代码 / 大类 / 份额 / 当日价（元）
    holdings = {h['symbol']: h for h in data['holdings']}
    assert holdings['SH600519']['class'] == 'stock'
    assert holdings['SH600519']['price'] == pytest.approx(11.0)
    assert holdings['SH600519']['quantity'] == pytest.approx(100.0)
    assert holdings['000001']['class'] == 'fund'
    assert holdings['000001']['price'] == pytest.approx(1.1)


def test_官方净值未出时用估值定格并标估(db, make_position, make_transaction, frozen_today):
    """今日官方净值缺失、但有收盘估值定格 ⇒ 金额用估值算，状态 estimated（徽标「估」）。"""
    _seed_fund(db, make_position, make_transaction)
    _nav(db, '000001', OLDER, 1.0)
    _nav(db, '000001', PREV, 1.0)
    db.add(
        FundValuationDaily(
            fund_code='000001',
            est_date=TODAY,
            estimated_nav=1.05,
            change_pct=5.0,
            source_time='2026-11-03 15:15',
            status='estimated',
        )
    )
    db.commit()

    data = build_today_pnl(db, family_id=1)

    assert data['status'] == 'estimated'
    assert data['classes'][0]['status'] == 'estimated'
    assert data['total_pnl'] == pytest.approx(50.0)  # (1.05 − 1.0) × 1000


def test_官方净值到位后同一场景翻确认(db, make_position, make_transaction, frozen_today):
    """估值行仍在库里，但官方净值已落 `daily_worth` ⇒ 必须优先官方、状态 confirmed。

    这是「确定后更新为确定值」的判据：估值只在官方缺失时被采信（#2141）。
    """
    _seed_fund(db, make_position, make_transaction)
    _nav(db, '000001', OLDER, 1.0)
    _nav(db, '000001', PREV, 1.0)
    _nav(db, '000001', TODAY, 1.02)  # 官方净值到了
    db.add(
        FundValuationDaily(
            fund_code='000001',
            est_date=TODAY,
            estimated_nav=1.05,  # 估值与官方不一致，官方优先
            change_pct=5.0,
            status='estimated',
        )
    )
    db.commit()

    data = build_today_pnl(db, family_id=1)

    assert data['status'] == 'confirmed'
    assert data['total_pnl'] == pytest.approx(20.0)  # (1.02 − 1.0) × 1000


def test_今日无当日报价时回退到最近有价日(db, make_position, make_transaction, frozen_today):
    """今天一个当日价都没有（盘中 / 净值未出 / 同步没跑）⇒ 不显示 0.00，回退上一交易日。"""
    _seed_fund(db, make_position, make_transaction)
    _nav(db, '000001', OLDER, 1.0)
    _nav(db, '000001', PREV, 1.1)  # 上一交易日净值
    # 今天没有任何净值行 / 估值行

    data = build_today_pnl(db, family_id=1)

    assert data['date'] == PREV.isoformat()
    assert data['is_today'] is False
    assert data['total_pnl'] == pytest.approx(100.0)  # 上一交易日真实收益，不是今天的 0


def test_无持仓时不给零收益(db, frozen_today):
    """没有持仓 ⇒ `total_pnl` 为 None（算不了），不是 0.00（没赚没亏）。"""
    data = build_today_pnl(db, family_id=1)

    assert data['total_pnl'] is None
    assert data['classes'] == []
    assert data['status'] == 'no_data'
    # 占比同属「算不了」：给 None 让前端隐藏整句，而不是渲染「占家庭总资产 0.0%」
    assert data['invested_ratio_of_assets'] is None


def test_可转债与ETF计入场内权益(db, make_position, make_transaction, frozen_today):
    """2026-11-04（D77）：`asset_class` 按定价方式分桶，bond / etf 都进「场内权益」。

    此前 `bond` 归 other（完全不进卡面）、`etf` 归 fund（与场外基金混在
    「基金」列，而它其实有实时价、盘中会跳）。两者与股票同属交易所报价，
    当日盈亏口径完全一致。
    """
    etf = Security(symbol='SH510300', name='沪深300ETF', market='CN_A', type='etf')
    bond = Security(symbol='SH110081', name='测试转债', market='CN_A', type='bond')
    db.add_all([etf, bond])
    db.commit()

    pos_etf = make_position(symbol='SH510300', name='沪深300ETF', quantity=100, avg_price=4.0, asset_type='etf')
    make_transaction(
        position_id=pos_etf.id,
        ledger_id=pos_etf.ledger_id,
        txn_type='buy',
        quantity=100,
        price=4.0,
        confirm_date=TODAY - dt.timedelta(days=60),
        symbol='SH510300',
    )
    pos_bond = make_position(symbol='SH110081', name='测试转债', quantity=10, avg_price=100.0, asset_type='bond')
    make_transaction(
        position_id=pos_bond.id,
        ledger_id=pos_bond.ledger_id,
        txn_type='buy',
        quantity=10,
        price=100.0,
        confirm_date=TODAY - dt.timedelta(days=60),
        symbol='SH110081',
    )

    for sec, symbol, prev, today in ((etf, 'SH510300', 4.0, 4.1), (bond, 'SH110081', 100.0, 101.0)):
        _bar(db, sec.id, symbol, OLDER, prev)
        _bar(db, sec.id, symbol, PREV, prev)
        _bar(db, sec.id, symbol, TODAY, today)

    data = build_today_pnl(db, family_id=1)

    classes = {c['key']: c for c in data['classes']}
    assert list(classes) == ['stock'], 'ETF 与可转债同属场内权益，不应再单列「基金」'
    assert classes['stock']['label'] == '场内权益'
    # ETF：(4.1 − 4.0) × 100 = 10；转债：(101 − 100) × 10 = 10
    assert classes['stock']['pnl'] == pytest.approx(20.0)
    assert data['total_pnl'] == pytest.approx(20.0)
    assert sum(c['pnl'] for c in data['classes']) == pytest.approx(data['total_pnl'])

    holdings = {h['symbol']: h for h in data['holdings']}
    assert holdings['SH510300']['class'] == 'stock'
    assert holdings['SH110081']['class'] == 'stock'


def test_占比由后端直出且分子分母与卡面同源(db, make_position, make_transaction, frozen_today):
    """`share_of_invested` / `invested_ratio_of_assets` 必须在后端算好。

    卡面同时显示「股票 1,100 / 基金 1,100 / 投资类资产 2,200 / 家庭总资产 4,000」，
    四个数各自都能被用户心算验算。若前端另算一遍，四舍五入一旦不同就会出现
    「金额对得上、百分比差 0.1」——这类观感 bug 无法靠对账解释。
    """
    sec, stock_pos = _seed_stock(db, make_position, make_transaction)  # 100 股 × 11 = 1,100
    fund_pos = _seed_fund(db, make_position, make_transaction)  # 1,000 份 × 1.1 = 1,100
    _bar(db, sec.id, 'SH600519', OLDER, 10.0)
    _bar(db, sec.id, 'SH600519', PREV, 10.0)
    _bar(db, sec.id, 'SH600519', TODAY, 11.0)
    _nav(db, '000001', OLDER, 1.0)
    _nav(db, '000001', PREV, 1.0)
    _nav(db, '000001', TODAY, 1.1)
    # 分子（`market_value_cents` 逐持仓求和）与分母（`family_totals`）现在同口径；
    # 夹具仍显式写一次快照价，是为了钉住「价格序列与持仓快照价一致」这个前提
    # （历史上这里踩过占比 122% 的假象：分子 2,200、分母 1,800）。
    stock_pos.current_price = Money.yuan_to_price_units(11.0)
    fund_pos.current_price = Money.yuan_to_price_units(1.1)
    db.commit()
    # 家里还有 1,800 现金 ⇒ 家庭总资产 4,000，投资类资产只占 55%
    db.add(
        Asset(
            user_id=1,
            major_category='cash',
            name='活期存款',
            amount=Money.yuan_to_cents(1800),
            currency='CNY',
        )
    )
    db.commit()

    data = build_today_pnl(db, family_id=1)

    assert data['invested_value'] == pytest.approx(2200.0)
    assert data['invested_ratio_of_assets'] == pytest.approx(55.0)
    by_key = {item['key']: item for item in data['classes']}
    assert by_key['stock']['share_of_invested'] == pytest.approx(50.0)
    assert by_key['fund']['share_of_invested'] == pytest.approx(50.0)
    # 两个分项占比必须闭合到 100（同一分母、同一舍入）
    assert sum(item['share_of_invested'] for item in data['classes']) == pytest.approx(100.0)


def test_家庭聚合失败只降级占比不拖垮整卡(db, make_position, make_transaction, frozen_today, monkeypatch):
    """占比是展示派生：家庭聚合挂了就只能少一个注解，不能把整张卡打成错误态。

    这条钉的是「分层独立」——`/api/summary/today-pnl/` 的主职责是当日收益，
    家庭总资产只是它的一个注解。若这里跟着抛 500，用户会看到「当日收益加载失败」，
    而实际上收益一分不差地算得出来。
    """
    import app.services.today_pnl as service

    sec, _ = _seed_stock(db, make_position, make_transaction)
    _seed_fund(db, make_position, make_transaction)
    _bar(db, sec.id, 'SH600519', OLDER, 10.0)
    _bar(db, sec.id, 'SH600519', PREV, 10.0)
    _bar(db, sec.id, 'SH600519', TODAY, 11.0)
    _nav(db, '000001', OLDER, 1.0)
    _nav(db, '000001', PREV, 1.0)
    _nav(db, '000001', TODAY, 1.1)

    def _boom(*args, **kwargs):
        raise RuntimeError('家庭聚合炸了')

    monkeypatch.setattr(service, 'family_totals', _boom)

    data = build_today_pnl(db, family_id=1)

    assert data['invested_ratio_of_assets'] is None
    # 主数据照常：收益、分项、占比（分项分母是投资类资产，与家庭聚合无关）
    assert data['total_pnl'] == pytest.approx(200.0)
    assert data['invested_value'] == pytest.approx(2200.0)
    assert sum(item['share_of_invested'] for item in data['classes']) == pytest.approx(100.0)


# ── 全站一本账（2026-11-04）：以下三条是「一直生效」的守卫 ──────────────
# 历史上首页市值取自 pnl 引擎的「当日价 × 引擎自算份额」，账户页取自
# `market_value_cents`（当前价 × `positions.quantity`），两套算法分叉出
# 93,712.70 的差额。任何人再把市值改回第二套口径，这三条都会红。


def test_首页市值与两张账户页同函数同值(db, make_position, make_transaction, frozen_today):
    """`/stocks` + `/funds` 的总市值 = 首页「投资类资产」，逐类也要相等。"""
    from app.services.position_aggregation import (
        get_fund_aggregation,
        get_securities_aggregation,
    )

    sec, _ = _seed_stock(db, make_position, make_transaction)
    _seed_fund(db, make_position, make_transaction)
    _bar(db, sec.id, 'SH600519', OLDER, 10.0)
    _bar(db, sec.id, 'SH600519', PREV, 10.0)
    _bar(db, sec.id, 'SH600519', TODAY, 11.0)
    _nav(db, '000001', OLDER, 1.0)
    _nav(db, '000001', PREV, 1.0)
    _nav(db, '000001', TODAY, 1.1)

    opts = {'dimension': 'product', 'page': 1, 'page_size': 0}
    stocks = Money.cents_to_yuan(get_securities_aggregation(db, 1, **opts)['total_market_value_cents'])
    funds = Money.cents_to_yuan(get_fund_aggregation(db, 1, **opts)['total_market_value_cents'])

    data = build_today_pnl(db, family_id=1)
    by_key = {c['key']: c for c in data['classes']}
    assert by_key['stock']['market_value'] == pytest.approx(stocks)
    assert by_key['fund']['market_value'] == pytest.approx(funds)
    assert data['invested_value'] == pytest.approx(stocks + funds)
    assert sum(c['market_value'] for c in data['classes']) == pytest.approx(data['invested_value'])


def test_无当日报价标的市值照样计入但当日收益为None(db, make_position, make_transaction, frozen_today):
    """导入型 / 停牌标的：市值按账户页同源计，收益不编 0.00。

    对应真实库里的 `026029`（净值恒 1 的组合，无 `daily_worth`）与
    `SZ127094`（可转债行情停在 4 月）：收益引擎按设计跳过它们，
    但账户页照常计市值——以前首页就少了这整整一块。
    """
    sec, _ = _seed_stock(db, make_position, make_transaction)
    _bar(db, sec.id, 'SH600519', OLDER, 10.0)
    _bar(db, sec.id, 'SH600519', PREV, 10.0)
    _bar(db, sec.id, 'SH600519', TODAY, 11.0)
    # 无锚点、无流水、无净值序列：模拟 `upsert_from_holding(write_anchor=False)`
    make_position(
        symbol='026029',
        name='净值恒1组合',
        quantity=5000,
        avg_price=1.0,
        current_price=1.0,
        asset_type='fund',
    )

    data = build_today_pnl(db, family_id=1)
    by_key = {c['key']: c for c in data['classes']}

    assert by_key['fund']['market_value'] == pytest.approx(5000.0)
    assert by_key['fund']['pnl'] is None  # 没数据 ≠ 没赚没亏
    assert data['unvalued_count'] == 1
    assert data['unvalued_value'] == pytest.approx(5000.0)
    assert data['status'] == 'partial'
    assert data['invested_value'] == pytest.approx(6100.0)


def test_份额唯一事实源是positions_quantity(db, make_position, make_transaction, frozen_today):
    """流水与 `quantity` 不一致时以 `quantity` 为准（终点锚倒推）。

    真实库 `SH688223` 的 quantity=3,100、流水净额=5,100、引擎自算=1,100，
    三者互不相同；没有这条守卫，新导入 / 手动校准过的持仓会再次分叉。
    """
    sec, pos = _seed_stock(db, make_position, make_transaction)
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='sell',
        quantity=50,
        price=10.0,
        confirm_date=PREV,
        symbol='SH600519',
    )
    # 人工校准成一个与流水净额（100−50=50）不同的权威份额
    pos.quantity = Money.shares_to_min_unit(300)
    db.commit()
    _bar(db, sec.id, 'SH600519', OLDER, 10.0)
    _bar(db, sec.id, 'SH600519', PREV, 10.0)
    _bar(db, sec.id, 'SH600519', TODAY, 11.0)

    data = build_today_pnl(db, family_id=1)
    holdings = {h['symbol']: h for h in data['holdings']}
    assert holdings['SH600519']['quantity'] == pytest.approx(300.0)
