# -*- coding: utf-8 -*-
"""交易时间线重放（#2171 · 详情页买卖点 / 成本线）。

口径锁（每条都有代码出处，改动需同步改这里）：
1. 成本含手续费（amount + fee）；卖出 / 取出成本不变（移动加权）；
2. 清仓（份额归零）成本线中断，该笔交易点 closed=True；再建仓重新出线；
3. 现金分红不进成本线、不进买卖点，只进 dividend_count；
4. 同日多笔成本线去重（保留当日最后一笔后的值）；
5. 收敛键是 symbol 写法变体（symbol_scope），**与 position_id 无关**——
   position_id 覆盖率仅 45%（#2009 实测），流水不填也必须收敛到；
6. ledger_id 可选过滤：不传=全部账户合并，传=单账户；
7. 未识别类型计数跳过，不静默丢弃；
8. trade_date 锚定 T 日，confirm_date 随点返回。
"""

from datetime import date, datetime

import pytest

from app.services.trade_timeline import build_trade_timeline, empty_trade_timeline

TL_URL = '/api/products/trade-timeline/'


def _day(y, m, d):
    return datetime(y, m, d, 10, 0, 0)


def _seed_position(make_position, symbol='004369', quantity=100.0, avg_price=1.0, account='测试账户'):
    return make_position(symbol=symbol, quantity=quantity, avg_price=avg_price, account_name=account)


def _txn(make_transaction, pos, **kwargs):
    """造流水：symbol / position_id / ledger_id 一律继承持仓行（写入侧对齐约定）。

    注意 make_transaction 默认 symbol='000001'——不显式继承就会与收敛键错位。
    """
    kwargs.setdefault('symbol', pos.symbol)
    kwargs.setdefault('position_id', pos.id)
    kwargs.setdefault('ledger_id', pos.ledger_id)
    return make_transaction(**kwargs)


# ── 基本重放 ────────────────────────────────────────────────────────
def test_basic_replay_buy_sell(db, make_position, make_transaction):
    """两笔买入 + 一笔卖出：点数、成本线、汇总计数。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.2, amount=120, trade_date=_day(2026, 2, 5))
    _txn(make_transaction, pos, txn_type='sell',
         quantity=50, price=1.5, amount=75, trade_date=_day(2026, 3, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert result['summary']['buy_count'] == 2
    assert result['summary']['sell_count'] == 1
    # 卖出 50/200 份后剩 150 份；成本按比例缩减：220 × 150/200 = 165
    assert result['summary']['current_quantity'] == 150.0
    assert result['summary']['current_cost_yuan'] == 165.0
    # 成本均价 = 165 / 150 = 1.1（成本率不变：两笔买入的加权率）
    assert result['summary']['current_avg_cost_yuan'] == 1.1
    # 三个买卖点（sell 也是决策点）
    assert [p['side'] for p in result['points']] == ['buy', 'buy', 'sell']
    assert result['points'][0]['date'] == '2026-01-05'
    # 成本线：三个不同日期各一条
    assert [c['date'] for c in result['cost_line']] == ['2026-01-05', '2026-02-05', '2026-03-05']
    assert result['cost_line'][-1]['cost_yuan'] == 165.0


def test_cost_includes_fee(db, make_position, make_transaction):
    """买入成本 = 成交金额 + 手续费（#2171 定稿口径 4）。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100, fee=50, trade_date=_day(2026, 1, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert result['summary']['current_cost_yuan'] == 100.5
    assert result['summary']['total_fee_yuan'] == 0.5
    assert result['points'][0]['fee_yuan'] == 0.5
    assert result['points'][0]['cost_after_yuan'] == 100.5


