# -*- coding: utf-8 -*-
"""债券兑付（bond_redeem）闭环（#2832）。

改版前的四条断点，每条对应一组用例：

1. **导入不关联持仓** —— 兑付硬编码 `position_id=None` + `entry_status='orphan'`，
   份额留在买入那天不动（`tests/domains/test_importers.py` 覆盖导入侧）；
2. **时间线把它当忽略类型** —— `_IGNORED_TYPES` 含 `bond_redeem`，成本线与累计已实现
   永远不含兑付这一笔（本文件 1~2）；
3. **不参与净投入** —— 兑付回款不计入 divest，收益率被低估（本文件 3）；
4. **白名单不认** —— 手动记账传 `op_type=bond_redeem` 被视图 abort(400)（本文件 4）。

另有两条边界：超量兑付必须报错而不是静默记孤儿（5、6），以及「到账净额含息」的
金额口径（7）——它是本卡唯一会算错钱的地方，单独钉住。
"""

from datetime import datetime

import pytest

from app.domains.positions.models import Position
from app.services.pnl_service import (
    compute_redeem_realized_cents,
    compute_sell_realized_cents,
    net_invested_by_position,
)
from app.services.trade_timeline import build_trade_timeline


def _day(y, m, d):
    return datetime(y, m, d, 10, 0, 0)


def _seed(make_position, symbol='110067', quantity=100.0, avg_price=1.0, account='测试账户'):
    return make_position(symbol=symbol, quantity=quantity, avg_price=avg_price, account_name=account)


def _txn(make_transaction, pos, **kwargs):
    kwargs.setdefault('symbol', pos.symbol)
    kwargs.setdefault('position_id', pos.id)
    kwargs.setdefault('ledger_id', pos.ledger_id)
    return make_transaction(**kwargs)


# ── 1. 时间线重放：兑付是份额变化，不是忽略类型 ─────────────────────


