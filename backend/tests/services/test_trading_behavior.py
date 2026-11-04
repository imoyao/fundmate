# -*- coding: utf-8 -*-
"""#2619 交易行为画像测试。

锁定五件事：
1. **窗口只筛样本、不裁配对**——卖出在窗口内、买入在窗口外，持有期仍算得出；
2. **分位数口径**——样本 = 每笔卖出的份额加权持有天数，样本 < 2 回 None；
3. **交易结构**——连续加仓按「相邻两笔均买入」计数、割肉回补每次亏损卖出只记一次；
4. **诚实降级**——无流水 / 单笔 / 无价格历史时各字段为 None 或覆盖率 0，
   绝不填 0 冒充（零卖出 ⇒ 买卖比为 None）；
5. **无评价性措辞**——返回值只有统计量。
"""

import datetime as dt

import pytest

from app.services.ai_recognizer.tools import ToolExecutor
from app.services.analytics.trading_behavior import (
    _percentile_rank,
    build_trading_behavior,
)

D1 = dt.date(2026, 1, 5)
D2 = dt.date(2026, 1, 6)
D3 = dt.date(2026, 1, 7)
D4 = dt.date(2026, 1, 8)
D5 = dt.date(2026, 1, 9)


def _pos(make_position, *, symbol='000301', price=1.1, quantity=1000, name='行为测试基金'):
    return make_position(
        symbol=symbol,
        name=name,
        quantity=quantity,
        avg_price=1.0,
        current_price=price,
        asset_type='fund',
        account_name='行为测试账户',
    )


def _txn(make_transaction, pos, *, txn_type, date, quantity=1000, price=1.0, amount=None):
    return make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type=txn_type,
        quantity=quantity,
        price=price,
        amount=amount,
        confirm_date=date,
        symbol=pos.symbol,
    )


def test_无交易用户_全字段诚实回空(db):
    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['holding']['samples'] == 0
    assert d['holding']['avg_days'] is None
    assert d['holding']['p50'] is None
    assert d['trading']['buy_count'] == 0
    assert d['trading']['buy_sell_ratio'] is None  # 零卖出不是 0
    assert d['trading']['turnover_pct'] is None
    assert d['buy_price_percentile']['mean'] is None
    assert d['buy_price_percentile']['coverage_pct'] is None
    assert d['structure']['consecutive_add_count'] == 0


def test_仅一笔买入_分位与持有期均无样本(db, make_position, make_transaction):
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1)

    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['trading']['buy_count'] == 1
    assert d['trading']['sell_count'] == 0
    assert d['trading']['buy_sell_ratio'] is None
    assert d['holding']['samples'] == 0
    assert d['holding']['p25'] is None


def test_窗口只筛样本不裁配对_窗口内卖出仍能算持有期(db, make_position, make_transaction):
    """买入在 D1（窗口外）、卖出在 D4（窗口内）⇒ 持有 3 天仍算得出。

    变异探针：把流水先按窗口裁剪 ⇒ 卖出找不到买入批次，`samples` 变 0、`closed_count` 变 0。
    """
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1, amount=1000)
    _txn(make_transaction, pos, txn_type='sell', date=D4, quantity=1000, price=1.1, amount=1100)

    d = build_trading_behavior(db, family_id=1, start_date=D4.isoformat(), end_date=D4.isoformat())

    assert d['trading']['buy_count'] == 0  # 买入不在窗口
    assert d['trading']['sell_count'] == 1
    assert d['holding']['samples'] == 1
    assert d['holding']['avg_days'] == pytest.approx(3.0, abs=0.01)
    assert d['structure']['closed_count'] == 1


def test_持有期分位数_按每笔卖出样本(db, make_position, make_transaction):
    """两轮持有：1 天（D1→D2）与 2 天（D3→D5）⇒ p25/p50/p75 = 1.25 / 1.5 / 1.75。"""
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1, amount=1000)
    _txn(make_transaction, pos, txn_type='sell', date=D2, quantity=1000, price=1.0, amount=1000)
    _txn(make_transaction, pos, txn_type='buy', date=D3, amount=1000)
    _txn(make_transaction, pos, txn_type='sell', date=D5, quantity=1000, price=1.0, amount=1000)

    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['holding']['samples'] == 2
    assert d['holding']['avg_days'] == pytest.approx(1.5, abs=0.01)  # 份额加权：(1 + 2)/2
    # 分位数与 avg 同为 1 位小数（实现约定）：1.25→1.2、1.75→1.8
    assert d['holding']['p25'] == pytest.approx(1.2, abs=0.01)
    assert d['holding']['p50'] == pytest.approx(1.5, abs=0.01)
    assert d['holding']['p75'] == pytest.approx(1.8, abs=0.01)