def test_sell_prorates_cost(db, make_position, make_transaction):
    """卖出后剩余成本按份额比例缩减（移动加权：成本率不变）。

    100 份成本 100 元（1 元/份）卖 40 份 → 剩 60 份成本 60 元，均价仍是 1.0。
    「成本总额不变」是错的：那会让成本率随减持被动抬升。
    """
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos, txn_type='sell',
         quantity=40, price=1.5, amount=60, trade_date=_day(2026, 2, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert result['summary']['current_quantity'] == 60.0
    assert result['summary']['current_cost_yuan'] == 60.0, '成本按剩余份额比例缩减'
    # 成本率不变：60 / 60 = 1.0
    assert result['summary']['current_avg_cost_yuan'] == 1.0


# ── 清仓与再建仓 ────────────────────────────────────────────────────
def test_clear_position_breaks_cost_line(db, make_position, make_transaction):
    """清仓笔 closed=True；清仓后不再产成本线点（线中断）。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos, txn_type='sell',
         quantity=100, price=1.2, amount=120, trade_date=_day(2026, 2, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    sell_point = result['points'][-1]
    assert sell_point['closed'] is True
    assert sell_point['cost_after_yuan'] == 0.0
    # 成本线只有建仓那天一条；清仓日不进线
    assert [c['date'] for c in result['cost_line']] == ['2026-01-05']
    assert result['summary']['current_quantity'] == 0.0


def test_rebuild_after_clear_restarts_cost_line(db, make_position, make_transaction):
    """清仓后再买入：新一轮成本线重新开始（不是续上前值）。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos, txn_type='sell',
         quantity=100, price=1.2, amount=120, trade_date=_day(2026, 2, 5))
    _txn(make_transaction, pos, txn_type='buy',
         quantity=50, price=0.8, amount=40, trade_date=_day(2026, 3, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert [c['date'] for c in result['cost_line']] == ['2026-01-05', '2026-03-05']
    assert result['cost_line'][-1]['cost_yuan'] == 40.0, '新一轮从 0 重新累计'
    assert result['points'][-1]['closed'] is False


# ── 分红与同日多笔 ──────────────────────────────────────────────────
def test_dividend_not_in_cost_line_or_points(db, make_position, make_transaction):
    """现金分红不改份额 / 成本，也不是买卖点；只进 dividend_count。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos, txn_type='dividend',
         quantity=0, price=0, amount=10, trade_date=_day(2026, 2, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert result['summary']['dividend_count'] == 1
    assert result['summary']['current_cost_yuan'] == 100.0
    assert len(result['points']) == 1, '分红不是买卖点'
    assert [c['date'] for c in result['cost_line']] == ['2026-01-05']


def test_same_day_trades_dedup_cost_line(db, make_position, make_transaction):
    """同日多笔：成本线去重为一条（当日最后一笔后的值），买卖点保留全部。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.5, amount=150, trade_date=_day(2026, 1, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert len(result['points']) == 2
    assert len(result['cost_line']) == 1
    assert result['cost_line'][0]['cost_yuan'] == 250.0


# ── 收敛键 ─────────────────────────────────────────────────────────
def test_symbol_variant_convergence(db, make_position, make_transaction):
    """同一产品两行持仓、两种字面量写法：入口任给一种都能收敛全部流水。

    模拟 #1662 实测的「同一标的写法变体长出多行」：第二行靠 symbol_norm
    （归一身份键）被 query_positions_by_symbol 命中，其字面量再进变体集合，
    挂在它名下的流水才不会漏。
    """
    from app.core.symbol_utils import symbol_identity

    pos_a = _seed_position(make_position, symbol='004369')
    pos_b = make_position(symbol='004369', quantity=100, avg_price=1.0,
                          account_name='账户B', symbol_norm=symbol_identity('004369', venue='OTC'))
    _txn(make_transaction, pos_a, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos_b, txn_type='buy',
         quantity=50, price=1.1, amount=55, trade_date=_day(2026, 1, 6))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert result['summary']['buy_count'] == 2, '两种写法的流水都要收敛到'


def test_null_position_id_still_counted(db, make_position, make_transaction):
    """position_id 为 NULL 的流水也必须收敛（覆盖率仅 45% 的实测教训，#2009）。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, position_id=None, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert result['summary']['buy_count'] == 1


def test_ledger_filter(db, make_position, make_transaction):
    """ledger_id 传了只重放该账户；不传全部合并。"""
    pos_a = _seed_position(make_position, account='账户A')
    pos_b = make_position(symbol='004369', quantity=50, avg_price=1.0, account_name='账户B')
    _txn(make_transaction, pos_a, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos_b, txn_type='buy',
         quantity=50, price=1.0, amount=50, trade_date=_day(2026, 1, 6))

    merged = build_trade_timeline(db, symbol='004369', family_id=1)
    single = build_trade_timeline(db, symbol='004369', family_id=1, ledger_id=pos_a.ledger_id)

    assert merged['summary']['buy_count'] == 2
    assert merged['summary']['current_quantity'] == 150.0
    assert single['summary']['buy_count'] == 1
    assert single['summary']['current_quantity'] == 100.0


# ── 边界与降级 ─────────────────────────────────────────────────────
def test_ignored_types_counted_not_silent(db, make_position, make_transaction):
    """未识别类型（拆分等）计数跳过，不静默丢弃、不进买卖点。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos, txn_type='split',
         quantity=0, price=0, amount=0, trade_date=_day(2026, 2, 5))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    assert result['summary']['ignored_count'] == 1
    assert 'split' in result['summary']['ignored_types']
    assert len(result['points']) == 1


def test_empty_timeline_shape():
    """空时间线结构与 build 一致（前端不分支）。"""
    result = empty_trade_timeline('004369')

    assert result['points'] == []
    assert result['cost_line'] == []
    assert result['summary']['buy_count'] == 0
    assert result['summary']['current_avg_cost_yuan'] is None


def test_missing_symbol_raises(db):
    with pytest.raises(ValueError):
        build_trade_timeline(db, symbol='', family_id=1)


def test_trade_date_anchors_point(db, make_position, make_transaction):
    """买卖点锚 T 日（trade_date），确认日随点返回（#2171 定稿口径 3）。"""
    pos = _seed_position(make_position)
    _txn(make_transaction, pos, txn_type='buy',
         quantity=100, price=1.0, amount=100,
         trade_date=_day(2026, 1, 5), confirm_date=date(2026, 1, 6))

    result = build_trade_timeline(db, symbol='004369', family_id=1)

    point = result['points'][0]
    assert point['date'] == '2026-01-05', '锚 T 日'
    assert point['confirm_date'] == '2026-01-06', '确认日供悬浮展示'


# ── 端点 ───────────────────────────────────────────────────────────
def test_endpoint_requires_symbol(client, db):
    resp = client.get(TL_URL)

    assert resp.status_code == 400


def test_endpoint_anonymous_returns_empty(client, db):
    """未登录：流水是私有数据，给空序列而非 401（可选登录，与 /resolve/ 一致）。"""
    resp = client.get(TL_URL, query_string={'symbol': '004369'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['points'] == []
    assert data['cost_line'] == []
    assert data['summary']['buy_count'] == 0
