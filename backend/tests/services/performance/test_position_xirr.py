# -*- coding: utf-8 -*-
"""#2009：`calculate_position_xirr` 的现金流收敛 —— 单持仓行只管自己的流水。

## 修的 bug

此前 `calculate_position_xirr` 只按 `family_id` 过滤流水，而市值侧
`_get_position_current_value(db, position)` 只取**这一行** ——
「现金流是全家、市值是单行」，两侧口径不一致。后果：家庭里只要多于一个标的，
算出来的年化就是错的，且标的越多越趋近于家庭整体收益
（本机库实测：family 1 有 **187 个不同 symbol**，故对多标的用户基本必错）。

## 收敛键（拍板结论见 #2009 评论）

`symbol`（写法变体）+ `ledger_id`。依据：`positions` 有唯一约束
`(ledger_id, symbol)` 故组合 ↔ 持仓行一一对应；而 `transactions.position_id` 覆盖率仅 45%；
且库里「`ledger_id` 空但 `symbol` 非空」的记录为 0 条（缺账户归属的流水同时也没有 symbol）。

## 覆盖

1. 单标的（回归基线）；
2. **多标的同账户 → B 的流水不得泄漏进 A**（本卡核心，复现原始 bug 的形态）；
3. **同 symbol 多账户 → 只算本账户那一行**（与 `scope=symbol` 跨账户汇总刻意相反）；
4. `scope=portfolio` 不回归（它本来就该吃全量）；
5. 端点级：抽屉实际走的 `scope=position` HTTP 路径。

市值口径用 `asset_type='bond'`（走 `current_price` 分支，不依赖 NAV / 行情表，
避免用例被无关的数据前置拖累，与 `test_symbol_xirr.py` 同一约定）。
"""

import math
from datetime import date, timedelta

from app.services.performance.calculators import (
    calculate_portfolio_xirr,
    calculate_position_xirr,
)

# 「持有一整年」的基准：相对今天倒推 365 天，避免写死年份让 XIRR 期望随真实日期漂移
ONE_YEAR_AGO = date.today() - timedelta(days=365)


def _bond_position(make_position, symbol, account_name, quantity, current_price):
    """建一条用 `current_price` 定值的持仓。

    同 `account_name` 会映射到**同一个** `ledger_id`（见 conftest `_ensure_ledger`），
    故「多标的同账户」用它构造即可。
    """
    return make_position(
        symbol=symbol,
        name=f'测试标的{symbol}',
        account_name=account_name,
        asset_type='bond',
        quantity=quantity,
        current_price=current_price,
    )


class TestSinglePosition:
    def test_buy_then_hold_is_buy_plus_virtual_sale(self, db, make_position, make_transaction):
        """单标的、单账户：现金流 = 买入（负）+ 虚拟卖出（当前市值，正）。"""
        pos = _bond_position(make_position, '000001', '账户A', quantity=1000, current_price=1.2)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            account_name='账户A',
            symbol='000001',
        )

        r = calculate_position_xirr(db, pos.id, family_id=1)

        assert r['cashflow_count'] == 2
        assert r['total_invested'] == 1000.0
        assert r['current_value'] == 1200.0
        assert r['total_return'] == 200.0
        # 持有满一年 +20% → XIRR 解应为 0.20
        assert abs(r['xirr'] - 0.20) < 0.005
        assert not math.isnan(r['xirr'])


class TestOtherPositionsDoNotLeak:
    def test_other_position_cashflows_are_excluded(self, db, make_position, make_transaction):
        """#2009 核心：同账户内**另一个标的**的流水不得计入本持仓年化。

        复现 bug 原始形态（见 #2009 正文的取证脚本）：A 只买 1000，B 买卖 50000 与 A 无关。
        修复前 A 的 `total_invested` 会变成 51000、现金流 4 笔、XIRR 被稀释到 ~0.004。
        """
        pos_a = _bond_position(make_position, 'AAA', '账户A', quantity=1000, current_price=1.2)
        pos_b = _bond_position(make_position, 'BBB', '账户A', quantity=0, current_price=1.0)
        # 前提断言：同一 account_name 必须落在同一个 ledger 上，否则本用例验证的不是「同账户」
        assert pos_a.ledger_id == pos_b.ledger_id

        make_transaction(
            pos_a.id,
            pos_a.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            account_name='账户A',
            symbol='AAA',
        )
        make_transaction(
            pos_b.id,
            pos_b.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=50000,
            confirm_date=ONE_YEAR_AGO,
            account_name='账户A',
            symbol='BBB',
        )
        make_transaction(
            pos_b.id,
            pos_b.ledger_id,
            txn_type='sell',
            asset_type='bond',
            amount=50000,
            confirm_date=date.today(),
            account_name='账户A',
            symbol='BBB',
        )

        r_a = calculate_position_xirr(db, pos_a.id, family_id=1)

        assert r_a['cashflow_count'] == 2, 'B 的流水泄漏进来了（#2009 复发）'
        assert r_a['total_invested'] == 1000.0, 'B 的买入额泄漏进来了（#2009 复发）'
        assert r_a['current_value'] == 1200.0
        assert abs(r_a['xirr'] - 0.20) < 0.005, '年化被 B 的流水稀释了（#2009 复发）'


