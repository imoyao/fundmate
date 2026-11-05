# -*- coding: utf-8 -*-
"""手续费口径自洽测试：四个「总收益」出口必须报同一个数。

## 为什么必须有这条用例

费用在两个地方被扣，扣法完全不同：

- `pnl_service`：``total = realized + unrealized − buy_fee``（卖出费已在 realized 里）；
- XIRR / 现金流：把费用并进**现金流金额**（买入流出 +费、卖出流入 −费）。

两条路径各自成立，但**只要有一处漏改**，页面上就会出现「收益概览 495、
收益日历 500、资金流动 495」这种各说一个数的情况——不会报错，只会让人不再
相信任何一个数字。本文件用同一笔交易把四个出口钉在一起。

## 场景（数字手算可核）

| 日期 | 事件 | 金额 |
|---|---|---|
| 2026-01-05 | 买入 1000 份 @ 10.00，佣金 5 元 | 成交额 10,000 |
| 2026-01-06 | 净值 10.50 | 市值 10,500 |

- 未实现 = 10,500 − 10,000 = **500**
- 已实现 = 0（未卖出）
- 买入费 = **5**
- 总收益 = 500 − 5 = **495**

XIRR：现金流 ``−10,005`` 与虚拟卖出 ``+10,500`` ⇒ 总收益 ``10,500 − 10,005 = 495``。
资金流动：现金残差 ``−10,005``、市值 ``10,500`` ⇒ 期末资产 ``495``。
"""

import datetime as dt

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.services.cash_flow_service import build_cash_flow
from app.services.performance import calculate_portfolio_xirr
from app.services.pnl_calendar import build_pnl_series
from app.services.summary_service import get_summary_data

BUY_DATE = dt.date(2026, 1, 5)
NAV_UP_DATE = dt.date(2026, 1, 6)
EXPECTED_TOTAL = 495.0
EXPECTED_FEE = 5.0


def _seed(db, make_position, make_transaction):
    """建一笔「买入带佣金」的持仓，并在次日净值上涨。"""
    pos = make_position(
        symbol='000001',
        name='测试基金',
        quantity=1000,
        avg_price=10.0,
        # 快照价与净值同值：summary 走 `current_price` 回退、日历走 DailyWorth，
        # 两条取价链路都得对上，否则用例测的就不是「费用」而是「取价」。
        current_price=10.5,
        asset_type='fund',
        account_name='测试账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=10.0,
        amount=10000.0,
        confirm_date=BUY_DATE,
        symbol='000001',
        fee=Money.yuan_to_cents(EXPECTED_FEE),
    )
    db.add(DailyWorth(fund_code='000001', date=BUY_DATE, unit_nav=10.0))
    db.add(DailyWorth(fund_code='000001', date=NAV_UP_DATE, unit_nav=10.5))
    db.commit()
    return pos


def test_四个出口对同一笔费用给出同一个总收益(db, make_position, make_transaction):
    pos = _seed(db, make_position, make_transaction)

    # ① 家庭总览（realized + unrealized − buy_fee）
    summary = get_summary_data(db, family_id=1)
    assert summary['unrealized_pnl_cny'] == 500.0
    assert summary['realized_pnl_cny'] == 0.0
    assert summary['buy_fee_cny'] == EXPECTED_FEE
    assert summary['total_pnl_cny'] == EXPECTED_TOTAL

    # ② XIRR（费用并入现金流）
    xirr = calculate_portfolio_xirr(db, family_id=1)
    assert xirr['fees'] == EXPECTED_FEE
    assert xirr['total_return'] == EXPECTED_TOTAL

    # ③ 资金流动（现金残差扣费）
    cash_flow = build_cash_flow(db, family_id=1, ledger_id=pos.ledger_id)
    assert cash_flow['totals']['total_return'] == EXPECTED_TOTAL

    # ④ 收益日历（累计扣费后做日差分）
    series = build_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')
    day_sum = round(sum(d['daily_pnl'] for d in series['days'] if d['daily_pnl'] is not None), 2)
    assert day_sum == EXPECTED_TOTAL


def test_费用记在买入当天而不是平摊到后面(db, make_position, make_transaction):
    """买入日应显示「亏了 5 元佣金」，次日只显示价格涨跌 500。

    这是「累计扣、归因按增量」两个动作的接缝：若只按当日扣 `day_total_pnl`，
    次日差分会把前一天的 5 元再赚回来，报成 +505。
    """
    _seed(db, make_position, make_transaction)
    series = build_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')
    by_date = {d['date']: d['daily_pnl'] for d in series['days']}

    assert by_date['2026-01-05'] == -EXPECTED_FEE
    assert by_date['2026-01-06'] == 500.0


def test_卖出费不重复扣(db, make_position, make_transaction):
    """卖出费已在 `realized_pnl` 里扣过，总收益口径不得再扣一次。

    场景：买 1000@10（费 5）→ 卖 1000@11（费 6），仓位归零。
    真实到手 = 11,000 − 6 − 10,000 − 5 = 989；双扣会变成 983。
    """
    pos = make_position(symbol='000002', name='测试基金2', quantity=0, avg_price=11.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=10.0,
        amount=10000.0,
        confirm_date=dt.date(2026, 1, 5),
        symbol='000002',
        fee=Money.yuan_to_cents(5),
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='sell',
        quantity=1000,
        price=11.0,
        amount=11000.0,
        confirm_date=dt.date(2026, 1, 8),
        symbol='000002',
        # 卖出已实现 = (11 − 10) × 1000 − 6 = 994，由写入侧结转，这里显式给定
        realized_pnl=Money.yuan_to_cents(994),
        fee=Money.yuan_to_cents(6),
    )
    db.commit()

    summary = get_summary_data(db, family_id=1)
    # 只剩买入费 5：卖出费已在 realized 的 994 里
    assert summary['buy_fee_cny'] == 5.0
    assert summary['realized_pnl_cny'] == 994.0
    assert summary['total_pnl_cny'] == 989.0

    xirr = calculate_portfolio_xirr(db, family_id=1)
    assert xirr['fees'] == 11.0  # 展示口径是双边合计
    assert xirr['total_return'] == 989.0
