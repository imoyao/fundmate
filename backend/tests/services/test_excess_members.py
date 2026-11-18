# -*- coding: utf-8 -*-
"""#3107 组合级超额聚合的成员规范化（`excess_members`）。

两种形态都会让组合「永久降级」，而它们都不是数据缺口：

1. **清仓后闲置的旧成员**（区间内无持仓 ⇒ `baseline=None`、持仓数 0）：
   贡献恒 0，跳过不改变 Σ；留着则整组 `baseline_missing`。真库实测组合 1 的
   账本 2024-06 全部清仓，连「近1月」都是 0 点。
2. **区间中途才建仓的新成员**（区间首日还没有资产 ⇒ `baseline=None`，但持仓数 >0）：
   期初资产**就是 0**，组合收益率 = Σ区间盈亏 ÷ Σ期初资产，归零后参与聚合是正确口径。

第三条边界同样必须钉住：**老成员缺基线是真缺口**，一律保留 ⇒ 整组继续降级，
不能拿「部分成员」冒充「整个组合」。
"""

import datetime as dt

import pytest

from app.domains.funds.models import DailyWorth
from app.domains.indices.models import IndexDaily
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.analytics.benchmark_excess import build_scope_excess
from app.services.analytics.excess_members import (
    build_member_payloads,
    normalize_member_payloads,
)

D1 = dt.date(2026, 1, 5)  # 老成员买入日（区间前一天）
D2 = dt.date(2026, 1, 6)  # 区间首日 / 新成员建仓日
D3 = dt.date(2026, 1, 7)  # 区间末日


def _payload(baseline, total_positions, first_txn=None):
    return {
        'range_baseline': baseline,
        'coverage': {'total_positions': total_positions},
        'month_total': 0.0,
        'first_txn_date': first_txn,
    }


def test_清仓空成员被剔除_活成员保留():
    kept = normalize_member_payloads(
        {1: _payload(1000.0, 3, '2020-01-02'), 2: _payload(None, 0, '2020-01-02')},
        D2.isoformat(),
    )

    assert list(kept) == [1]


def test_区间内才建仓的新成员_基线归零():
    kept = normalize_member_payloads({1: _payload(None, 4, D2.isoformat())}, D2.isoformat())

    assert kept[1]['range_baseline'] == 0.0
    # 其余字段原样保留（只改基线这一处）
    assert kept[1]['coverage']['total_positions'] == 4


def test_老成员缺基线是真缺口_不归零也不剔除():
    kept = normalize_member_payloads({1: _payload(None, 5, '2019-03-04')}, D2.isoformat())

    assert kept[1]['range_baseline'] is None


def test_首日当天建仓也算新成员():
    """`first_txn_date == start` 时区间前一日的资产同样是 0 ⇒ 归零。"""
    kept = normalize_member_payloads({1: _payload(None, 1, D2.isoformat())}, D2.isoformat())

    assert kept[1]['range_baseline'] == 0.0


def test_无流水起点却有持仓_不猜_保留原样():
    """流水与持仓错配（#1916 一类）无从判断建仓时点，宁可降级。"""
    kept = normalize_member_payloads({1: _payload(None, 2, None)}, D2.isoformat())

    assert kept[1]['range_baseline'] is None


def test_基线为0的有持仓成员保留():
    kept = normalize_member_payloads({1: _payload(0.0, 2, '2020-01-02')}, D2.isoformat())

    assert kept[1]['range_baseline'] == 0.0


def test_入参不被修改():
    payloads = {1: _payload(None, 3, D2.isoformat()), 2: _payload(1000.0, 3, '2020-01-02')}

    normalize_member_payloads(payloads, D2.isoformat())

    assert payloads[1]['range_baseline'] is None


def test_全空成员_返回空集合():
    assert normalize_member_payloads({1: _payload(None, 0, D1.isoformat())}, D2.isoformat()) == {}


# ── 导入型持仓：只有 `positions.snapshot_date` 锚点、没有买入流水 ──────────
def test_只有锚点没有流水_也算区间内新建_基线归零():
    """账本 21 的形态：30 笔导入持仓 + 零买入流水 ⇒ `first_txn_date` 恒 None。

    变异探针：把 `_starts_after` 改回只认 `first_txn_date`，本例回落 None。
    """
    kept = normalize_member_payloads(
        {1: _payload(None, 30, None)}, D2.isoformat(), {1: dt.date(2026, 1, 6).isoformat()}
    )

    assert kept[1]['range_baseline'] == 0.0


def test_锚点早于区间首日_仍视为老成员_不归零():
    """锚点在区间之前 ⇒ 期初就有资产，缺基线是真缺口，不许猜。"""
    kept = normalize_member_payloads({1: _payload(None, 3, None)}, D2.isoformat(), {1: '2020-01-02'})

    assert kept[1]['range_baseline'] is None


def test_流水比锚点更早_按更早的算():
    """老账户后来又导入过一次持仓：存在起点取两者更早的那天。"""
    kept = normalize_member_payloads({1: _payload(None, 5, '2019-03-04')}, D2.isoformat(), {1: D2.isoformat()})

    assert kept[1]['range_baseline'] is None