def test_连续加仓按相邻买入对数计数(db, make_position, make_transaction):
    """三笔连续买入 ⇒ 2 次加仓；随后一笔卖出后买入不算连续加仓。"""
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1, amount=1000)
    _txn(make_transaction, pos, txn_type='buy', date=D2, amount=1000)
    _txn(make_transaction, pos, txn_type='buy', date=D3, amount=1000)
    _txn(make_transaction, pos, txn_type='sell', date=D4, quantity=1000, price=1.0, amount=1000)
    _txn(make_transaction, pos, txn_type='buy', date=D5, amount=1000)

    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['structure']['consecutive_add_count'] == 2


def test_同日拆单不算连续加仓(db, make_position, make_transaction):
    """同一天两笔买入（渠道拆单）只算一次建仓，不计加仓；次日再买才计。"""
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1, quantity=500, amount=500)
    _txn(make_transaction, pos, txn_type='buy', date=D1, quantity=500, amount=500)
    _txn(make_transaction, pos, txn_type='buy', date=D2, amount=1000)

    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['trading']['buy_count'] == 3
    assert d['structure']['consecutive_add_count'] == 1  # 仅 D1→D2 那一次


def test_割肉后回补每次亏损卖出只记一次(db, make_position, make_transaction):
    """买 1.0 → 卖 0.8（亏）→ 买 → 买：只记 1 次回补（第二次买入是加仓）。"""
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1, amount=1000)
    _txn(make_transaction, pos, txn_type='sell', date=D2, quantity=1000, price=0.8, amount=800)
    _txn(make_transaction, pos, txn_type='buy', date=D3, amount=900)
    _txn(make_transaction, pos, txn_type='buy', date=D4, amount=900)

    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['structure']['rebuy_after_loss_count'] == 1


def test_盈利卖出不触发回补计数(db, make_position, make_transaction):
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1, amount=1000)
    _txn(make_transaction, pos, txn_type='sell', date=D2, quantity=1000, price=1.2, amount=1200)
    _txn(make_transaction, pos, txn_type='buy', date=D3, amount=1200)

    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['structure']['rebuy_after_loss_count'] == 0


def test_换手率按区间成交额与当前市值(db, make_position, make_transaction):
    """区间买入 1000 元、当前市值 1100 元 ⇒ 换手 1000/2/1100 ≈ 45.45%。"""
    pos = _pos(make_position, price=1.1, quantity=1000)
    _txn(make_transaction, pos, txn_type='buy', date=D1, amount=1000)

    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['trading']['turnover_pct'] == pytest.approx(45.45, abs=0.02)


def test_无价格历史_买点分位覆盖率0而非均值0(db, make_position, make_transaction):
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1, amount=1000)

    d = build_trading_behavior(db, family_id=1, start_date=D1.isoformat(), end_date=D5.isoformat())

    assert d['buy_price_percentile']['mean'] is None
    assert d['buy_price_percentile']['covered_buys'] == 0
    assert d['buy_price_percentile']['total_buys'] == 1
    assert d['buy_price_percentile']['coverage_pct'] == pytest.approx(0.0)


def test_百分位秩纯函数_最低与最高():
    closes = [float(i) for i in range(1, 21)]  # 1..20
    assert _percentile_rank(closes, 0.5) == pytest.approx(0.0)
    assert _percentile_rank(closes, 20.5) == pytest.approx(100.0)
    assert _percentile_rank(closes, 10.0) == pytest.approx(50.0)


def test_工具层_正常调用且无评价性措辞(db, make_position, make_transaction):
    pos = _pos(make_position)
    _txn(make_transaction, pos, txn_type='buy', date=D1, amount=1000)
    db.commit()  # 工具用独立会话，必须提交才可见

    r = ToolExecutor.run('get_trading_behavior', {'start_date': D1.isoformat(), 'end_date': D5.isoformat()})
    assert r['status'] == 'success', r.get('msg')
    payload = r['data']
    assert payload['trading']['buy_count'] == 1
    forbidden = ('过高', '过低', '追涨', '糟糕', '很好', '优秀', '建议')
    text = str(payload)
    assert not any(word in text for word in forbidden)


def test_工具层_symbol限定(db, make_position, make_transaction):
    pos_a = _pos(make_position, symbol='000301')
    pos_b = _pos(make_position, symbol='000302', name='另一只')
    _txn(make_transaction, pos_a, txn_type='buy', date=D1, amount=1000)
    _txn(make_transaction, pos_b, txn_type='buy', date=D1, amount=2000)
    db.commit()

    r = ToolExecutor.run(
        'get_trading_behavior', {'start_date': D1.isoformat(), 'end_date': D5.isoformat(), 'symbol': '000302'}
    )
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['scope'] == 'symbol'
    assert r['data']['trading']['buy_count'] == 1


def test_工具层_日期格式非法被拒绝():
    r = ToolExecutor.run('get_trading_behavior', {'start_date': '2026/01/05'})
    assert r['status'] == 'error'
    assert '不匹配格式' in r['msg']