def test_timeline_replays_bond_redeem_as_share_change(db, make_position, make_transaction):
    """买入 100 份 @1.0，全额兑付到账 105 元（含息）：已实现 5 元、成本线断在清仓。

    这是「并入 _SHARE_TYPES」的判据：改版前兑付被 `_IGNORED_TYPES` 直接 continue，
    成本线停在买入当天、已实现恒为 0，用户看到「钱到账了但收益没变」。
    """
    pos = _seed(make_position, quantity=100.0, avg_price=1.0)
    _txn(make_transaction, pos, txn_type='buy', quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(
        make_transaction,
        pos,
        txn_type='bond_redeem',
        quantity=100,
        price=1.05,  # 券商成交均价（含息）
        amount=105,  # 实际到账净额
        trade_date=_day(2026, 6, 1),
    )

    result = build_trade_timeline(db, symbol=pos.symbol, family_id=1)

    # 已实现 = 到账 105 − 成本 100
    assert result['summary']['realized_pnl_yuan'] == 5.0
    # 兑付不是买卖决策：不进 sell_count（否则「卖出 N 笔」与买卖点个数对不上）
    assert result['summary']['sell_count'] == 0
    # 但它是回款，计入累计卖出金额
    assert result['summary']['total_sell_amount_yuan'] == 105.0
    # 不再出现在 ignored_types 里
    assert 'bond_redeem' not in result['summary']['ignored_types']
    # 清仓后成本线必须断开：不能留一个「仍有成本」的尾巴
    last_point = result['cost_line'][-1]
    assert last_point['date'] == '2026-01-05'


def test_timeline_partial_redeem_releases_cost_proportionally(db, make_position, make_transaction):
    """部分兑付（100 份里兑 40）：剩余成本按比例缩减，不是「总额不变」。"""
    pos = _seed(make_position, quantity=100.0, avg_price=1.0)
    _txn(make_transaction, pos, txn_type='buy', quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(
        make_transaction,
        pos,
        txn_type='bond_redeem',
        quantity=40,
        price=1.1,
        amount=44,
        trade_date=_day(2026, 3, 1),
    )

    result = build_trade_timeline(db, symbol=pos.symbol, family_id=1)

    # 释放成本 = 100 × 40/100 = 40；已实现 = 44 − 40 = 4
    assert result['summary']['realized_pnl_yuan'] == 4.0
    # 剩余 60 份仍持有，成本线继续（最后一点在兑付日）
    assert result['cost_line'][-1]['date'] == '2026-03-01'
    assert result['cost_line'][-1]['cost_yuan'] == 60.0
    assert result['cost_line'][-1]['avg_cost_yuan'] == 1.0


# ── 2. 净投入：兑付是回款 ──────────────────────────────────────


def test_net_invested_offsets_bond_redeem(db, make_position, make_transaction):
    """净投入 = 买入 − 兑付回款。不计兑付会让「投入」停在买入全额。"""
    pos = _seed(make_position, quantity=100.0, avg_price=1.0)
    _txn(make_transaction, pos, txn_type='buy', quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(
        make_transaction,
        pos,
        txn_type='bond_redeem',
        quantity=100,
        price=1.05,
        amount=105,
        trade_date=_day(2026, 6, 1),
    )

    net = net_invested_by_position(db, family_id=1)
    # 100 元投入 − 105 元回款 = −5 元（分）
    assert net[pos.id] == -500


# ── 3. 手动记账白名单 ─────────────────────────────────────────


def test_create_position_accepts_bond_redeem_op_type(client, db, make_position, make_transaction):
    """`op_type=bond_redeem` 必须被视图接受（改版前 `_KNOWN_OP_TYPES` 不含它 → 400）。

    走 HTTP 层而非直接调 service：漏改视图白名单时 service 测试仍会全绿，
    只有真实请求能证明这条链路通了。
    """
    pos = _seed(make_position, symbol='110068', quantity=100.0, avg_price=1.0)
    _txn(make_transaction, pos, txn_type='buy', quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    # make_transaction 只 flush 不 commit：db 会话若握着未提交的写事务，HTTP 侧
    # 的池连接写 pnl_daily_snapshots 时会撞「database is locked」，先提交释放锁
    db.commit()

    resp = client.post(
        '/api/positions/',
        json={
            'op_type': 'bond_redeem',
            'position_id': pos.id,
            'symbol': pos.symbol,
            'quantity': 100,
            'avg_price': 1.05,
            'amount': 105,
            'trade_date': '2026-06-01',
            'confirm_date': '2026-06-01',
        },
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()['message'] == '持仓已清空'

    db.expire_all()
    refreshed = db.query(Position).filter_by(id=pos.id).first()
    assert refreshed.quantity == 0
    assert refreshed.ownership_status == 'cleared'


# ── 4. 超量兑付必须报错 ───────────────────────────────────────


@pytest.fixture
def ledger_for_api(db):
    """手动记账请求不带 ledger_id 时，service 按 family 定位持仓即可。"""
    return None


def test_over_redeem_raises_value_error(db, make_position, make_transaction, client):
    """兑付量 > 持仓量 → 400 且提示明确，绝不静默落孤儿。

    改版前这种数据会生成一条孤儿流水，用户看到「钱到账、持仓还在」两个互相矛盾的
    事实，而且没有任何一处提示他买入流水漏了。
    """
    pos = _seed(make_position, symbol='110069', quantity=10.0, avg_price=1.0)
    _txn(make_transaction, pos, txn_type='buy', quantity=10, price=1.0, amount=10, trade_date=_day(2026, 1, 5))

    resp = client.post(
        '/api/positions/',
        json={
            'op_type': 'bond_redeem',
            'position_id': pos.id,
            'symbol': pos.symbol,
            'quantity': 30,
            'avg_price': 1.0,
            'amount': 30,
            'trade_date': '2026-06-01',
        },
    )

    assert resp.status_code == 400, resp.get_data(as_text=True)
    message = resp.get_json()['message']
    assert '兑付数量超过持仓' in message
    # 提示里要能看见两个数，否则用户不知道该改哪边
    assert '10' in message and '30' in message

    # 关键：没有任何 bond_redeem 流水落库（不是「记了条孤儿」）
    from app.domains.transactions.models import Transaction

    assert db.query(Transaction).filter_by(txn_type='bond_redeem').count() == 0


# ── 5. 金额口径：到账净额含息 ───────────────────────────────────


def test_redeem_realized_uses_settled_amount_not_price_times_qty():
    """已实现 = 到账额 − 成本，**不是** (均价 − 成本均价) × 份额。

    10 张面值 100、票息 3.5 的债：到账 1035，成交均价仍是 100。
    若照卖出口径算 (100 − 90) × 10 = 100，会把 35 元利息吃掉。
    """
    # 成本均价 90 元/张（90 × 10000 = 900000 price units），10 张
    redeem = compute_redeem_realized_cents(
        amount_cents=103_500,  # 1035 元
        avg_price_units=900_000,
        qty_units=100_000,  # 10 张
    )
    # 释放成本 = 90 元 × 10 张 = 900 元 = 90,000 分；已实现 = 1035 − 900 = 135 元
    assert redeem == 103_500 - 90_000
    assert redeem == 13_500

    # 反证：卖出口径只看价差，拿不到这 35 元利息
    sell_view = compute_sell_realized_cents(price_units=1_000_000, avg_price_units=900_000, qty_units=100_000)
    assert sell_view == 10_000  # 100 元
    assert redeem > sell_view