class TestSameSymbolAcrossAccounts:
    def test_only_this_account_is_counted(self, db, make_position, make_transaction):
        """同 symbol 多账户：按 position 收敛时只算**本账户**那一行。

        与 `scope=symbol`（跨账户汇总成一条时间线）刻意相反 —— 那是产品级口径，
        这里是持仓行口径，两者不该串。
        """
        pos_a = _bond_position(make_position, '000001', '账户A', quantity=1000, current_price=1.2)
        pos_b = _bond_position(make_position, '000001', '账户B', quantity=500, current_price=1.2)
        assert pos_a.ledger_id != pos_b.ledger_id

        make_transaction(
            pos_a.id,
            pos_a.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            account_name='账户A',
            symbol='000001',
        )
        make_transaction(
            pos_b.id,
            pos_b.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=500,
            confirm_date=date.today(),
            account_name='账户B',
            symbol='000001',
        )

        r_a = calculate_position_xirr(db, pos_a.id, family_id=1)
        r_b = calculate_position_xirr(db, pos_b.id, family_id=1)

        assert r_a['total_invested'] == 1000.0, '账户 B 的流水串进了账户 A'
        assert r_a['current_value'] == 1200.0
        assert r_b['total_invested'] == 500.0, '账户 A 的流水串进了账户 B'
        assert r_b['current_value'] == 600.0


class TestPortfolioScopeUnchanged:
    def test_portfolio_still_eats_everything(self, db, make_position, make_transaction):
        """`scope=portfolio` 不回归：它本来就该吃全量，不受本次收敛影响。"""
        pos_1 = _bond_position(make_position, 'AAA', '账户A', quantity=0, current_price=1.0)
        pos_2 = _bond_position(make_position, 'BBB', '账户A', quantity=0, current_price=1.0)
        for pos, amount in ((pos_1, 1000), (pos_2, 2000)):
            make_transaction(
                pos.id,
                pos.ledger_id,
                txn_type='buy',
                asset_type='bond',
                amount=amount,
                confirm_date=date(2024, 1, 1),
                account_name='账户A',
                symbol=pos.symbol,
            )
            make_transaction(
                pos.id,
                pos.ledger_id,
                txn_type='sell',
                asset_type='bond',
                amount=amount * 2,
                confirm_date=date(2025, 1, 1),
                account_name='账户A',
                symbol=pos.symbol,
            )

        r_pos = calculate_position_xirr(db, pos_1.id, family_id=1)
        r_portfolio = calculate_portfolio_xirr(db, family_id=1)

        assert r_pos['cashflow_count'] == 2  # 只吃 AAA
        assert r_pos['total_invested'] == 1000.0
        assert r_portfolio['cashflow_count'] == 4  # 全量口径不变
        assert r_portfolio['total_invested'] == 3000.0


class TestEndpoint:
    """端点级：前端持仓交易抽屉实际走的就是这条 HTTP 路径。"""

    def test_scope_position_returns_single_row_scope(self, client, db, make_position, make_transaction):
        pos_a = _bond_position(make_position, 'AAA', '账户A', quantity=1000, current_price=1.2)
        pos_b = _bond_position(make_position, 'BBB', '账户A', quantity=0, current_price=1.0)
        make_transaction(
            pos_a.id,
            pos_a.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            account_name='账户A',
            symbol='AAA',
        )
        make_transaction(
            pos_b.id,
            pos_b.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=50000,
            confirm_date=ONE_YEAR_AGO,
            account_name='账户A',
            symbol='BBB',
        )
        # make_transaction 只 flush；HTTP 请求走另一个 session，不 commit 看不到
        db.commit()

        resp = client.get(f'/api/performance/xirr/?scope=position&position_id={pos_a.id}')

        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['cashflow_count'] == 2, '端点回的仍是全家口径（#2009）'
        assert data['total_invested'] == 1000.0
        assert data['current_value'] == 1200.0
        assert not math.isnan(data['xirr'])