def test_锚点查询按成员分组_只取有锚点的行(db, make_position):
    from app.services.analytics.excess_members import _anchor_dates

    l1 = Ledger(name='导入型', ledger_type='fund', family_id=1)
    l2 = Ledger(name='无锚点', ledger_type='fund', family_id=1)
    db.add_all([l1, l2])
    db.flush()
    make_position(
        symbol='000031',
        name='导入A',
        quantity=100,
        avg_price=1.0,
        asset_type='fund',
        ledger_id=l1.id,
        snapshot_date=D1,
        snapshot_quantity=100,
    )
    make_position(
        symbol='000046',
        name='导入B',
        quantity=100,
        avg_price=1.0,
        asset_type='fund',
        ledger_id=l1.id,
        snapshot_date=D2,
        snapshot_quantity=100,
    )
    make_position(symbol='000059', name='无锚点', quantity=100, avg_price=1.0, asset_type='fund', ledger_id=l2.id)

    out = _anchor_dates(db, 1, [l1.id, l2.id])

    assert out == {l1.id: D1.isoformat()}  # 取最早锚点；无锚点成员不入表


# ── 集成回归：新成员 / 清仓成员都不再拖垮整组 ──────────────────────
def _add_index(db, code, day, close):
    db.add(IndexDaily(index_code=code, trade_date=day, close=close, source='tencent'))
    db.commit()


def _buy(db, make_position, make_transaction, ledger, symbol, confirm_date):
    pos = make_position(
        symbol=symbol, name=f'{symbol}基金', quantity=1000, avg_price=1.0, asset_type='fund', ledger_id=ledger.id
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=ledger.id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=confirm_date,
        symbol=symbol,
    )
    db.commit()
    return pos


def test_组合_新成员与清仓成员共存时仍可算(db, make_position, make_transaction):
    """老成员 +10%、新成员区间首日建仓且不动、清仓成员空 ⇒ 组合应报 10%。

    变异探针：把 `normalize_member_payloads` 直接 `return payload_by_id`，
    本用例立刻回 `range_rate is None` + `baseline_missing`。
    """
    pf = Portfolio(name='混合成员组合', family_id=1)
    db.add(pf)
    db.flush()
    old = Ledger(name='老成员', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    fresh = Ledger(name='新成员', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    idle = Ledger(name='已清仓成员', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add_all([old, fresh, idle])
    db.flush()

    _buy(db, make_position, make_transaction, old, '000031', D1)
    _buy(db, make_position, make_transaction, fresh, '000046', D2)
    db.add_all(
        [
            DailyWorth(fund_code='000031', date=D1, unit_nav=1.0),
            DailyWorth(fund_code='000031', date=D2, unit_nav=1.0),
            DailyWorth(fund_code='000031', date=D3, unit_nav=1.1),
            DailyWorth(fund_code='000046', date=D2, unit_nav=1.0),
            DailyWorth(fund_code='000046', date=D3, unit_nav=1.0),
        ]
    )
    db.commit()
    _add_index(db, '000300.SH', D2, 4000.0)
    _add_index(db, '000300.SH', D3, 4200.0)

    out = build_scope_excess(db, 1, D2.isoformat(), D3.isoformat(), portfolio_id=pf.id)

    assert out['range_reason'] is None
    # 分母只含老成员的期初 1000 元；分子 100 元（新成员不动）
    assert out['range_baseline'] == pytest.approx(1000.0)
    assert out['range_rate'] == pytest.approx(10.0)
    assert out['excess_return'] == pytest.approx(5.0)
    assert out['series'], '曲线不该因为空成员被清空'


# ── 请求内复用：家庭级派生结果算一遍就够，且不得改变任何数值 ──────────
def _collect_queries(db, fn):
    from sqlalchemy import event

    seen = []
    target = db.get_bind()

    def _on(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    event.listen(target, 'before_cursor_execute', _on)
    try:
        out = fn()
    finally:
        event.remove(target, 'before_cursor_execute', _on)
    return out, seen


def _two_member_portfolio(db, make_position, make_transaction):
    pf = Portfolio(name='复用组合', family_id=1)
    db.add(pf)
    db.flush()
    l1 = Ledger(name='成员一', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    l2 = Ledger(name='成员二', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add_all([l1, l2])
    db.flush()
    _buy(db, make_position, make_transaction, l1, '000031', D1)
    _buy(db, make_position, make_transaction, l2, '000046', D1)
    db.add_all(
        [
            DailyWorth(fund_code='000031', date=D1, unit_nav=1.0),
            DailyWorth(fund_code='000031', date=D2, unit_nav=1.1),
            DailyWorth(fund_code='000031', date=D3, unit_nav=1.2),
            DailyWorth(fund_code='000046', date=D1, unit_nav=1.0),
            DailyWorth(fund_code='000046', date=D2, unit_nav=0.9),
            DailyWorth(fund_code='000046', date=D3, unit_nav=0.95),
        ]
    )
    db.commit()
    return pf, [l1.id, l2.id]


def test_逐成员聚合_家庭级查询只算一遍且数值不变(db, make_position, make_transaction):
    from app.services.pnl_calendar import build_daily_pnl_series

    _pf, ids = _two_member_portfolio(db, make_position, make_transaction)
    s, e = D2.isoformat(), D3.isoformat()

    # 逐成员直算（无复用）：基准
    serial, serial_sql = _collect_queries(
        db, lambda: {lid: build_daily_pnl_series(db, 1, s, e, ledger_id=lid) for lid in ids}
    )
    # 聚合入口（内部 `request_memo` 开复用）
    grouped, grouped_sql = _collect_queries(db, lambda: build_member_payloads(db, 1, ids, s, e))

    # ① 数值逐位一致（复用只该省时间，不该改口径）
    assert grouped == normalize_member_payloads(serial, s)

    def _presence_max(stmts):
        return sum(1 for q in stmts if 'max(daily_worth.date)' in q or 'max(price_history.trade_date)' in q)

    # ② 家庭级「最新价」组查：两个成员都是场外基金 ⇒ 直算各查一次净值（共 2），复用后只 1 次
    assert _presence_max(serial_sql) == 2
    assert _presence_max(grouped_sql) == 1
    assert len(grouped_sql) < len(serial_sql)
